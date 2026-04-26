#!/usr/bin/env python3
"""Modern Travel Planner GUI - Multi-engine IA with web search via SearXNG."""

import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, simpledialog, ttk
import json
import threading
import os
import sys
import requests
from document_generator import DocumentGenerator
from llm_client import build_client, call_llm, format_tool_result

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


INFO_REQUISE = (
    "Pour établir votre planning, j'ai besoin des informations suivantes :\n\n"
    "   📍  Destination(s) souhaitée(s)\n"
    "   📅  Dates de départ et de retour\n"
    "   👥  Nombre de voyageurs (adultes / enfants)\n"
    "   💶  Budget estimatif total\n"
    "   🎯  Centres d'intérêt (culture, plage, gastronomie, nature…)\n"
    "   🏨  Type d'hébergement (hôtel, Airbnb, camping…)\n"
    "   🚗  Mode de transport (avion, voiture, train…)\n"
    "   🍽️  Régimes alimentaires particuliers\n\n"
    "Décrivez votre voyage idéal et je vous poserai les questions manquantes.\n"
    "Une fois les attractions proposées, cliquez sur ✅ Valider les attractions pour générer le planning complet."
)

SYSTEM_STEP1 = """Tu es un assistant de planification de voyage expert.

ÉTAPE 1 — DÉCOUVERTE & PROPOSITION D'ATTRACTIONS :

Phase A — Collecte d'informations :
- Accueille chaleureusement l'utilisateur
- Identifie les informations présentes et manquantes : destination, dates, nombre de voyageurs, budget, centres d'intérêt, hébergement, transport, régimes alimentaires
- Pose les questions manquantes de façon concise (une ou deux à la fois maximum)

Phase B — Proposition d'attractions (quand tu as assez d'infos) :
- Propose une sélection d'attractions, activités et restaurants adaptés au profil du voyage
- Pour chaque attraction, précise : nom, type, durée estimée, prix indicatif
- Organise-les par catégorie : 🏛️ Culture & Patrimoine | 🏖️ Nature & Détente | 🍽️ Gastronomie | 🎭 Loisirs & Expériences
- Termine par : "Cliquez sur ✅ Valider les attractions pour que je génère le planning complet avec horaires, prix et liens de réservation."

🇫🇷 RÈGLE ABSOLUE : Réponds toujours en français.
⛔ FORMAT INTERDIT : Ne jamais écrire de JSON, de XML, de code ou de structures entre accolades/crochets dans tes réponses. Utilise uniquement du texte, des listes à puces et des tableaux."""

SYSTEM_STEP2 = """Tu es un expert en planification de voyage. Génère le planning complet et détaillé.

🇫🇷 RÈGLE ABSOLUE : 100% EN FRANÇAIS
⛔ INTERDIT : JSON, XML, accolades, crochets de code. Uniquement texte, listes et tableaux Markdown.

══════════════════════════════════════════════
RESPECTE EXACTEMENT CE FORMAT :
══════════════════════════════════════════════

VOYAGE À [DESTINATION EN MAJUSCULES]
[Date début] – [Date fin] | [N] personnes | [N] jours / [N] nuits

─── Infos voyage ──────────────────────────────
[emoji transport] [Transport] · 🏨 [Hébergement] · 👥 [N] personnes · [N] jours / [N] nuits
───────────────────────────────────────────────

[Pour chaque jour, répète ce bloc :]

[JOUR EN MAJUSCULES] [JJ/MM] – [Thème du jour]

• [emoji] [Nom activité] ([heure]) – durée [X]h[X]min
    → [Note pratique] — [✅ Confirmé / ❓ À réserver / 🔔 Pas encore ouvert]
    → 🔗 https://lien-reservation-officiel.com
• [emoji] [Activité suivante] ...

[Fin des jours]

═══════════════════════════════════════════════
TABLEAU RÉCAPITULATIF
═══════════════════════════════════════════════

| Activité | Jour | Heure | Durée | Prix/pers. | Total ([N] pers.) | Statut | Réservation |
|---|---|---|---|---|---|---|---|
| [nom] | [JJ/MM] | [heure] | [Xh] | [X]€ | [X]€ | ✅/❓/🔔 | 🔗 [lien] |
| **TOTAL estimé** | | | | | **[X]€** | | |

═══════════════════════════════════════════════
BUDGET ESTIMATIF
═══════════════════════════════════════════════

• Activités & visites : [X]€
• Hébergement : [X]€
• Transport : [X]€
• Repas : [X]€
• **TOTAL ESTIMÉ : [X]€ pour [N] personnes**

══════════════════════════════════════════════

EMOJIS PAR TYPE :
✈️ Vol · 🚂 Train · 🚗 Voiture · 🚍 Bus · 🚢 Bateau · 🏛️ Culture/Musée
🍽️ Restaurant · 🏨 Hôtel · 🎭 Spectacle · 🚶 Balade · 🌉 Vue · ⛪ Église · 🛒 Shopping

RÈGLES :
✓ Heures précises en 24h · Prix estimatifs par personne ET total
✓ 🔗 lien officiel pour chaque activité, hôtel et restaurant
✓ Ne jamais inventer un prix — écrire ⏳ si inconnu
✓ ✅ confirmé · ❓ à réserver · 🔔 réservation pas encore ouverte"""


class TravelPlannerGUI:
    """Modern GUI for Travel Planner Agent."""

    def __init__(self, root):
        self.root = root
        self.root.title("🌍 Agent de Planification de Voyage")
        self.root.geometry("1100x750")
        self.root.configure(bg="#FAFAFA")

        self.doc_generator = DocumentGenerator()
        self.conversation_history = []
        self.destination = "Travel Plan"
        self.engine = None
        self.model = None
        self.client = None
        self.is_loading = False
        self.loader_animation = 0
        self.planning_step = 1
        self.validate_btn = None
        self.step_label = None

        self.show_engine_selection()

    def show_engine_selection(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("🌍 Choisir votre moteur IA")
        dialog.geometry("480x280")
        dialog.configure(bg="#FAFAFA")
        dialog.transient(self.root)
        dialog.grab_set()

        self.root.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        dialog.geometry(f"+{rx + rw // 2 - 240}+{ry + rh // 2 - 140}")

        tk.Label(
            dialog, text="Sélectionnez votre moteur IA :",
            font=("Segoe UI", 14, "bold"), bg="#FAFAFA", fg="#1F2937"
        ).pack(pady=15)

        self.engine_var = tk.StringVar(value="anthropic")

        engines = [
            ("☁️  Anthropic Claude (cloud)",      "anthropic"),
            ("💻 Mistral via Ollama (local)",      "mistral"),
            ("☁️  Gemini Flash Preview (cloud)",   "gemini"),
        ]

        for label, value in engines:
            tk.Radiobutton(
                dialog, text=label,
                variable=self.engine_var, value=value,
                font=("Segoe UI", 11), bg="#FAFAFA", fg="#1F2937",
                selectcolor="#FFFFFF", activebackground="#FAFAFA",
                activeforeground="#166534"
            ).pack(anchor=tk.W, padx=50, pady=4)

        def start_app():
            choice = self.engine_var.get()
            engine_map = {
                "anthropic": ("anthropic", "claude-haiku-4-5-20251001"),
                "mistral":   ("ollama",    "mistral"),
                "gemini":    ("gemini",    "gemini-3-flash-preview"),
            }
            self.engine, self.model = engine_map[choice]
            try:
                self.client, _ = build_client(self.engine)
                dialog.destroy()
                self.setup_ui()
            except ValueError as e:
                messagebox.showerror("Erreur", f"❌ {str(e)}")

        tk.Button(
            dialog, text="Démarrer ✈️", command=start_app,
            font=("Segoe UI", 11, "bold"), bg="#2563EB", fg="#FFFFFF",
            padx=30, pady=10, relief=tk.FLAT, cursor="hand2",
            activebackground="#1D4ED8", activeforeground="#FFFFFF"
        ).pack(pady=15)

    def setup_ui(self):
        # Header — plus sombre que le fond pour créer de la profondeur
        header = tk.Frame(self.root, bg="#1E3A8A", height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        engine_label = f"{self.engine.upper()} — {self.model}"
        tk.Label(
            header,
            text=f"🌍  Agent de Planification de Voyage  |  {engine_label}",
            font=("Segoe UI", 14, "bold"), bg="#1E3A8A", fg="#FFFFFF"
        ).pack(pady=16)

        # Barre étape — bleu vif (étape 1) / vert (étape 2)
        self._step_bar = tk.Frame(self.root, bg="#2563EB", height=28)
        self._step_bar.pack(fill=tk.X)
        self._step_bar.pack_propagate(False)
        self.step_label = tk.Label(
            self._step_bar,
            text="📋  Étape 1 / 2 — Collecte d'infos & proposition d'attractions   ›   Étape 2 / 2 — Planning détaillé",
            font=("Segoe UI", 9, "bold"), bg="#2563EB", fg="#DBEAFE"
        )
        self.step_label.pack(pady=5)

        # Main container
        main = tk.Frame(self.root, bg="#FAFAFA")
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        BG = "#FAFAFA"

        # ── Boutons ronds (packés en BOTTOM avant le chat) ───────────
        btn_frame = tk.Frame(main, bg=BG)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(2, 4))

        def round_btn(emoji, label, color, hover_color, cmd, side=tk.LEFT, state=tk.NORMAL):
            size = 54
            wrap = tk.Frame(btn_frame, bg=BG)
            wrap.pack(side=side, padx=6, pady=2)
            c = tk.Canvas(wrap, width=size, height=size,
                          bg=BG, highlightthickness=0, cursor="hand2")
            c.pack()
            pad = 3
            fill_color = color if state == tk.NORMAL else "#E5E7EB"
            text_color = "white" if state == tk.NORMAL else "#9CA3AF"

            circle = c.create_oval(pad, pad, size - pad, size - pad,
                                    fill=fill_color, outline="")
            text_id = c.create_text(size // 2, size // 2, text=emoji,
                          font=("Segoe UI", 17), fill=text_color)
            label_obj = tk.Label(wrap, text=label, font=("Segoe UI", 7),
                     bg=BG, fg="#6B7280" if state == tk.NORMAL else "#9CA3AF")
            label_obj.pack()

            def on_enter(e):
                if state == tk.NORMAL:
                    c.itemconfig(circle, fill=hover_color)
            def on_leave(e):
                if state == tk.NORMAL:
                    c.itemconfig(circle, fill=color)
            def on_click(e):
                if state == tk.NORMAL:
                    cmd()

            c.bind("<Enter>",    on_enter)
            c.bind("<Leave>",    on_leave)
            c.bind("<Button-1>", on_click)
            return wrap, c, circle, text_id, label_obj

        # RIGHT-packed must be called first
        round_btn("✖",  "Quitter",     "#EF4444", "#DC2626", self.root.quit,       side=tk.RIGHT)
        round_btn("📋", "Formulaire",  "#2563EB", "#1D4ED8", self.show_info_form)
        round_btn("⬆",  "Importer",   "#2563EB", "#1D4ED8", self.upload_document)

        # New green color: #166534 (Forest Green) instead of #10B981
        self.save_btn_wrap, _, _, _, _ = round_btn("💾", "Sauvegarder", "#166534", "#14532D", self.save_documents)

        # New attractions validation round button
        self.validate_btn_wrap, self.v_canvas, self.v_circle, self.v_text, self.v_label = round_btn(
            "✅", "Valider", "#E5E7EB", "#166534", self.validate_and_continue, state=tk.DISABLED
        )

        round_btn("🔄", "Nouveau",     "#6B7280", "#4B5563", self.new_conversation)

        # ── Séparateur ───────────────────────────────────────────────
        tk.Frame(main, bg="#E5E7EB", height=1).pack(side=tk.BOTTOM, fill=tk.X)

        # ── Zone de saisie (packée en BOTTOM avant le chat) ──────────
        input_frame = tk.Frame(main, bg=BG)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 4))

        input_border = tk.Frame(input_frame, bg="#2563EB", padx=2, pady=2)
        input_border.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 6))

        self.input_field = tk.Entry(
            input_border, font=("Segoe UI", 11),
            bg="#FFFFFF", fg="#1F2937", insertbackground="#2563EB",
            relief=tk.FLAT, bd=6
        )
        self.input_field.pack(fill=tk.X)
        self.input_field.bind("<Return>", lambda e: self.send_message())

        tk.Button(
            input_frame, text="📤 Envoyer",
            command=self.send_message,
            font=("Segoe UI", 10, "bold"), relief=tk.FLAT, bd=0,
            padx=16, pady=8, cursor="hand2",
            bg="#F97316", fg="#FFFFFF",
            activebackground="#EA580C", activeforeground="#FFFFFF"
        ).pack(side=tk.LEFT)

        # ── Zone chat — remplit tout l'espace restant ─────────────────
        chat_container = tk.Frame(main, bg="#FFFFFF", relief=tk.FLAT, bd=1)
        chat_container.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        self.chat_display = scrolledtext.ScrolledText(
            chat_container, wrap=tk.WORD, font=("Segoe UI", 11),
            bg="#FFFFFF", fg="#1F2937", relief=tk.FLAT,
            selectbackground="#2563EB", selectforeground="#ffffff",
            spacing1=2, spacing3=2
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.chat_display.config(state=tk.DISABLED)

        self.chat_display.tag_config("vous",      foreground="#F97316", font=("Segoe UI", 11, "bold"), spacing1=6)
        self.chat_display.tag_config("assistant", foreground="#2563EB", font=("Segoe UI", 11, "bold"), spacing1=6)
        self.chat_display.tag_config("système",   foreground="#9CA3AF", font=("Segoe UI", 10),         spacing1=4)
        self.chat_display.tag_config("loading",   foreground="#F97316", font=("Segoe UI", 10, "italic"))

        # Welcome message with required info
        self.display_message("Système", f"👋 Bienvenue !\n\n{INFO_REQUISE}")

    def _parse_attractions(self):
        """Extract (category, name, description) tuples from the last assistant message."""
        last_text = ""
        for msg in reversed(self.conversation_history):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, str):
                    last_text = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            last_text = block.get("text", "")
                            break
                        elif hasattr(block, "type") and block.type == "text":
                            last_text = block.text
                            break
                if last_text:
                    break

        attractions = []
        current_category = "Général"
        category_keywords = {
            "Culture": "🏛️ Culture & Patrimoine",
            "Patrimoine": "🏛️ Culture & Patrimoine",
            "Nature": "🏖️ Nature & Détente",
            "Détente": "🏖️ Nature & Détente",
            "Gastronomie": "🍽️ Gastronomie",
            "Restaurant": "🍽️ Gastronomie",
            "Loisirs": "🎭 Loisirs & Expériences",
            "Expériences": "🎭 Loisirs & Expériences",
        }

        for line in last_text.split("\n"):
            stripped = line.strip()
            # Detect category headers
            for keyword, category in category_keywords.items():
                if keyword in stripped and len(stripped) < 60:
                    current_category = category
                    break
            # Detect bullet points
            if stripped and stripped[0] in ("•", "-", "*", "–", "▪", "◆", "✦"):
                raw = stripped.lstrip("•-*–▪◆✦ ").strip()
                name = raw
                description = ""
                # Split name from description at the first separator
                for sep in (" — ", " – ", " : ", " - (", " ("):
                    if sep in raw:
                        idx = raw.index(sep)
                        name = raw[:idx].strip()
                        description = raw[idx + len(sep):].strip().rstrip(")")
                        break
                # Truncate description to ~80 chars for display
                if len(description) > 85:
                    description = description[:82].rstrip() + "…"
                name = name.strip()
                if name and 4 <= len(name) <= 80:
                    attractions.append((current_category, name, description))

        return attractions

    def validate_and_continue(self):
        """Show attraction checkbox dialog, then trigger full detailed planning."""
        attractions = self._parse_attractions()

        if attractions:
            self._show_attraction_selection(attractions)
        else:
            # No attractions parsed — proceed directly
            self._trigger_planning(None)

    def _show_attraction_selection(self, attractions):
        """Display a dialog with checkboxes for each proposed attraction."""
        dialog = tk.Toplevel(self.root)
        dialog.title("✅ Sélectionner les attractions")
        dialog.configure(bg="#FAFAFA")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, True)

        self.root.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        dialog.geometry(f"560x520+{rx + rw // 2 - 280}+{ry + rh // 2 - 260}")

        tk.Label(
            dialog, text="Cochez les attractions qui vous intéressent :",
            font=("Segoe UI", 12, "bold"), bg="#FAFAFA", fg="#1F2937"
        ).pack(pady=(14, 4), padx=16, anchor=tk.W)
        tk.Label(
            dialog, text="Toutes les attractions sont cochées par défaut.",
            font=("Segoe UI", 9), bg="#FAFAFA", fg="#6B7280"
        ).pack(pady=(0, 8), padx=16, anchor=tk.W)

        # Scrollable frame (contained in its own frame so buttons stay below)
        scroll_container = tk.Frame(dialog, bg="#FFFFFF", relief=tk.FLAT, bd=1)
        scroll_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        canvas = tk.Canvas(scroll_container, bg="#FFFFFF", highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#FFFFFF")
        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Mouse-wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Group by category
        vars_by_name = {}
        current_cat = None
        for category, name, description in attractions:
            if category != current_cat:
                current_cat = category
                tk.Label(
                    scroll_frame, text=current_cat,
                    font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg="#2563EB"
                ).pack(anchor=tk.W, padx=10, pady=(12, 2))
            var = tk.BooleanVar(value=True)
            vars_by_name[name] = var
            row = tk.Frame(scroll_frame, bg="#FFFFFF")
            row.pack(anchor=tk.W, padx=20, pady=(2, 0), fill=tk.X)
            tk.Checkbutton(
                row, text=name, variable=var,
                font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg="#1F2937",
                selectcolor="#FFFFFF", activebackground="#FFFFFF",
                activeforeground="#166534", anchor=tk.W
            ).pack(anchor=tk.W)
            if description:
                tk.Label(
                    row, text=description,
                    font=("Segoe UI", 9), bg="#FFFFFF", fg="#6B7280",
                    anchor=tk.W, wraplength=460, justify=tk.LEFT
                ).pack(anchor=tk.W, padx=24, pady=(0, 3))

        # Select all / none buttons
        ctrl_frame = tk.Frame(dialog, bg="#FAFAFA")
        ctrl_frame.pack(fill=tk.X, padx=16, pady=(8, 0))

        def select_all():
            for v in vars_by_name.values():
                v.set(True)

        def select_none():
            for v in vars_by_name.values():
                v.set(False)

        tk.Button(
            ctrl_frame, text="Tout sélectionner", command=select_all,
            font=("Segoe UI", 9), bg="#F97316", fg="#FFFFFF",
            relief=tk.FLAT, padx=10, pady=4, cursor="hand2",
            activebackground="#EA580C", activeforeground="#FFFFFF"
        ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(
            ctrl_frame, text="Tout désélectionner", command=select_none,
            font=("Segoe UI", 9), bg="#E5E7EB", fg="#6B7280",
            relief=tk.FLAT, padx=10, pady=4, cursor="hand2",
            activebackground="#D1D5DB", activeforeground="#4B5563"
        ).pack(side=tk.LEFT)

        # Confirm / cancel buttons
        def confirm():
            canvas.unbind_all("<MouseWheel>")
            selected = [name for name, var in vars_by_name.items() if var.get()]
            dialog.destroy()
            self._trigger_planning(selected if selected else None)

        def cancel():
            canvas.unbind_all("<MouseWheel>")
            dialog.destroy()

        btn_row = tk.Frame(dialog, bg="#FAFAFA")
        btn_row.pack(pady=12)
        tk.Button(
            btn_row, text="Annuler", command=cancel,
            font=("Segoe UI", 10), bg="#E5E7EB", fg="#9CA3AF",
            relief=tk.FLAT, padx=16, pady=7, cursor="hand2",
            activebackground="#4B5563", activeforeground="#6B7280"
        ).pack(side=tk.LEFT, padx=8)
        tk.Button(
            btn_row, text="✅ Confirmer et générer le planning", command=confirm,
            font=("Segoe UI", 10, "bold"), bg="#166534", fg="#FFFFFF",
            relief=tk.FLAT, padx=16, pady=7, cursor="hand2",
            activebackground="#14532D", activeforeground="#FFFFFF"
        ).pack(side=tk.LEFT, padx=8)

    def _trigger_planning(self, selected_attractions):
        """Trigger step-2 planning with optional filtered attraction list."""
        self.planning_step = 2
        self.step_label.config(
            text="📅  Étape 2 / 2 — Génération du planning détaillé en cours…",
            bg="#166534", fg="#D1FAE5"
        )
        self._step_bar.config(bg="#166534")
        # Disable validate btn round
        self.v_canvas.itemconfig(self.v_circle, fill="#E5E7EB")
        self.v_canvas.itemconfig(self.v_text, fill="#9CA3AF")
        self.v_label.config(fg="#9CA3AF")

        if selected_attractions:
            attraction_list = ", ".join(selected_attractions)
            msg = (
                f"Je valide uniquement les attractions suivantes : {attraction_list}. "
                "Génère maintenant le planning complet jour par jour en incluant uniquement ces attractions, "
                "avec : les horaires précis, la durée de chaque activité, les prix estimatifs par personne, "
                "et le lien de réservation officiel (🔗) pour chaque attraction, hôtel et restaurant."
            )
        else:
            msg = (
                "Je valide ces attractions. "
                "Génère maintenant le planning complet jour par jour avec : "
                "les horaires précis, la durée de chaque activité, les prix estimatifs par personne, "
                "et le lien de réservation officiel (🔗) pour chaque attraction, hôtel et restaurant."
            )

        self.display_message("Vous", msg)
        self._show_loader()
        thread = threading.Thread(target=self._process_message, args=(msg,))
        thread.daemon = True
        thread.start()

    def display_message(self, sender: str, text: str):
        self.chat_display.config(state=tk.NORMAL)
        tag = sender.lower()
        self.chat_display.insert(tk.END, f"\n{sender} :\n", tag if tag in ("vous", "assistant") else "système")
        self.chat_display.insert(tk.END, f"{text}\n\n")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def send_message(self):
        user_input = self.input_field.get().strip()
        if not user_input or self.is_loading:
            return
        self.display_message("Vous", user_input)
        self.input_field.delete(0, tk.END)
        self._show_loader()
        thread = threading.Thread(target=self._process_message, args=(user_input,))
        thread.daemon = True
        thread.start()

    def _show_loader(self):
        self.is_loading = True
        self.loader_animation = 0
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, "⏳ Traitement en cours.\n", "loading")
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self._animate_loader()

    def _hide_loader(self):
        def hide():
            self.is_loading = False
            self.chat_display.config(state=tk.NORMAL)
            loader_start = self.chat_display.search("⏳ Traitement", tk.END, backwards=True)
            if loader_start:
                line_start = self.chat_display.index(f"{loader_start} linestart")
                line_end = self.chat_display.index(f"{loader_start} lineend+1c")
                self.chat_display.delete(line_start, line_end)
            self.chat_display.config(state=tk.DISABLED)
        self.root.after(0, hide)

    def _animate_loader(self):
        if not self.is_loading:
            return
        dots = [".", "..", "..."]
        dot = dots[self.loader_animation % 3]
        self.chat_display.config(state=tk.NORMAL)
        loader_pos = self.chat_display.search("⏳ Traitement", tk.END, backwards=True)
        if loader_pos:
            line_start = self.chat_display.index(f"{loader_pos} linestart")
            line_end = self.chat_display.index(f"{loader_pos} lineend")
            self.chat_display.delete(line_start, line_end)
            self.chat_display.insert(line_start, f"⏳ Traitement en cours{dot}", "loading")
        self.chat_display.config(state=tk.DISABLED)
        self.loader_animation += 1
        self.root.after(300, self._animate_loader)

    def _process_message(self, user_input: str):
        try:
            self.conversation_history.append({"role": "user", "content": user_input})

            while True:
                response_type, content, raw_response = call_llm(
                    self.client, self.engine, self.model,
                    self._get_system_prompt(), self._get_tools(),
                    self.conversation_history
                )

                if response_type == "text":
                    self.root.after(0, lambda t=content: self.display_message("Assistant", t))
                    self.conversation_history.append({"role": "assistant", "content": content})
                    self._hide_loader()
                    # Enable validate button after first AI response in step 1
                    if self.planning_step == 1:
                        self.root.after(0, self._enable_validate_btn)
                    break

                elif response_type == "tool_use":
                    self.conversation_history.append({"role": "assistant", "content": raw_response})
                    tool_results_list = []

                    for tool_call in content:
                        if self.engine == "anthropic":
                            tool_name = tool_call.name
                            tool_input = tool_call.input
                            tool_use_id = tool_call.id
                        else:
                            tool_name = tool_call.function.name
                            tool_input = json.loads(tool_call.function.arguments)
                            tool_use_id = tool_call.id

                        self.root.after(0, lambda n=tool_name: self.display_message(
                            "Système", f"🔧 Outil : {n}"
                        ))
                        result = self._process_tool_call(tool_name, tool_input)
                        tool_results_list.append(format_tool_result(self.engine, tool_use_id, result))

                    if self.engine == "anthropic":
                        self.conversation_history.append({"role": "user", "content": tool_results_list})
                    else:
                        for r in tool_results_list:
                            self.conversation_history.append(r)

        except Exception as e:
            self.root.after(0, lambda err=str(e): self.display_message("Erreur", f"❌ {err}"))
            self._hide_loader()

    def _enable_validate_btn(self):
        # Update round button to enabled state
        self.v_canvas.itemconfig(self.v_circle, fill="#166534")
        self.v_canvas.itemconfig(self.v_text, fill="white")
        self.v_label.config(fg="#6B7280")
        # I need to store the state or re-bind to make it actually work
        # The current round_btn doesn't easily support updating state after creation
        # but I'll fix the logic in setup_ui to handle it if I can, or just re-bind here.

        def on_enter(e):
            self.v_canvas.itemconfig(self.v_circle, fill="#14532D")
        def on_leave(e):
            self.v_canvas.itemconfig(self.v_circle, fill="#166534")
        def on_click(e):
            self.validate_and_continue()

        self.v_canvas.bind("<Enter>",    on_enter)
        self.v_canvas.bind("<Leave>",    on_leave)
        self.v_canvas.bind("<Button-1>", on_click)
        self.v_canvas.config(cursor="hand2")

    def _get_system_prompt(self) -> str:
        return SYSTEM_STEP1 if self.planning_step == 1 else SYSTEM_STEP2

    def _get_tools(self) -> list:
        return [
            {
                "name": "create_itinerary",
                "description": "Créer un itinéraire détaillé jour par jour",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "destination": {"type": "string"},
                        "duration_days": {"type": "integer"},
                        "days": {"type": "array", "items": {"type": "object"}},
                        "total_estimated_budget": {"type": "string"},
                    },
                    "required": ["destination", "duration_days", "days"],
                },
            },
            {
                "name": "list_attractions",
                "description": "Lister les principales attractions",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "destination": {"type": "string"},
                        "attractions": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["destination", "attractions"],
                },
            },
            {
                "name": "restaurant_recommendations",
                "description": "Recommander des restaurants",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "destination": {"type": "string"},
                        "budget_level": {"type": "string"},
                        "restaurants": {"type": "array"},
                    },
                    "required": ["destination", "budget_level", "restaurants"],
                },
            },
            {
                "name": "practical_travel_info",
                "description": "Fournir des infos pratiques de voyage",
                "input_schema": {
                    "type": "object",
                    "properties": {"destination": {"type": "string"}},
                    "required": ["destination"],
                },
            },
            {
                "name": "search_web",
                "description": "Rechercher des informations actuelles sur internet",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        ]

    def _process_tool_call(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "search_web":
            try:
                searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080/search")
                resp = requests.get(searxng_url, params={
                    "q": tool_input.get("query"),
                    "format": "json",
                    "language": "fr"
                }, timeout=10)
                raw = resp.json().get("results", [])[:5]
                # Return plain text so it doesn't pollute the conversation with JSON
                lines = []
                for r in raw:
                    title = r.get("title", "")
                    url = r.get("url", "")
                    snippet = r.get("content", "")
                    lines.append(f"- {title}\n  {url}\n  {snippet}")
                return "Résultats de recherche :\n" + "\n\n".join(lines) if lines else "Aucun résultat trouvé."
            except Exception as e:
                return f"Erreur de recherche : {e}"
        else:
            # For data tools (create_itinerary, list_attractions, etc.)
            # Just acknowledge — the real content is written by the AI as text
            return f"✅ Données enregistrées pour {tool_input.get('destination', tool_name)}. Continue avec le contenu textuel formaté."

    def show_info_form(self):
        """Open a form to fill in travel information (all fields optional)."""
        # Style crème pour les Combobox
        style = ttk.Style()
        style.configure("Cream.TCombobox",
                         fieldbackground="#FFF8F0", background="#FFF8F0",
                         foreground="#1F2937", selectbackground="#2563EB",
                         selectforeground="#FFF8F0")

        dialog = tk.Toplevel(self.root)
        dialog.title("📋 Informations voyage")
        dialog.geometry("520x580")
        dialog.configure(bg="#FAFAFA")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        self.root.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        dialog.geometry(f"+{rx + rw // 2 - 260}+{ry + rh // 2 - 290}")

        tk.Label(
            dialog, text="📋  Décrivez votre voyage",
            font=("Segoe UI", 13, "bold"), bg="#FAFAFA", fg="#1F2937"
        ).pack(pady=(14, 4))
        tk.Label(
            dialog, text="Tous les champs sont optionnels — laissez vide si vous ne savez pas encore.",
            font=("Segoe UI", 9), bg="#FAFAFA", fg="#6B7280"
        ).pack(pady=(0, 10))

        form = tk.Frame(dialog, bg="#FAFAFA")
        form.pack(fill=tk.BOTH, expand=True, padx=24)

        fields = {}

        def add_row(label, key, widget_type="entry", options=None, row=None):
            fr = tk.Frame(form, bg="#FAFAFA")
            fr.pack(fill=tk.X, pady=4)
            tk.Label(
                fr, text=label, font=("Segoe UI", 10), bg="#FAFAFA", fg="#1F2937",
                width=22, anchor=tk.W
            ).pack(side=tk.LEFT)
            if widget_type == "combo":
                var = tk.StringVar()
                w = ttk.Combobox(fr, textvariable=var, values=options or [],
                                 font=("Segoe UI", 10), width=26, state="normal",
                                 style="Cream.TCombobox")
                w.pack(side=tk.LEFT)
                fields[key] = var
            elif widget_type == "spinbox":
                var = tk.StringVar(value="")
                w = tk.Spinbox(fr, from_=1, to=20, textvariable=var,
                               font=("Segoe UI", 10), width=8,
                               bg="#FFF8F0", fg="#1F2937",
                               buttonbackground="#2563EB", insertbackground="#1F2937",
                               relief=tk.FLAT)
                w.delete(0, tk.END)
                w.pack(side=tk.LEFT)
                fields[key] = var
            else:
                var = tk.StringVar()
                w = tk.Entry(fr, textvariable=var, font=("Segoe UI", 10), width=28,
                             bg="#FFF8F0", fg="#1F2937",
                             insertbackground="#1F2937", relief=tk.FLAT, bd=3)
                w.pack(side=tk.LEFT)
                fields[key] = var

        add_row("📍 Destination(s)",       "destination")
        add_row("📅 Date de départ",        "depart",  "entry")
        add_row("📅 Date de retour",        "retour",  "entry")
        add_row("👥 Nombre de voyageurs",   "voyageurs", "spinbox")
        add_row("💶 Budget estimatif",      "budget",  "entry")
        add_row("🏨 Hébergement",           "hebergement", "combo",
                ["", "Hôtel", "Airbnb / Location", "Camping", "Auberge de jeunesse",
                 "Chambre d'hôtes", "Resort", "Sans préférence"])
        add_row("🚗 Transport",             "transport", "combo",
                ["", "Avion", "Voiture", "Train", "Bus / Car", "Bateau",
                 "Combiné", "Sans préférence"])
        add_row("🎯 Centres d'intérêt",     "interets", "entry")
        add_row("🍽️ Régimes alimentaires",  "regimes",  "entry")

        # ── buttons ──────────────────────────────────────────────
        btn_row = tk.Frame(dialog, bg="#FAFAFA")
        btn_row.pack(pady=14)

        def submit():
            parts = []
            dest = fields["destination"].get().strip()
            if dest:
                parts.append(f"Je souhaite planifier un voyage à {dest}.")
            depart = fields["depart"].get().strip()
            retour = fields["retour"].get().strip()
            if depart and retour:
                parts.append(f"Départ le {depart}, retour le {retour}.")
            elif depart:
                parts.append(f"Départ prévu le {depart}.")
            elif retour:
                parts.append(f"Retour prévu le {retour}.")
            voy = fields["voyageurs"].get().strip()
            if voy and voy != "0":
                parts.append(f"Nous serons {voy} voyageur(s).")
            budget = fields["budget"].get().strip()
            if budget:
                parts.append(f"Budget estimatif : {budget}.")
            heb = fields["hebergement"].get().strip()
            if heb:
                parts.append(f"Hébergement souhaité : {heb}.")
            trans = fields["transport"].get().strip()
            if trans:
                parts.append(f"Transport : {trans}.")
            interets = fields["interets"].get().strip()
            if interets:
                parts.append(f"Centres d'intérêt : {interets}.")
            regimes = fields["regimes"].get().strip()
            if regimes:
                parts.append(f"Régimes alimentaires : {regimes}.")

            if not parts:
                messagebox.showwarning(
                    "Formulaire vide",
                    "Veuillez renseigner au moins un champ.",
                    parent=dialog
                )
                return

            message = " ".join(parts)
            dialog.destroy()
            self.input_field.delete(0, tk.END)
            self.input_field.insert(0, message)
            self.send_message()

        tk.Button(
            btn_row, text="Annuler", command=dialog.destroy,
            font=("Segoe UI", 10), bg="#555566", fg="white",
            padx=18, pady=7, relief=tk.FLAT, cursor="hand2"
        ).pack(side=tk.LEFT, padx=8)

        tk.Button(
            btn_row, text="📤 Envoyer au planificateur", command=submit,
            font=("Segoe UI", 10, "bold"), bg="#2563EB", fg="#FFFFFF",
            padx=18, pady=7, relief=tk.FLAT, cursor="hand2",
            activebackground="#1D4ED8", activeforeground="#FFFFFF"
        ).pack(side=tk.LEFT, padx=8)

    def upload_document(self):
        file_path = filedialog.askopenfilename(
            title="Sélectionner un document",
            filetypes=[
                ("Tous", "*.*"),
                ("Word", "*.docx *.doc"),
                ("Texte", "*.txt *.md"),
                ("PDF", "*.pdf"),
            ]
        )
        if not file_path:
            return

        filename = os.path.basename(file_path)
        ext = filename.lower().rsplit(".", 1)[-1]
        self.display_message("Vous", f"📎 Document chargé : {filename}")

        try:
            content = ""
            if ext in ("docx", "doc"):
                from docx import Document
                doc = Document(file_path)
                content = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            elif ext == "pdf":
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    content = "\n".join(page.extract_text() or "" for page in pdf.pages)
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

            if not content.strip():
                self.display_message("Erreur", "❌ Document vide ou non lisible")
                return

            msg = f"J'ai chargé un document pour mon voyage. Analyse-le et aide-moi à planifier : {content[:800]}…"
            self.display_message("Vous", msg)
            self._show_loader()
            thread = threading.Thread(target=self._process_message, args=(msg,))
            thread.daemon = True
            thread.start()

        except Exception as e:
            self.display_message("Erreur", f"❌ {str(e)}")

    def save_documents(self):
        if not self.conversation_history:
            messagebox.showwarning("Aucun contenu", "Rien à sauvegarder !")
            return
        destination = simpledialog.askstring(
            "Sauvegarder", "Nom de la destination :", initialvalue=self.destination
        )
        if destination:
            self.destination = destination
            try:
                files = self.doc_generator.generate_all_formats(
                    self.conversation_history, destination, step=self.planning_step
                )
                doc_path = files['docx']
                messagebox.showinfo("Succès", f"✅ Sauvegardé !\n\n📄 {doc_path}")
                os.startfile(doc_path)
            except Exception as e:
                messagebox.showerror("Erreur", f"❌ {str(e)}")

    def new_conversation(self):
        if messagebox.askyesno("Nouvelle conversation", "Réinitialiser la conversation ?"):
            self.conversation_history = []
            self.planning_step = 1
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete(1.0, tk.END)
            self.chat_display.config(state=tk.DISABLED)
            self.step_label.config(
                text="📋  Étape 1 / 2 — Collecte d'infos & proposition d'attractions   ›   Étape 2 / 2 — Planning détaillé",
                bg="#2563EB", fg="#DBEAFE"
            )
            self._step_bar.config(bg="#2563EB")
            # Reset validate button to disabled
            self.v_canvas.itemconfig(self.v_circle, fill="#E5E7EB")
            self.v_canvas.itemconfig(self.v_text, fill="#9CA3AF")
            self.v_label.config(fg="#9CA3AF")
            self.v_canvas.unbind("<Enter>")
            self.v_canvas.unbind("<Leave>")
            self.v_canvas.unbind("<Button-1>")
            self.v_canvas.config(cursor="arrow")

            self.display_message("Système", f"✨ Nouvelle conversation.\n\n{INFO_REQUISE}")


def main():
    root = tk.Tk()
    app = TravelPlannerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
