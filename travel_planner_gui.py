#!/usr/bin/env python3
"""Modern Travel Planner GUI - Multi-engine IA with web search via SearXNG."""

import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, simpledialog, ttk
import json
import re
import threading
import os
import sys
import requests
from pathlib import Path
from datetime import datetime
from document_generator import DocumentGenerator, extract_plan_from_conversation, fix_day_names
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
    "   🚗  Mode de transport (avion, train, voiture…) + ville de départ\n"
    "   🏨  Hébergement prévu (ou à rechercher)\n"
    "   🎯  Activités / visites souhaitées (même approximatif)\n"
    "   ✅  Activités déjà confirmées / réservées\n"
    "   🕐  Contraintes horaires particulières (vols, spectacles…)\n\n"
    "Décrivez votre voyage et je vous poserai les questions manquantes.\n"
    "Une fois le planning présenté, cliquez sur ✅ Valider pour lancer la recherche de prix et liens de réservation."
)

SYSTEM_STEP1 = """Tu es un assistant expert en planification de voyage.

ÉTAPE 1 — COLLECTE & ORGANISATION DU PLANNING :

Phase A — Collecte d'informations (si manquantes, pose en une seule fois) :
- Destination(s) et dates (du ... au ...)
- Nombre de personnes
- Mode de transport principal : ✈️ Avion / 🚂 Train / 🚗 Voiture / 🚢 Bateau / 🚌 Bus + ville de départ
- Liste des activités / visites souhaitées (même approximative)
- Activités déjà confirmées ou réservées
- Contraintes horaires (vols, trains, spectacles à heure fixe…)
- Hébergement prévu (ou type souhaité)

Phase B — Génération du planning (dès que tu as assez d'infos) :
- Répartis les activités sur les jours disponibles (logique géographique, 4-6 activités/jour max)
- MÉLANGE les types d'attractions chaque jour (ne pas faire un jour musée, un autre nature)
- Le 1er et le dernier jour sont souvent raccourcis par les transports
- Utilise le format EXACT ci-dessous SANS AUCUNE MODIFICATION
- Termine TOUJOURS par : "Cliquez sur ✅ Valider pour lancer la recherche de prix et de réservation."

⚠️ RÈGLE ABSOLUE : Tu DOIS respecter le template ci-dessous EXACTEMENT. Aucune déviation n'est tolérée.
Si tu dévies ne serait-ce qu'une ligne de ce format, la réponse est INVALIDE et sera rejetée.

🇫🇷 RÈGLE ABSOLUE : Réponds toujours en français.
⛔ FORMAT ABSOLUMENT INTERDIT : JSON, XML, accolades { }, crochets [ ], blocs de code ```. Uniquement texte brut, listes à puces (•) et tableaux Markdown (|col|col|). Toute réponse contenant du JSON est INVALIDE.

⚠️ EMOJI TRANSPORT OBLIGATOIRE — remplace [emoji_transport] par l'icône EXACTE du transport déclaré :
  🚗 voiture · ✈️ avion · 🚄 TGV/Intercités · 🚂 train régional · 🚢 bateau/ferry · 🚌 car/bus · 🚇 métro/RER · 🚲 vélo
  ⛔ NE JAMAIS mettre ✈️ si le transport est une voiture, un train ou autre chose qu'un avion.
  Exemple : si l'utilisateur voyage en voiture → utilise 🚗 partout où [emoji_transport] apparaît.

EMOJIS ACTIVITÉS : 🏛️ Culture/Musée · 🍽️ Restaurant · 🏨 Hôtel · 🎭 Spectacle · 🚶 Balade · 🌉 Vue · ⛪ Église · 🛒 Shopping

══════════════════════════════════════════════
FORMAT OBLIGATOIRE POUR LE PLANNING :
══════════════════════════════════════════════

VOYAGE À [DESTINATION EN MAJUSCULES]
[Date début] – [Date fin] | [N] personnes | [N] jours / [N] nuits

🗒️ PENSE-BÊTE — INFOS PRATIQUES
[emoji_transport] Transport aller : [date] · [heure départ] → [heure arrivée] · durée [X]h[X]min · [compagnie si connue]
[emoji_transport] Transport retour : [date] · [heure départ] → [heure arrivée] · durée [X]h[X]min
🏨 [Nom hôtel si connu, sinon "À confirmer"] — [adresse si connue]
   📅 Check-in : [date] à [heure ou ⏳] | Check-out : [date] à [heure ou ⏳]
   🔗 ⏳ (lien à rechercher à l'étape 2)
───────────────────────────────────────────────

─── Infos voyage ──────────────────────────────
[emoji_transport] [Transport] · 🏨 [Hébergement] · 👥 [N] personnes · [N] jours / [N] nuits
───────────────────────────────────────────────

[Pour chaque jour, répète ce bloc :]

[JOUR EN MAJUSCULES] [JJ/MM] – [Thème du jour]

• [emoji] [Nom activité] ([heure]) – durée [X]h[X]min
    → ✅ Confirmé / ❓ À réserver — [note pratique]
• [emoji] [Activité suivante] ...

[Fin des jours]

═══════════════════════════════════════════════
TABLEAU RÉCAPITULATIF
═══════════════════════════════════════════════

| Activité | Jour | Heure | Durée | Prix/pers. | Statut | Réservation |
|---|---|---|---|---|---|---|
| [nom] | [JJ/MM] | [heure] | [Xh] | ⏳ | ✅/❓ | ⏳ |
| **TOTAL estimé** | | | | **⏳ à calculer** | | |

══════════════════════════════════════════════

⚠️ RÈGLES STRICTES — NON NÉGOCIABLES :
1. Les sections VOYAGE À, 🗒️ PENSE-BÊTE, ─── Infos voyage ───, et TABLEAU sont EXACTEMENT formatées comme ci-dessus
2. Les jours sont au format : [JOUR MAJUSCULES] [JJ/MM] – [Thème]
3. Chaque activité : • [emoji] [Nom] ([heure]) – durée [X]h[X]min
4. Message de fin OBLIGATOIRE : "Cliquez sur ✅ Valider pour lancer la recherche de prix et de réservation."
5. Pas de JSON, XML, crochets [ ], ou blocs de code ```
6. Français UNIQUEMENT

"""

SYSTEM_STEP2 = """Tu es un expert en planification de voyage. Le planning validé t'a été fourni dans le message utilisateur.

🇫🇷 LANGUE : Réponds UNIQUEMENT en français.

⛔ FORMAT INTERDIT — ta réponse sera REJETÉE si elle contient :
  • du JSON ou des accolades { }
  • des crochets [ ] de tableau code
  • des blocs ``` de code
  Utilise UNIQUEMENT : texte, listes à puces (•) et tableaux Markdown (|col|col|).

══════════════════════════════════════════
PROCÉDURE OBLIGATOIRE (dans cet ordre)
══════════════════════════════════════════

ÉTAPE A — RECHERCHES (une par une, avant de réécrire) :
Pour chaque activité, hébergement et transport du planning :
  1. Lance search_web "[nom activité] [ville] prix billet 2026"
  2. Lance search_web "[nom activité] [ville] réservation en ligne tickets"
  3. Lance search_web "[nom activité] [ville] horaires ouverture"
Recherche aussi les coordonnées et liens de l'hébergement si ⏳.

ÉTAPE B — RÉÉCRITURE (après TOUTES les recherches) :
Réécris le planning COMPLET en conservant exactement la même structure, en remplaçant chaque ⏳ :

FORMAT D'ENRICHISSEMENT par activité :
• [emoji] [Nom activité] ([heure]) – durée [X]h
    → [✅ Disponible / 📅 À réserver tôt / ❓ À confirmer / 🔔 Pas encore ouvert]
    → 💶 Prix : [X €/pers.] — [X € pour N pers.]
    → 🔗 [lien officiel de réservation]
    → ℹ️ [note utile : horaires, fermetures, gratuités, conseils]

STATUTS :
  ✅ Disponible — lien de réservation trouvé, créneaux ouverts
  📅 À réserver tôt — disponible mais haute saison / attraction populaire
  ❓ À confirmer — infos incomplètes ou site inaccessible
  🔔 Pas encore ouvert — précise la date estimée d'ouverture (généralement 3–6 mois avant)

TABLEAU RÉCAPITULATIF ENRICHI :
| Activité | Jour | Heure | Durée | Prix/pers. | Total (N pers.) | Statut | Réservation |
|---|---|---|---|---|---|---|---|
| [nom] | [JJ/MM] | [heure] | [Xh] | [X €] | [X €] | ✅/📅/❓/🔔 | [lien] |
| **TOTAL estimé** | | | | **X € / pers.** | **X € au total** | | |

BUDGET ESTIMATIF (section finale) :
Ajoute une section "💶 BUDGET ESTIMATIF" avec la somme par catégorie (transport, hébergement, activités, repas) et le total général.

RÈGLES :
✓ Ne jamais inventer un prix — écrire "⏳ à vérifier" si non trouvé
✓ Mentionner gratuités (1er dimanche du mois, -18 ans, pass musée…)
✓ Tenir compte saisonnalité (horaires été/hiver, fermetures)
✓ Si activité 🔔 : écrire "Vérifier à partir du [date estimée]" """

# Support externe de templates : charge templates/step1.md / step1.txt et templates/step2.md / step2.txt si présents.
# Si le dossier templates/ n'existe pas, il sera créé et les fichiers step1.md/step2.md seront initialisés
# à partir des templates embarquées (SYSTEM_STEP1 / SYSTEM_STEP2) pour faciliter modifications ultérieures.

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
try:
    os.makedirs(templates_dir, exist_ok=True)
    step1_md = os.path.join(templates_dir, "step1.md")
    step2_md = os.path.join(templates_dir, "step2.md")
    step1_txt = os.path.join(templates_dir, "step1.txt")
    step2_txt = os.path.join(templates_dir, "step2.txt")

    def _load_or_create(path, default_text):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                # Ensure extraction rules are present
                if "DATE EXTRACTION" not in content and 'SYSTEM_EXTRACTION_RULES' in globals():
                    content = content + "\n\n" + SYSTEM_EXTRACTION_RULES
                    try:
                        with open(path, "w", encoding="utf-8") as fw:
                            fw.write(content)
                    except Exception:
                        pass
                return content
            else:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(default_text)
                except Exception:
                    pass
                return default_text
        except Exception:
            return default_text

    # Prefer .md; fallback to .txt; create .md if neither exist
    if os.path.exists(step1_md):
        SYSTEM_STEP1 = _load_or_create(step1_md, SYSTEM_STEP1)
    elif os.path.exists(step1_txt):
        SYSTEM_STEP1 = _load_or_create(step1_txt, SYSTEM_STEP1)
    else:
        SYSTEM_STEP1 = _load_or_create(step1_md, SYSTEM_STEP1)

    if os.path.exists(step2_md):
        SYSTEM_STEP2 = _load_or_create(step2_md, SYSTEM_STEP2)
    elif os.path.exists(step2_txt):
        SYSTEM_STEP2 = _load_or_create(step2_txt, SYSTEM_STEP2)
    else:
        SYSTEM_STEP2 = _load_or_create(step2_md, SYSTEM_STEP2)
except Exception:
    pass


# Extraction and usage rules appended to system prompts
SYSTEM_EXTRACTION_RULES = """
⚠️ IMPORTANT - FORM DATA EXTRACTION AND USAGE RULES:

1. DATE EXTRACTION: If the user provides travel dates (e.g., "Départ le 14/05/2026, retour le 17/05/2026"),
   EXTRACT and USE these dates EXACTLY as the planning start/end dates. NEVER generate alternative dates.

2. TRANSPORT MODE: If the user specifies transport mode (e.g., "Transport : Voiture"),
   USE this mode in the "Infos voyage" section. Replace placeholder text like "TBA", "TBC" with actual information when available.

3. NUMBER OF TRAVELERS: If the user specifies a number (e.g., "Nous serons 2 voyageur(s)"),
   USE this exact number. Do not change it.

4. ACCOMMODATION: If the user specifies accommodation (e.g., "Hébergement : Hôtel"),
   USE it and do not leave it as "À confirmer" unless explicitly unknown.

5. NO BOILERPLATE: Do not output placeholders such as "TBA", "TBC", or "TBD". Replace placeholders with user data or the phrase "à confirmer".

"""

# Append the extraction rules to both system prompts used by the GUI so the model must follow them
SYSTEM_STEP1 += "\n\n" + SYSTEM_EXTRACTION_RULES
SYSTEM_STEP2 += "\n\n" + SYSTEM_EXTRACTION_RULES


_CODE_BLOCK_RE = re.compile(r'```[\w]*\n?(.*?)```', re.S)
_JSON_BLOCK_RE  = re.compile(r'^\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*$', re.M)

def _strip_code_blocks(text: str) -> str:
    """Supprime les blocs ```code``` et les blocs JSON autonomes de la réponse."""
    # Supprime blocs ```...```
    text = _CODE_BLOCK_RE.sub(lambda m: m.group(1).strip(), text)
    return text.strip()


BLUE_50 = "#95A6CF"
BLUE_100 = "#7B95C5"
BLUE_200 = "#5C76AF"
BLUE_300 = "#4875B1"
BLUE_400 = "#325FA9"
BLUE_500 = "#0F52BA"  # Primary
BLUE_600 = "#0E4AA4"  # Primary dark
BLUE_700 = "#1C4293"  # Header / darker

PRIMARY = BLUE_300
PRIMARY_DARK = BLUE_500
PRIMARY_LIGHT = BLUE_50
HEADER_BG = BLUE_700

SECONDARY = BLUE_400  # Accent (remplace l'ancien vert)
FORM_FIELD_BG = "#FFFFFF"
BG = "#FAFAFA"
CARD_BG = "#FFFFFF"

# Utility: color helpers and UI constants
def hex_darken(hex_color, factor=0.85):
    hc = hex_color.lstrip('#')
    r = int(hc[0:2], 16)
    g = int(hc[2:4], 16)
    b = int(hc[4:6], 16)
    r = max(0, min(255, int(r * factor)))
    g = max(0, min(255, int(g * factor)))
    b = max(0, min(255, int(b * factor)))
    return f"#{r:02x}{g:02x}{b:02x}"

FIELD_BORDER = hex_darken(FORM_FIELD_BG, 0.92)  # subtle neutral border for fields
FIELD_BORDER_FOCUS = PRIMARY_DARK
BORDER_WIDTH = 1
ORANGE = "#FB8C00"
ORANGE_DARK = hex_darken(ORANGE, 0.78)
CLICK_EFFECT_DURATION = 160  # ms

class TravelPlannerGUI:
    """Modern GUI for Travel Planner Agent."""

    def _bind_tk_button_click_indicator(self):
        """Bind a global click indicator to all tk.Button widgets.

        When any tk.Button is pressed, its background briefly changes to PRIMARY_DARK
        to give immediate feedback. The binding is applied to the Button class so
        it affects buttons created later as well.
        """
        def on_button_click(event):
            btn = event.widget
            try:
                orig_bg = btn.cget('bg')
                btn.configure(bg=PRIMARY_DARK)
                btn.after(150, lambda: btn.configure(bg=orig_bg))
            except Exception:
                pass
        # Bind to the 'Button' class so all tk.Button instances show feedback
        # add='+' preserves existing bindings/behavior
        self.root.bind_class('Button', '<Button-1>', on_button_click, add='+')

    def show_toast(self, title: str, message: str, kind: str = 'info', duration: int = 3000):
        """Display a non-blocking toast notification (top-right of app)."""
        try:
            toast = tk.Toplevel(self.root)
            toast.overrideredirect(True)
            try:
                toast.attributes('-topmost', True)
            except Exception:
                pass
            kind_cfg = {
                'info':    {'bg': '#EBF3FF', 'border': PRIMARY,   'fg': '#1E3A5F', 'icon': 'ℹ️'},
                'success': {'bg': '#ECFDF5', 'border': '#059669', 'fg': '#065F46', 'icon': '✅'},
                'warning': {'bg': '#FFFBEB', 'border': '#D97706', 'fg': '#78350F', 'icon': '⚠️'},
                'error':   {'bg': '#FEF2F2', 'border': '#DC2626', 'fg': '#991B1B', 'icon': '❌'},
            }
            cfg = kind_cfg.get(kind, kind_cfg['info'])
            bg, border, fg = cfg['bg'], cfg['border'], cfg['fg']
            icon = cfg['icon']

            try:
                toast.attributes('-alpha', 0.93)
            except Exception:
                pass

            # Outer frame with white-ish bg
            outer = tk.Frame(toast, bg=bg, bd=0)
            outer.pack(fill=tk.BOTH, expand=True)

            # Colored left accent bar
            tk.Frame(outer, bg=border, width=4).pack(side=tk.LEFT, fill=tk.Y)

            inner = tk.Frame(outer, bg=bg, bd=0)
            inner.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 10))

            tk.Label(inner, text=f"{icon}  {title}", font=("Segoe UI", 10, 'bold'),
                     bg=bg, fg=border).pack(anchor=tk.W, pady=(8, 0))
            tk.Label(inner, text=message, font=("Segoe UI", 9),
                     bg=bg, fg=fg, wraplength=340, justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 8))

            # Position top-right of root window
            self.root.update_idletasks()
            w = 380
            h = toast.winfo_reqheight()
            x = self.root.winfo_rootx() + self.root.winfo_width() - w - 16
            y = self.root.winfo_rooty() + 16
            toast.geometry(f"{w}x{h}+{x}+{y}")
            # Auto destroy
            toast.after(duration, toast.destroy)
        except Exception:
            try:
                messagebox.showinfo(title, message)
            except Exception:
                pass

    def __init__(self, root):
        self.root = root
        self.root.title("🌍 Agent de Planification de Voyage")
        self.root.configure(bg="#FAFAFA")
        self.root.state('zoomed')
        # Bind global click indicator for tk.Button widgets (shows brief press feedback)
        self._bind_tk_button_click_indicator()

        self.doc_generator = DocumentGenerator()
        self.conversation_history = []
        self.destination = ""
        self.engine = None
        self.model = None
        self.client = None
        self.is_loading = False
        self.loader_animation = 0
        self.planning_step = 1
        self.validate_btn = None
        self.step_label = None

        self.show_engine_selection()

    def _get_md_path(self):
        # If destination is empty, try to infer from the conversation history before falling back
        dest = (self.destination or "").strip()
        if not dest:
            try:
                for msg in reversed(self.conversation_history):
                    text = msg.get("content", "")
                    if isinstance(text, list):
                        # flatten list blocks
                        for b in text:
                            if isinstance(b, dict):
                                t = b.get("text", "")
                            elif hasattr(b, "text"):
                                t = b.text
                            else:
                                t = ""
                            if t:
                                text = t
                                break
                    if isinstance(text, str):
                        maybe = self._infer_destination_from_text(text)
                        if maybe:
                            dest = maybe
                            break
            except Exception:
                pass
        if not dest:
            dest = "voyage"
        slug = self.doc_generator._slugify(dest)
        out_dir = Path("output") / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        # persist the selected destination for future saves
        self.destination = dest
        try:
            self.update_md_header(self.destination)
        except Exception:
            pass
        return out_dir / "planning.md"

        def update_md_header(self, new_dest: str):
            """Update existing planning.md header to use new destination."""
        try:
            md_path = self._get_md_path()
            if not md_path.exists():
                return
            text = md_path.read_text(encoding="utf-8")
            lines = text.splitlines()
            idx = None
            for i, ln in enumerate(lines):
                if ln.strip().upper().startswith("# VOYAGE"):
                    idx = i
                    break
            header_line = f"# VOYAGE À {new_dest.upper()}"
            if idx is None:
                new_text = header_line + "\n\n" + text
            else:
                lines[idx] = header_line
                new_text = "\n".join(lines) + "\n"
            md_path.write_text(new_text, encoding="utf-8")
        except Exception:
            pass

    def _infer_destination_from_text(self, text):
        """Attempt to extract a destination phrase from free text.

        Returns the destination string (e.g., 'Paris') or None if no match.
        """
        if not text or not isinstance(text, str):
            return None
        patterns = [
            r"planifier un voyage à\s+([A-Za-zÀ-ÖØ-öø-ÿ0-9'\- ]+)",
            r"voyage à\s+([A-Za-zÀ-ÖØ-öø-ÿ0-9'\- ]+)",
            r"destination\s*[:]\s*([A-Za-zÀ-ÖØ-öø-ÿ0-9'\- ]+)"
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                v = m.group(1).strip()
                v = v.rstrip(' .,:;!?')
                return v
        return None

    def _append_md(self, content: str, note: str = None):
        """Maintain a single planning.md per destination and update named sections.

        Sections maintained:
        - Attractions proposées
        - Attractions sélectionnées
        - Plan détaillé (assistant)
        """
        try:
            md_path = self._get_md_path()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            header = f"# VOYAGE À {self.destination.upper()}\n\n"

            # Initialize empty sections
            sections = {
                "Attractions proposées": "",
                "Attractions sélectionnées": "",
                "Plan détaillé": "",
                "Modifications utilisateur": "",
            }

            # If file exists, try to parse existing sections to preserve them
            if md_path.exists():
                try:
                    raw = md_path.read_text(encoding="utf-8")
                    # extract each known section using simple regex
                    for sec in list(sections.keys()):
                        m = re.search(rf"## {re.escape(sec)}\n(.*?)(?=\n## |\Z)", raw, flags=re.S)
                        if m:
                            sections[sec] = m.group(1).strip()
                except Exception:
                    pass

            # Map note -> section to update
            target = None
            if note == "Attractions proposées":
                target = "Attractions proposées"
            elif note == "Attractions sélectionnées":
                target = "Attractions sélectionnées"
            elif note == "Réponse assistant":
                target = "Plan détaillé"
            elif note in ("Modification utilisateur", "Utilisateur", "User"):
                target = "Modifications utilisateur"
            else:
                # default: update Plan détaillé
                target = "Plan détaillé"

            # Normalize incoming content
            to_write = content.strip() if content else ""
            # Pour "Plan détaillé", n'écrire que si le texte contient un vrai planning
            _has_planning = bool(re.search(r'VOYAGE\s+[AÀ]\s+', to_write, re.IGNORECASE))
            if to_write and (target != "Plan détaillé" or _has_planning):
                sections[target] = to_write

            # Compose the single-file markdown with updated timestamp and sections
            md_lines = [header, f"_Dernière mise à jour: {now}_", "\n"]
            for sec_name, sec_content in sections.items():
                md_lines.append(f"## {sec_name}")
                md_lines.append("")
                md_lines.append(sec_content)
                md_lines.append("")

            md_text = "\n".join(md_lines).strip() + "\n"
            md_path.write_text(md_text, encoding="utf-8")
        except Exception:
            pass

    def _make_rect_btn(self, parent, text, cmd,
                       width=110, height=34,
                       bg_color=None, hover_color=None, fg="#FFFFFF"):
        """Canvas-based rounded-rectangle button — same style as the Envoyer button."""
        if bg_color is None:
            bg_color = PRIMARY
        if hover_color is None:
            hover_color = PRIMARY_DARK
        r = 10
        try:
            parent_bg = parent.cget('bg')
        except Exception:
            parent_bg = BG
        wrap = tk.Frame(parent, bg=parent_bg, bd=0)
        c = tk.Canvas(wrap, width=width, height=height, bg=parent_bg,
                      highlightthickness=0, bd=0, relief=tk.FLAT,
                      cursor="hand2", takefocus=0)
        c.pack()

        def draw(color):
            c.delete("all")
            c.create_arc(0, 0, 2*r, 2*r, start=90, extent=90,
                         fill=color, outline="", style=tk.PIESLICE)
            c.create_arc(width-2*r, 0, width, 2*r, start=0, extent=90,
                         fill=color, outline="", style=tk.PIESLICE)
            c.create_arc(0, height-2*r, 2*r, height, start=180, extent=90,
                         fill=color, outline="", style=tk.PIESLICE)
            c.create_arc(width-2*r, height-2*r, width, height, start=270, extent=90,
                         fill=color, outline="", style=tk.PIESLICE)
            c.create_rectangle(r, 0, width-r, height, fill=color, outline="")
            c.create_rectangle(0, r, width, height-r, fill=color, outline="")
            c.create_text(width//2, height//2, text=text,
                          font=("Segoe UI", 10, "bold"), fill=fg)

        draw(bg_color)
        c._draw = draw; c._bg_color = bg_color; c._hov_color = hover_color

        def on_enter(e): draw(hover_color)
        def on_leave(e): draw(bg_color)
        def on_press(e):
            draw(hex_darken(bg_color, 0.70))
            c.after(CLICK_EFFECT_DURATION, lambda: draw(bg_color))
            c.after(30, cmd)

        c.bind("<Enter>", on_enter)
        c.bind("<Leave>", on_leave)
        c.bind("<Button-1>", on_press)
        return wrap, c

    def _open_draft_editor(self):
        """Open a modal editor for the single planning.md draft and provide an explicit Save button."""
        md_path = self._get_md_path()
        try:
            if not md_path.exists():
                header = f"# VOYAGE À {self.destination.upper()}\n\n"
                md_path.write_text(header + f"_Créé: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n\n", encoding='utf-8')
        except Exception:
            pass

        try:
            full_content = md_path.read_text(encoding='utf-8')
        except Exception:
            full_content = f"# VOYAGE À {self.destination.upper()}\n\n"

        # Extrait uniquement la section Plan détaillé pour l'affichage
        _plan_re = re.compile(r'## Plan détaillé\s*\n(.*?)(?=\n## |\Z)', re.S)
        _m = _plan_re.search(full_content)
        content = _m.group(1).strip() if _m else full_content

        dialog = tk.Toplevel(self.root)
        dialog.title("✏️ Éditer le brouillon")
        dialog.geometry("760x520")
        dialog.configure(bg="#FAFAFA")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.lift()
        try:
            dialog.attributes('-topmost', True)
            self.root.after(120, lambda: dialog.attributes('-topmost', False))
        except Exception:
            pass

        tk.Label(dialog, text=f"Brouillon : {md_path}", font=("Segoe UI", 9), bg="#FAFAFA", fg="#1F2937", anchor=tk.W).pack(fill=tk.X, padx=12, pady=(8,0))

        # Save function (uses editor content at call time)
        def do_save(event=None):
            try:
                new_plan = editor.get("1.0", tk.END).rstrip()
            except Exception:
                new_plan = content
            try:
                current = md_path.read_text(encoding='utf-8')
                if _plan_re.search(current):
                    updated = _plan_re.sub(
                        lambda mo: f"## Plan détaillé\n{new_plan}\n",
                        current, count=1
                    )
                else:
                    updated = current.rstrip() + f"\n\n## Plan détaillé\n{new_plan}\n"
                md_path.write_text(updated, encoding='utf-8')
                self.show_toast("Enregistré", f"Brouillon enregistré : {md_path}", kind="success")
                dialog.destroy()
            except Exception as e:
                self.show_toast("Erreur", f"Impossible d'enregistrer le brouillon : {e}", kind="error")

        # Bottom action row packed BEFORE editor so expand=True doesn't hide it
        btn_row = tk.Frame(dialog, bg="#FAFAFA")
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 14), padx=16)

        save_wrap, _ = self._make_rect_btn(
            btn_row, "💾 Enregistrer", do_save,
            width=130, height=34, bg_color=PRIMARY, hover_color=PRIMARY_DARK
        )
        save_wrap.pack(side=tk.RIGHT)

        close_wrap, _ = self._make_rect_btn(
            btn_row, "✖ Annuler", dialog.destroy,
            width=100, height=34, bg_color="#6B7280", hover_color="#4B5563"
        )
        close_wrap.pack(side=tk.RIGHT, padx=(0, 8))

        editor = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, font=("Segoe UI", 11), bg="#FFFFFF", fg="#1F2937")
        editor.pack(fill=tk.BOTH, expand=True, padx=12, pady=(8, 4))
        editor.insert("1.0", content)
        editor.focus_set()

        # Keyboard shortcut (Ctrl+S) bound to dialog and editor
        try:
            dialog.bind("<Control-s>", do_save)
            editor.bind("<Control-s>", do_save)
        except Exception:
            pass

        # Ensure dialog is closed cleanly
        def _on_close():
            try:
                dialog.unbind("<Control-s>")
                editor.unbind("<Control-s>")
            except Exception:
                pass
            dialog.destroy()
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

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

        self.engine_var = tk.StringVar(value="mistral")

        engines = [
            ("💻 Mistral via Ollama (local)", "mistral"),
            ("🧠 GLM 4.7 (glm-4.7-flash:latest)", "glm"),
            ("☁️  Gemma 4 (cloud)", "gemma"),
        ]

        radio_widgets = []
        for label, value in engines:
            rb = tk.Radiobutton(
                dialog, text=label,
                variable=self.engine_var, value=value,
                font=("Segoe UI", 11), bg=BG, fg="#6B7280",
                selectcolor="#FFFFFF", activebackground=BG,
                activeforeground=PRIMARY,
            )
            rb.pack(anchor=tk.W, padx=50, pady=4)
            radio_widgets.append((rb, value))

        def _refresh_radio(*_):
            selected = self.engine_var.get()
            for rb, val in radio_widgets:
                if val == selected:
                    rb.config(fg=PRIMARY, font=("Segoe UI", 11, "bold"), selectcolor=PRIMARY)
                else:
                    rb.config(fg="#6B7280", font=("Segoe UI", 11), selectcolor="#FFFFFF")

        self.engine_var.trace_add("write", _refresh_radio)
        _refresh_radio()

        def start_app():
            choice = self.engine_var.get()
            engine_map = {
                "mistral":   ("ollama",    "mistral"),
                "glm":       ("gemma",     "gemma4:26b"),
                "gemma":     ("gemma",     "gemma4:26b"),
            }
            self.engine, self.model = engine_map[choice]
            
            # Change button to show loading spinner
            start_btn.config(state=tk.DISABLED, text="⏳ Chargement...")
            dialog.update_idletasks()
            
            try:
                self.client, _ = build_client(self.engine)
            except ValueError as e:
                self.show_toast("Erreur", f"❌ {str(e)}", kind="error")
                start_btn.config(state=tk.NORMAL, text="Démarrer ✈️")
                return
            # Validate that the selected model exists on the server (local Ollama/GLM)
            try:
                from llm_client import ensure_model_available
                try:
                    actual_model = ensure_model_available(self.engine, self.model)
                    if actual_model != self.model:
                        self.show_toast("Info", f"Modèle '{self.model}' introuvable — utilisation de '{actual_model}' à la place.", kind="info")
                        self.model = actual_model
                except Exception as em:
                    self.show_toast("Info", f"Impossible de vérifier le modèle local: {em}. Démarrage quand même avec '{self.model}'.", kind="warning")
                    # continuer sans bloquer l'application
            except Exception:
                pass
            dialog.destroy()
            self.setup_ui()

        start_btn = tk.Button(
            dialog, text="Démarrer ✈️", command=start_app,
            font=("Segoe UI", 11, "bold"), bg=PRIMARY, fg="#FFFFFF",
            padx=30, pady=10, relief=tk.FLAT, cursor="hand2",
            activebackground=PRIMARY_DARK, activeforeground="#FFFFFF"
        )
        start_btn.pack(pady=15)

    def setup_ui(self):
        # Header — plus sombre que le fond pour créer de la profondeur
        header = tk.Frame(self.root, bg=HEADER_BG, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        engine_label = f"{self.engine.upper()} — {self.model}"
        tk.Label(
            header,
            text=f"🌍  Agent de Planification de Voyage  |  {engine_label}",
            font=("Segoe UI", 14, "bold"), bg=HEADER_BG, fg="#FFFFFF"
        ).pack(pady=16)

        # Barre étape — bleu vif (étape 1) / vert (étape 2)
        self._step_bar = tk.Frame(self.root, bg=PRIMARY, height=28)
        self._step_bar.pack(fill=tk.X)
        self._step_bar.pack_propagate(False)
        self.step_label = tk.Label(
            self._step_bar,
            text="📋  Étape 1 / 2 — Collecte d'infos & organisation du planning   ›   Étape 2 / 2 — Recherche prix & réservations",
            font=("Segoe UI", 9, "bold"), bg=PRIMARY, fg=PRIMARY_LIGHT
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
            from PIL import Image, ImageDraw, ImageFilter, ImageTk

            SIZE = 54          # logical canvas size
            SCALE = 4          # supersampling factor → 216×216 drawn, then shrunk
            S = SIZE * SCALE
            PAD = SCALE * 4    # margin inside the supersized image
            OFF = SCALE * 2    # shadow offset

            def _make_photo(circle_hex, text_color="#FFFFFF"):
                bg_h = BG.lstrip('#')
                bg_rgb = (int(bg_h[0:2], 16), int(bg_h[2:4], 16), int(bg_h[4:6], 16))
                img = Image.new('RGB', (S, S), bg_rgb)
                draw = ImageDraw.Draw(img)
                # soft shadow
                shadow_layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
                s_draw = ImageDraw.Draw(shadow_layer)
                s_draw.ellipse([PAD + OFF, PAD + OFF, S - PAD + OFF, S - PAD + OFF],
                               fill=(0, 0, 0, 60))
                shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(SCALE * 1.5))
                img.paste(Image.new('RGB', (S, S), bg_rgb), mask=Image.new('L', (S, S), 255))
                img = Image.new('RGB', (S, S), bg_rgb)
                img.paste(shadow_layer.convert('RGB'), mask=shadow_layer.split()[3])
                # main circle
                h = circle_hex.lstrip('#')
                rgb = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
                draw = ImageDraw.Draw(img)
                draw.ellipse([PAD, PAD, S - PAD, S - PAD], fill=rgb)
                img = img.resize((SIZE, SIZE), Image.LANCZOS)
                return ImageTk.PhotoImage(img)

            enabled = (state == tk.NORMAL)
            disabled_color = "#E5E7EB"

            # Pre-render the three states — kept alive on canvas object
            ph_normal   = _make_photo(color if enabled else disabled_color)
            ph_hover    = _make_photo(hover_color)
            ph_press    = _make_photo(hex_darken(color, 0.72))
            ph_disabled = _make_photo(disabled_color)

            wrap = tk.Frame(btn_frame, bg=BG)
            wrap.pack(side=side, padx=6, pady=2)
            c = tk.Canvas(wrap, width=SIZE, height=SIZE,
                          bg=BG, highlightthickness=0, cursor="hand2")
            c.pack()

            img_id  = c.create_image(0, 0, anchor=tk.NW,
                                     image=ph_normal if enabled else ph_disabled)
            text_id = c.create_text(SIZE // 2, SIZE // 2, text=emoji,
                                    font=("Segoe UI Emoji", 16),
                                    fill="white" if enabled else "#9CA3AF")
            label_obj = tk.Label(wrap, text=label, font=("Segoe UI", 7),
                                 bg=BG, fg="#6B7280" if enabled else "#9CA3AF")
            label_obj.pack()

            # Keep PhotoImage refs alive (prevents GC)
            c._photos = (ph_normal, ph_hover, ph_press, ph_disabled)
            c._enabled = enabled

            # All state access goes through c._photos to survive set_enabled calls
            # index: 0=normal, 1=hover, 2=press, 3=disabled
            c._photos = [ph_normal, ph_hover, ph_press, ph_disabled]

            def _show(idx, txt_color="white"):
                c.itemconfig(img_id, image=c._photos[idx])
                c.itemconfig(text_id, fill=txt_color)

            def _refresh():
                if c._enabled:
                    _show(0)
                else:
                    _show(3, "#9CA3AF")
                label_obj.config(fg="#6B7280" if c._enabled else "#9CA3AF")
                c.config(cursor="hand2" if c._enabled else "arrow")

            _refresh()

            def set_enabled(val: bool):
                c._enabled = val
                if val:
                    c._photos[0] = _make_photo(color)
                _refresh()

            c.set_enabled = set_enabled

            circle   = img_id    # compatibility shim
            text_idd = text_id

            def on_enter(e):
                if c._enabled: _show(1)
            def on_leave(e):
                if c._enabled: _show(0)
            def on_click(e):
                if c._enabled:
                    # Show pressed state with gray background
                    _show(2)
                    # Add a simple spinner animation
                    spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
                    spinner_idx = [0]
                    spinner_active = [True]
                    
                    def animate_spinner():
                        if spinner_active[0]:
                            c.itemconfig(text_id, text=spinner_chars[spinner_idx[0] % len(spinner_chars)])
                            spinner_idx[0] += 1
                            self.root.after(80, animate_spinner)
                    
                    def stop_spinner():
                        spinner_active[0] = False
                        _show(0)
                        c.itemconfig(text_id, text=emoji)
                    
                    animate_spinner()
                    self.root.after(40, cmd)
                    self.root.after(CLICK_EFFECT_DURATION + 400, stop_spinner)

            c.bind("<Enter>",    on_enter)
            c.bind("<Leave>",    on_leave)
            c.bind("<Button-1>", on_click)
            return wrap, c, circle, text_idd, label_obj

        # RIGHT-packed must be called first
        round_btn("✖",  "Quitter",     "#EF4444", "#DC2626", self.root.quit,       side=tk.RIGHT)
        round_btn("📋", "Formulaire",  PRIMARY, PRIMARY_DARK, self.show_info_form)
        round_btn("⬆",  "Importer",   PRIMARY, PRIMARY_DARK, self.upload_document)

        # Accent remanié : remplacer le vert par SECONDARY
        self.save_btn_wrap, _, _, _, _ = round_btn("💾", "Sauvegarder", SECONDARY, PRIMARY_DARK, self.save_documents)
        self.draft_btn_wrap, _, _, _, _ = round_btn("📝", "Brouillon", SECONDARY, PRIMARY_DARK, self._open_draft_editor)

        # New attractions validation round button
        self.validate_btn_wrap, self.v_canvas, self.v_circle, self.v_text, self.v_label = round_btn(
            "✅", "Valider", "#E5E7EB", SECONDARY, self.validate_and_continue, state=tk.DISABLED
        )

        round_btn("🔄", "Nouveau",     "#6B7280", "#4B5563", self.new_conversation)

        # ── Séparateur ───────────────────────────────────────────────
        tk.Frame(main, bg="#E5E7EB", height=1).pack(side=tk.BOTTOM, fill=tk.X)

        # ── Zone de saisie (packée en BOTTOM avant le chat) ──────────
        input_frame = tk.Frame(main, bg=BG)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 4))

        input_border = tk.Frame(input_frame, bg=FIELD_BORDER, padx=2, pady=2)
        input_border.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 6))

        self.input_field = tk.Entry(
            input_border, font=("Segoe UI", 11),
            bg="#FFFFFF", fg="#1F2937", insertbackground=PRIMARY,
            relief=tk.FLAT, bd=6
        )
        self.input_field.pack(fill=tk.X)
        self.input_field.bind("<Return>", lambda e: self.send_message())

        def rect_btn(text, cmd, width=96, height=36, bg_color=ORANGE_DARK, hover_color=ORANGE, fg="#FFFFFF"):
            wrap2, c2 = self._make_rect_btn(input_frame, text, cmd, width, height, bg_color, hover_color, fg)
            wrap2.pack(side=tk.LEFT)
            return wrap2, c2

        self.send_btn_wrap, self.send_btn_canvas = rect_btn("📤 Envoyer", self.send_message, width=96, height=36, bg_color=ORANGE_DARK, hover_color=ORANGE, fg="#FFFFFF")

        # ── Zone chat — remplit tout l'espace restant ─────────────────
        chat_container = tk.Frame(main, bg="#FFFFFF", relief=tk.FLAT, bd=1)
        chat_container.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        self.chat_display = scrolledtext.ScrolledText(
            chat_container, wrap=tk.WORD, font=("Segoe UI", 11),
            bg="#FFFFFF", fg="#1F2937", relief=tk.FLAT,
            selectbackground=PRIMARY, selectforeground="#ffffff",
            spacing1=2, spacing3=2
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.chat_display.config(state=tk.DISABLED)

        self.chat_display.tag_config("vous",      foreground=ORANGE, font=("Segoe UI", 11, "bold"), spacing1=6)
        self.chat_display.tag_config("assistant", foreground=PRIMARY, font=("Segoe UI", 11, "bold"), spacing1=6)
        self.chat_display.tag_config("système",   foreground="#9CA3AF", font=("Segoe UI", 10),         spacing1=4)
        self.chat_display.tag_config("loading",   foreground=ORANGE, font=("Segoe UI", 10, "italic"))

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

            raw = None
            # Bullet points classiques : •  -  –  ▪  ◆  ✦  et * seul (pas **)
            if stripped and stripped[0] in ("•", "–", "▪", "◆", "✦"):
                raw = stripped.lstrip("•–▪◆✦ ").strip()
            elif stripped.startswith("- ") or stripped.startswith("* "):
                raw = stripped[2:].strip()
            # Listes numérotées : "1. " ou "1) "
            elif re.match(r'^\d+[.)]\s', stripped):
                raw = re.sub(r'^\d+[.)]\s+', '', stripped).strip()
            # Markdown bold : "**Nom**" ou "**Nom** — description"
            elif stripped.startswith("**"):
                raw = re.sub(r'^\*\*', '', stripped).replace("**", " ").strip()

            if not raw:
                continue

            name = raw
            description = ""
            for sep in (" — ", " – ", " : ", " - (", " (", " | "):
                if sep in raw:
                    idx = raw.index(sep)
                    name = raw[:idx].strip()
                    description = raw[idx + len(sep):].strip().rstrip(")")
                    break
            if len(description) > 85:
                description = description[:82].rstrip() + "…"
            # Nettoyer le markdown résiduel dans le nom
            name = re.sub(r'\*+', '', name).strip()
            if name and 4 <= len(name) <= 80:
                attractions.append((current_category, name, description))

        return attractions

    def validate_and_continue(self):
        """Confirm the step-1 planning then trigger step-2 price/link enrichment."""
        if messagebox.askyesno(
            "✅ Valider le planning",
            "Le planning vous convient ?\n\n"
            "Cliquez sur Oui pour lancer la recherche\n"
            "de prix et liens de réservation pour chaque activité.",
            parent=self.root
        ):
            self._trigger_planning(None)

    def _show_attraction_selection(self, attractions):
        """Display a dialog with checkboxes for each proposed attraction."""
        # Save the latest assistant message into the draft markdown to persist proposed attractions
        try:
            last_text = extract_plan_from_conversation(self.conversation_history)
            if last_text and last_text.strip():
                self._append_md(last_text, note="Attractions proposées")
        except Exception:
            pass
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
                    font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg=PRIMARY
                ).pack(anchor=tk.W, padx=10, pady=(12, 2))
            var = tk.BooleanVar(value=True)
            vars_by_name[name] = var
            row = tk.Frame(scroll_frame, bg="#FFFFFF")
            row.pack(anchor=tk.W, padx=20, pady=(2, 0), fill=tk.X)
            tk.Checkbutton(
                row, text=name, variable=var,
                font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg="#1F2937",
                selectcolor="#FFFFFF", activebackground="#FFFFFF",
                activeforeground=SECONDARY, anchor=tk.W
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
            # update draft md with user selection
            try:
                sel_text = "\n".join([f"- {s}" for s in selected]) if selected else "Aucune attraction sélectionnée."
                self._append_md(sel_text, note="Attractions sélectionnées")
            except Exception:
                pass
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
            font=("Segoe UI", 10, "bold"), bg=SECONDARY, fg="#FFFFFF",
            relief=tk.FLAT, padx=16, pady=7, cursor="hand2",
            activebackground=PRIMARY_DARK, activeforeground="#FFFFFF"
        ).pack(side=tk.LEFT, padx=8)

    def _trigger_planning(self, selected_attractions):
        """Trigger step-2 planning with optional filtered attraction list."""
        # Try to infer a destination name from the conversation if not explicitly set
        try:
            dest_found = None
            for msg in reversed(self.conversation_history):
                if msg.get("role") not in ("user", "assistant"):
                    continue
                text = msg.get("content", "")
                if isinstance(text, list):
                    # flatten list blocks
                    for block in text:
                        if isinstance(block, dict):
                            t = block.get("text", "")
                        else:
                            t = getattr(block, 'text', '') if hasattr(block, 'text') else ''
                        if isinstance(t, str) and t:
                            text = t
                            break
                if not isinstance(text, str):
                    continue
                import re
                m = re.search(r"planifier un voyage à\s+([A-Za-zÀ-ÖØ-öø-ÿ0-9'\- ]+)", text, re.IGNORECASE)
                if not m:
                    m = re.search(r"voyage à\s+([A-Za-zÀ-ÖØ-öø-ÿ0-9'\- ]+)", text, re.IGNORECASE)
                if m:
                    dest_found = m.group(1).strip().strip('.').strip()
                    break
            if dest_found:
                self.destination = dest_found
                try:
                    self.update_md_header(self.destination)
                except Exception:
                    pass
        except Exception:
            pass

        self.planning_step = 2
        self.step_label.config(
            text="🔍  Étape 2 / 2 — Recherche de prix & liens de réservation en cours…",
            bg=SECONDARY, fg="#FFFFFF"
        )
        self._step_bar.config(bg=SECONDARY)
        # Disable validate btn round
        if hasattr(self, 'v_canvas') and hasattr(self.v_canvas, 'set_enabled'):
            try:
                self.v_canvas.set_enabled(False)
            except Exception:
                self.v_canvas.itemconfig(self.v_circle, fill="#E5E7EB")
                self.v_canvas.itemconfig(self.v_text, fill="#9CA3AF")
                self.v_label.config(fg="#9CA3AF")
        else:
            self.v_canvas.itemconfig(self.v_circle, fill="#E5E7EB")
            self.v_canvas.itemconfig(self.v_text, fill="#9CA3AF")
            self.v_label.config(fg="#9CA3AF")

        # Lire le planning sauvegardé dans planning.md pour le donner à l'IA
        planning_base = ""
        try:
            md_path = self._get_md_path()
            if md_path.exists():
                md_content = md_path.read_text(encoding="utf-8")
                m = re.search(r'## Plan détaillé\s*\n(.*?)(?=\n## |\Z)', md_content, re.S)
                if m:
                    planning_base = m.group(1).strip()
        except Exception:
            pass

        if planning_base:
            msg = (
                "✅ Le planning ci-dessous est validé. Enrichis-le avec des données réelles.\n\n"
                f"{planning_base}\n\n"
                "---\n"
                "Pour chaque activité, hébergement et transport du planning ci-dessus : utilise search_web "
                "pour trouver le prix réel, le lien officiel de réservation et les horaires. "
                "Si la recherche échoue, utilise tes connaissances pour estimer. "
                "Réécris ensuite le planning COMPLET en reprenant exactement la même structure, "
                "en remplaçant tous les ⏳ par les données réelles, en ajoutant les liens 🔗 "
                "et les statuts à jour, et en calculant le budget total estimé."
            )
        else:
            msg = (
                "✅ Le planning est validé. "
                "Pour chaque activité, hébergement et transport du planning : utilise search_web pour trouver "
                "le prix réel, le lien officiel de réservation et les horaires pour les dates du voyage. "
                "Une fois toutes les informations rassemblées, réécris le planning COMPLET en reprenant "
                "exactement la même structure jour par jour, en remplaçant tous les ⏳ par les données réelles, "
                "en ajoutant les liens 🔗 et les statuts à jour, et en calculant le budget total estimé."
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
        # Try to infer destination from the user's message
        try:
            maybe_dest = self._infer_destination_from_text(user_input)
            if maybe_dest:
                self.destination = maybe_dest
                try:
                    self.update_md_header(self.destination)
                except Exception:
                    pass
        except Exception:
            pass
        # Don't record simple commands like save/exit in the draft
        cmd_lower = user_input.lower().strip()
        if cmd_lower not in ("save", "exit", "quit"):
            try:
                # Record user modifications to the single planning.md (under Modifications utilisateur)
                self._append_md(user_input, note="Modification utilisateur")
            except Exception:
                pass

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
        c2 = getattr(self, 'send_btn_canvas', None)
        if c2 and hasattr(c2, '_draw'):
            c2._draw(c2._hov_color)
        self._animate_loader()

    def _hide_loader(self):
        def hide():
            self.is_loading = False
            c2 = getattr(self, 'send_btn_canvas', None)
            if c2 and hasattr(c2, '_draw'):
                c2._draw(c2._bg_color)
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

            MAX_ATTEMPTS = 2
            attempts = 0
            while True:
                response_type, content, raw_response = call_llm(
                    self.client, self.engine, self.model,
                    self._get_system_prompt(), self._get_tools(),
                    self.conversation_history
                )

                if response_type == "text":
                    if isinstance(content, str):
                        content = _strip_code_blocks(content)
                        content = fix_day_names(content)
                    # STEP 1: Enforce template
                    if self.planning_step == 1:
                        if not hasattr(self, '_looks_like_step1') or not hasattr(self, '_validate_step1'):
                            # fallback: always accept if helpers missing
                            pass
                        elif not self._looks_like_step1(content) or not self._validate_step1(content):
                            attempts += 1
                            if attempts < MAX_ATTEMPTS:
                                self.conversation_history.append({
                                    "role": "system",
                                    "content": (
                                        "USE STEP 1 TEMPLATE EXACTLY. "
                                        "Respecte STRICTEMENT le format du planning et la structure demandée. "
                                        "Relis la consigne et recommence."
                                    )
                                })
                                continue
                            else:
                                self.root.after(0, lambda t=content: self.display_message("Assistant", t))
                                self.conversation_history.append({"role": "assistant", "content": content})
                                self._hide_loader()
                                break
                    # STEP 2: Enforce TABLEAU RÉCAPITULATIF and BUDGET ESTIMATIF
                    elif self.planning_step == 2:
                        missing_tableau = "TABLEAU RÉCAPITULATIF" not in content and "TABLEAU RÉCAPITULATIF ENRICHI" not in content
                        missing_budget = "BUDGET ESTIMATIF" not in content and "💶 BUDGET ESTIMATIF" not in content
                        if missing_tableau or missing_budget:
                            attempts += 1
                            if attempts < MAX_ATTEMPTS:
                                self.conversation_history.append({
                                    "role": "system",
                                    "content": (
                                        "La réponse doit inclure le TABLEAU RÉCAPITULATIF et la section BUDGET ESTIMATIF EXACTEMENT comme demandé. "
                                        "Relis la consigne et recommence."
                                    )
                                })
                                continue
                            else:
                                self.root.after(0, lambda t=content: self.display_message("Assistant", t))
                                self.conversation_history.append({"role": "assistant", "content": content})
                                self._hide_loader()
                                break
                    self.root.after(0, lambda t=content: self.display_message("Assistant", t))
                    self.conversation_history.append({"role": "assistant", "content": content})
                    # Persist assistant response into draft markdown when relevant
                    try:
                        if isinstance(content, str) and len(content.strip()) > 30 and self.planning_step in (1, 2):
                            self._append_md(content, note="Réponse assistant")
                    except Exception:
                        pass
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
        # Enable the round validate button visually and functionally via canvas helper
        if hasattr(self, 'v_canvas') and hasattr(self.v_canvas, 'set_enabled'):
            try:
                self.v_canvas.set_enabled(True)
                # ensure click triggers validate_and_continue
                self.v_canvas.bind("<Button-1>", lambda e: self.validate_and_continue())
            except Exception:
                try:
                    self.v_canvas.itemconfig(self.v_circle, fill=SECONDARY)
                    self.v_canvas.itemconfig(self.v_text, fill="white")
                    self.v_label.config(fg="#6B7280")
                    self.v_canvas.bind("<Button-1>", lambda e: self.validate_and_continue())
                    self.v_canvas.config(cursor="hand2")
                except Exception:
                    pass

    def _get_system_prompt(self) -> str:
        """Return the system prompt for the current step, loading templates dynamically.

        Prefers templates/step1.md or step2.md if present, falls back to embedded SYSTEM_STEP1/SYSTEM_STEP2.
        Also prefixes the prompt with 'USE STEP X TEMPLATE EXACTLY' to enforce strict format.
        """
        try:
            templates_dir = os.path.join(os.path.dirname(__file__), "templates")
            step_md = os.path.join(templates_dir, "step1.md" if self.planning_step == 1 else "step2.md")
            step_txt = os.path.join(templates_dir, "step1.txt" if self.planning_step == 1 else "step2.txt")
            prompt = None
            if os.path.exists(step_md):
                with open(step_md, "r", encoding="utf-8") as f:
                    prompt = f.read()
            elif os.path.exists(step_txt):
                with open(step_txt, "r", encoding="utf-8") as f:
                    prompt = f.read()
            else:
                prompt = SYSTEM_STEP1 if self.planning_step == 1 else SYSTEM_STEP2
        except Exception:
            prompt = SYSTEM_STEP1 if self.planning_step == 1 else SYSTEM_STEP2

        # Append extraction rules if missing
        try:
            if "DATE EXTRACTION" not in prompt and 'SYSTEM_EXTRACTION_RULES' in globals():
                prompt = prompt + "\n\n" + SYSTEM_EXTRACTION_RULES
        except Exception:
            pass

        # Prefix enforcement header
        prefix = "USE STEP 1 TEMPLATE EXACTLY\n\n" if self.planning_step == 1 else "USE STEP 2 TEMPLATE EXACTLY\n\n"
        if not prompt.strip().startswith(prefix.strip()):
            prompt = prefix + prompt

        return prompt

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
        dialog = tk.Toplevel(self.root)
        dialog.title("📋 Informations voyage")
        dialog.geometry("450x1")  # Temporary small size
        dialog.configure(bg="#f5f5f5")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        self.root.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        dialog.geometry(f"+{rx + rw // 2 - 225}+{ry + rh // 2 - 300}")

        tk.Label(
            dialog, text="📋  Décrivez votre voyage",
            font=("Arial", 13, "bold"), bg="#f5f5f5", fg="#003366"
        ).pack(pady=(14, 4))
        tk.Label(
            dialog, text="Les champs avec * sont obligatoires.",
            font=("Arial", 9), bg="#f5f5f5", fg="#888888"
        ).pack(pady=(0, 10))

        form = tk.Frame(dialog, bg="#f5f5f5")
        form.pack(fill=tk.BOTH, expand=True, padx=16, pady=0)

        fields = {}
        required_fields = {"destination", "depart", "retour", "voyageurs", "transport"}
        
        # Icon colors mapping
        icon_colors = {
            "destination": "#FF6B6B",      # Red
            "depart": "#4ECDC4",           # Teal
            "retour": "#45B7D1",           # Blue
            "voyageurs": "#FFA07A",        # Salmon
            "budget": "#98D8C8",           # Green
            "hebergement": "#F7DC6F",      # Yellow
            "transport": "#BB8FCE",        # Purple
            "interets": "#F8B739",         # Orange
            "regimes": "#7FB069",          # Olive
        }

        def add_row(label, key, widget_type="entry", options=None, icon_color="#333333"):
            row_frame = tk.Frame(form, bg="#f5f5f5")
            row_frame.pack(fill=tk.X, pady=4)
            
            # Colored icon label
            icon = label.split()[0] if label else "•"
            icon_label = tk.Label(
                row_frame, text=icon, font=("Arial", 12, "bold"), bg="#f5f5f5", fg=icon_color,
                width=2, anchor=tk.W
            )
            icon_label.pack(side=tk.LEFT)
            
            # Field label with asterisk for required fields
            text_label = label.split(maxsplit=1)[1] if ' ' in label else ""
            label_frame = tk.Frame(row_frame, bg="#f5f5f5", width=130)
            label_frame.pack(side=tk.LEFT, fill=tk.Y, expand=False)
            label_frame.pack_propagate(False)
            
            tk.Label(
                label_frame, text=text_label, font=("Arial", 9), bg="#f5f5f5", fg="#333333",
                anchor=tk.W
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            # Red asterisk for required fields
            if key in required_fields:
                tk.Label(
                    label_frame, text="*", font=("Arial", 9, "bold"), bg="#f5f5f5", fg="#FF0000"
                ).pack(side=tk.LEFT, padx=(0, 4))
            
            if widget_type == "combo":
                var = tk.StringVar()
                w = ttk.Combobox(row_frame, textvariable=var, values=options or [],
                                 font=("Arial", 9), width=18, state="normal")
                w.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 0))
                fields[key] = var
            elif widget_type == "spinbox":
                var = tk.StringVar(value="1")
                w = tk.Spinbox(row_frame, from_=1, to=20, textvariable=var,
                               font=("Arial", 9), width=18)
                w.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 0))
                fields[key] = var
            elif widget_type == "datepicker":
                var = tk.StringVar()
                inner_fr = tk.Frame(row_frame, bg="white", relief=tk.GROOVE, bd=1)
                inner_fr.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 0))
                
                entry_w = tk.Entry(inner_fr, textvariable=var, font=("Arial", 9), 
                                   bg="white", relief=tk.FLAT, width=18)
                entry_w.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4, pady=3)
                
                # Calendar button
                cal_btn = tk.Label(inner_fr, text="📅", font=("Arial", 11), 
                                   bg="white", fg=icon_color, cursor="hand2", padx=4)
                cal_btn.pack(side=tk.RIGHT, padx=4, pady=3)
                
                cal_dropdown = [None]
                
                def _close_calendar():
                    if cal_dropdown[0] and cal_dropdown[0].winfo_exists():
                        cal_dropdown[0].destroy()
                        cal_dropdown[0] = None
                
                def _open_calendar(e=None):
                    _close_calendar()
                    try:
                        from tkcalendar import Calendar
                        
                        cal_dropdown[0] = tk.Toplevel(dialog)
                        cal_dropdown[0].wm_overrideredirect(True)
                        
                        x = inner_fr.winfo_rootx()
                        y = inner_fr.winfo_rooty() + inner_fr.winfo_height()
                        cal_dropdown[0].geometry(f"+{x}+{y}")
                        
                        cal = Calendar(
                            cal_dropdown[0],
                            selectmode='day',
                            locale='fr_FR',
                            date_pattern='dd/mm/yyyy',
                            background="#FFFFFF",
                            foreground="#333333",
                            selectbackground=icon_color,
                            selectforeground="#FFFFFF",
                            normalbackground="#FFFFFF",
                            normalforeground="#333333",
                            borderwidth=1,
                        )
                        cal.pack(padx=4, pady=4)
                        
                        def _on_date_selected(date_obj):
                            selected = cal.get_date()
                            var.set(selected)
                            _close_calendar()
                        
                        cal.bind('<<CalendarSelected>>', lambda e: _on_date_selected(e))
                    except ImportError:
                        pass
                
                cal_btn.bind('<Button-1>', _open_calendar)
                entry_w.bind('<Button-1>', _open_calendar)
                fields[key] = var
            else:
                var = tk.StringVar()
                w = tk.Entry(row_frame, textvariable=var, font=("Arial", 9), 
                             bg="white", relief=tk.GROOVE, width=18)
                w.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 0))
                fields[key] = var

        add_row("📍 Destination",        "destination", icon_color=icon_colors["destination"])
        add_row("📅 Départ",             "depart", "datepicker", icon_color=icon_colors["depart"])
        add_row("📅 Retour",             "retour", "datepicker", icon_color=icon_colors["retour"])
        add_row("👥 Voyageurs",          "voyageurs", "spinbox", icon_color=icon_colors["voyageurs"])
        add_row("💶 Budget",             "budget", icon_color=icon_colors["budget"])
        add_row("🏨 Hébergement",        "hebergement", "combo",
                ["", "Hôtel", "Airbnb", "Camping", "Auberge", "Chambre d'hôtes", "Resort"],
                icon_color=icon_colors["hebergement"])
        add_row("🚗 Transport",          "transport", "combo",
                ["", "Avion", "Voiture", "Train", "Bus", "Bateau", "Combiné"],
                icon_color=icon_colors["transport"])
        add_row("🎯 Centres d'intérêt", "interets", icon_color=icon_colors["interets"])
        add_row("🍽️ Régimes",           "regimes", icon_color=icon_colors["regimes"])

        # ── buttons ──────────────────────────────────────────────
        btn_row = tk.Frame(dialog, bg="#f5f5f5")
        btn_row.pack(pady=12)

        # Validation function
        def validate_fields():
            all_valid = True
            for field_key in required_fields:
                value = fields[field_key].get().strip()
                if not value:
                    all_valid = False
                    break
            
            # Enable/disable submit button
            if all_valid:
                submit_btn.config(state=tk.NORMAL, bg="#0066CC")
            else:
                submit_btn.config(state=tk.DISABLED, bg="#CCCCCC")

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
                parts.append(f"Départ le {depart}.")
            elif retour:
                parts.append(f"Retour le {retour}.")
            voy = fields["voyageurs"].get().strip()
            if voy and voy != "0":
                parts.append(f"Nous serons {voy} voyageur(s).")
            budget = fields["budget"].get().strip()
            if budget:
                parts.append(f"Budget estimatif : {budget}.")
            heb = fields["hebergement"].get().strip()
            if heb:
                parts.append(f"Hébergement : {heb}.")
            trans = fields["transport"].get().strip()
            if trans:
                parts.append(f"Transport : {trans}.")
            interets = fields["interets"].get().strip()
            if interets:
                parts.append(f"Centres d'intérêt : {interets}.")
            regimes = fields["regimes"].get().strip()
            if regimes:
                parts.append(f"Régimes : {regimes}.")

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
            font=("Arial", 9), bg="#aaaaaa", fg="white",
            padx=16, pady=6, relief=tk.FLAT, cursor="hand2"
        ).pack(side=tk.LEFT, padx=6)

        submit_btn = tk.Button(
            btn_row, text="📤 Envoyer", command=submit,
            font=("Arial", 9, "bold"), bg="#CCCCCC", fg="white",
            padx=16, pady=6, relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED
        )
        submit_btn.pack(side=tk.LEFT, padx=6)
        
        # Add traces to required fields
        for field_key in required_fields:
            if field_key in fields and hasattr(fields[field_key], 'trace'):
                fields[field_key].trace('w', lambda *args: validate_fields())
        
        # Initial validation
        validate_fields()
        
        # Auto-adjust window height to content
        dialog.update_idletasks()
        required_height = dialog.winfo_reqheight()
        dialog.geometry(f"450x{required_height}")
        
        # Reposition window to center
        self.root.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        dialog.geometry(f"+{rx + rw // 2 - 225}+{ry + rh // 2 - required_height // 2}")

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

            # Try to infer destination from document content
            try:
                maybe_dest = self._infer_destination_from_text(content)
                if maybe_dest:
                    self.destination = maybe_dest
                    try:
                        self.update_md_header(self.destination)
                    except Exception:
                        pass
                else:
                    # Ask user to name the destination folder for this document
                    try:
                        answer = simpledialog.askstring("Destination", "Nom de la destination pour ce document :", initialvalue=self.destination or "")
                        if answer:
                            self.destination = answer.strip()
                            try:
                                self.update_md_header(self.destination)
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                pass

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
            self.show_toast("Aucun contenu", "Rien à sauvegarder !", kind="warning")
            return
        destination = simpledialog.askstring(
            "Sauvegarder", "Nom de la destination :", initialvalue=self.destination
        )
        if not destination:
            return
        self.destination = destination
        try:
            self.update_md_header(self.destination)
        except Exception:
            pass

        def _has_step2_in_history():
            try:
                md_path = self._get_md_path()
                if md_path.exists():
                    text = md_path.read_text(encoding='utf-8')
                    if "TABLEAU RÉCAPITULATIF" in text or "BUDGET ESTIMATIF" in text:
                        return True
                for msg in reversed(self.conversation_history):
                    if msg.get("role") == "assistant":
                        c = msg.get("content", "")
                        if isinstance(c, str) and ("TABLEAU RÉCAPITULATIF" in c or "BUDGET ESTIMATIF" in c or "TABLEAU RÉCAPITULATIF" in c.upper()):
                            return True
                return False
            except Exception:
                return False

        # If still step 1 or no sign of step2, offer to run Step 2 before saving
        if self.planning_step == 1 or not _has_step2_in_history():
            res = messagebox.askyesnocancel(
                "Sauvegarder (Étape 2 recommandée)",
                "Le planning enrichi (Étape 2) n'a pas été généré.\n\n"
                "Oui → Lancer l'Étape 2 maintenant, puis sauvegarder automatiquement le document final.\n"
                "Non → Sauvegarder le planning actuel (Étape 1).\n"
                "Annuler → Abandonner.",
                parent=self.root
            )
            if res is None:
                return
            if res is True:
                # Launch Step 2 generation, then save when done
                try:
                    self._trigger_planning(None)
                except Exception:
                    pass

                def wait_and_save(dest):
                    import time
                    timeout = 180
                    waited = 0.0
                    while getattr(self, "is_loading", False) and waited < timeout:
                        time.sleep(0.5)
                        waited += 0.5
                    try:
                        files = self.doc_generator.generate_all_formats(self.conversation_history, dest, step=2)
                        doc_path = files.get('docx')
                        self.root.after(0, lambda: self.show_toast("Succès", f"✅ Sauvegardé !\n\n📄 {doc_path}", kind="success"))
                        if doc_path:
                            try:
                                os.startfile(doc_path)
                            except Exception:
                                pass
                    except Exception as e:
                        self.root.after(0, lambda: self.show_toast("Erreur", f"❌ {str(e)}", kind="error"))

                t = threading.Thread(target=wait_and_save, args=(destination,))
                t.daemon = True
                t.start()
                return
            # else: user chose No -> proceed to save current plan

        # Save current planning (use step 2 if already present, else step 1)
        try:
            step_to_use = 2 if (self.planning_step == 2 or _has_step2_in_history()) else self.planning_step
            files = self.doc_generator.generate_all_formats(self.conversation_history, destination, step=step_to_use)
            doc_path = files.get('docx')
            self.show_toast("Succès", f"✅ Sauvegardé !\n\n📄 {doc_path}", kind="success")
            if doc_path:
                try:
                    os.startfile(doc_path)
                except Exception:
                    pass
        except Exception as e:
            self.show_toast("Erreur", f"❌ {str(e)}", kind="error")

    def new_conversation(self):
        if messagebox.askyesno("Nouvelle conversation", "Réinitialiser la conversation ?"):
            self.conversation_history = []
            self.planning_step = 1
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete(1.0, tk.END)
            self.chat_display.config(state=tk.DISABLED)
            self.step_label.config(
                text="📋  Étape 1 / 2 — Collecte d'infos & organisation du planning   ›   Étape 2 / 2 — Recherche prix & réservations",
                bg=PRIMARY, fg=PRIMARY_LIGHT
            )
            self._step_bar.config(bg=PRIMARY)
            # Reset validate button to disabled
            if hasattr(self, 'v_canvas') and hasattr(self.v_canvas, 'set_enabled'):
                try:
                    self.v_canvas.set_enabled(False)
                    # remove any custom click binding
                    self.v_canvas.unbind("<Button-1>")
                except Exception:
                    self.v_canvas.itemconfig(self.v_circle, fill="#E5E7EB")
                    self.v_canvas.itemconfig(self.v_text, fill="#9CA3AF")
                    self.v_label.config(fg="#9CA3AF")
                    self.v_canvas.unbind("<Enter>")
                    self.v_canvas.unbind("<Leave>")
                    self.v_canvas.unbind("<Button-1>")
                    self.v_canvas.config(cursor="arrow")
            else:
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
