#!/usr/bin/env python3
"""Travel Planner Agent - Multi-engine IA (Anthropic + Ollama) with web search via SearXNG."""

import json
import os
import sys
import requests
from pathlib import Path
from document_generator import DocumentGenerator, extract_plan_from_conversation
from llm_client import build_client, call_llm, format_tool_result

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

doc_generator = DocumentGenerator()

SKILL_PATH = os.getenv(
    "SKILL_PATH",
    r"C:\Users\Kikine\Desktop\coworkClaude\skills\voyage-planning\SKILL.md"
)


def load_skill(path: str) -> str:
    """Load skill instructions from SKILL.md, stripping YAML frontmatter."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Strip YAML frontmatter block (--- ... ---)
        if content.startswith('---'):
            end = content.find('---', 3)
            if end != -1:
                content = content[end + 3:].strip()
        return content
    except FileNotFoundError:
        print(f"⚠️  Skill introuvable : {path}")
        return ""


SYSTEM_PROMPT = load_skill(SKILL_PATH) or (
    "Tu es un expert en planification de voyage. "
    "Tu crées des plannings détaillés en français et génères des documents Word."
)

TOOLS = [
    {
        "name": "generate_planning_document",
        "description": (
            "Génère le document Word du planning de voyage. "
            "Appelle cet outil APRÈS avoir présenté le planning complet à l'utilisateur (étape 1), "
            "ou après avoir effectué les recherches web de prix et réservations (étape 2)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {
                    "type": "string",
                    "description": "Nom de la destination en minuscules sans espaces (ex: venise, paris-2025, tokyo-mars)"
                },
                "step": {
                    "type": "string",
                    "enum": ["1", "2"],
                    "description": "1 = planning initial avant validation, 2 = planning enrichi avec prix et réservations"
                }
            },
            "required": ["destination", "step"]
        }
    },
    {
        "name": "search_web",
        "description": (
            "Rechercher des informations actuelles sur internet : prix de billets, "
            "disponibilités, horaires d'ouverture, liens de réservation pour les activités du voyage. "
            "À utiliser uniquement à l'étape 2, après validation de l'utilisateur."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "La recherche à effectuer (en français)"
                }
            },
            "required": ["query"]
        }
    },
]


def process_tool_call(tool_name: str, tool_input: dict, conversation_history: list = None) -> str:
    """Process tool calls from the model and return results."""
    if tool_name == "generate_planning_document":
        destination = tool_input.get("destination", "voyage")
        step = int(tool_input.get("step", "1"))

        # Extract planning text from the latest assistant message in history
        planning_text = ""
        if conversation_history:
            for msg in reversed(conversation_history):
                if msg.get("role") == "assistant":
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if hasattr(block, 'text') and hasattr(block, 'type') and block.type == 'text':
                                planning_text = block.text
                                break
                            elif isinstance(block, dict) and block.get('type') == 'text':
                                planning_text = block.get('text', '')
                                break
                    elif isinstance(content, str):
                        planning_text = content
                    if planning_text:
                        break

        try:
            file_path = doc_generator.generate_planning_doc(planning_text, destination, step)
            return json.dumps({
                "status": "success",
                "message": f"Document Word créé : {file_path}",
                "file_path": file_path
            })
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Erreur génération document : {str(e)}"})

    elif tool_name == "search_web":
        try:
            searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080/search")
            response = requests.get(searxng_url, params={
                "q": tool_input.get("query"),
                "format": "json",
                "language": "fr"
            }, timeout=10)
            results = [
                {"title": r.get("title"), "url": r.get("url"), "summary": r.get("content")}
                for r in response.json().get("results", [])[:5]
            ]
            return json.dumps({
                "status": "success",
                "message": f"Résultats de recherche pour : {tool_input.get('query')}",
                "results": results
            })
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Erreur lors de la recherche : {str(e)}"})

    else:
        return json.dumps({"status": "error", "message": f"Outil inconnu : {tool_name}"})


def _save_documents(conversation_history: list, destination: str) -> None:
    """Save conversation as a Word document."""
    try:
        files = doc_generator.generate_all_formats(conversation_history, destination)
        print("\n" + "=" * 50)
        print("✅ Document sauvegardé !")
        print("=" * 50)
        print(f"📄 {files['docx']}")
        print("=" * 50 + "\n")
    except Exception as e:
        print(f"\n❌ Erreur lors de la sauvegarde : {e}\n")


def select_engine_and_model():
    """Interactive selection of LLM engine and model."""
    print("\n🌍 Bienvenue dans l'Agent de Planification de Voyage!")
    print("=" * 60)
    print("\n Choisissez votre moteur IA:\n")
    print("  1) Anthropic Claude Sonnet (cloud, clé API requise)")
    print("  2) Ollama - Mistral (local, ~4GB)")
    print("  3) Ollama - Dolphin Mixtral (local, ~7GB, plus puissant)")
    print("  4) Ollama - Neural Chat (local, ~4GB)")
    print()

    while True:
        choice = input("Sélection (1-4) : ").strip()
        if choice in ['1', '2', '3', '4']:
            break
        print("Choix invalide. Veuillez sélectionner 1-4.")

    models = {
        '1': ('anthropic', 'claude-sonnet-4-6'),
        '2': ('ollama', 'mistral'),
        '3': ('ollama', 'dolphin-mixtral'),
        '4': ('ollama', 'neural-chat'),
    }

    return models[choice]


def travel_planner_agent():
    """Main agent loop for the travel planner with multi-engine support."""
    engine, MODEL = select_engine_and_model()

    try:
        client, _ = build_client(engine)
    except ValueError as e:
        print(f"\n❌ Erreur : {e}")
        sys.exit(1)

    skill_loaded = Path(SKILL_PATH).exists()
    skill_status = f"✅ Skill chargé : {SKILL_PATH}" if skill_loaded else f"⚠️  Skill introuvable : {SKILL_PATH}"

    print(f"\n✅ Moteur : {engine.upper()} — {MODEL}")
    print(f"{skill_status}")
    print("=" * 60)
    print("\nJe suis votre assistant de planification de voyage.")
    print("Décrivez votre voyage et je créerai un planning Word complet.")
    print("\nCommandes :")
    print("  'save'  — Sauvegarder la conversation en document Word")
    print("  'exit'  — Terminer la conversation\n")

    conversation_history = []
    destination = "voyage"

    while True:
        user_input = input("Vous : ").strip()

        if user_input.lower() == 'exit':
            if conversation_history:
                save = input("\n💾 Sauvegarder le planning ? (oui/non) : ").strip().lower()
                if save in ['oui', 'o', 'yes', 'y']:
                    destination = input("📍 Nom de la destination (pour le fichier) : ").strip() or destination
                    _save_documents(conversation_history, destination)
            print("\n✈️  Bon voyage ! À bientôt !")
            break

        if user_input.lower() == 'save':
            if conversation_history:
                destination = input("📍 Nom de la destination (pour le fichier) : ").strip() or destination
                _save_documents(conversation_history, destination)
            else:
                print("Aucune conversation à sauvegarder.")
            continue

        if not user_input:
            continue

        conversation_history.append({"role": "user", "content": user_input})

        print("\n⏳ Traitement en cours...", end="", flush=True)
        while True:
            response_type, content, raw_response = call_llm(
                client, engine, MODEL, SYSTEM_PROMPT, TOOLS, conversation_history
            )
            print("\r" + " " * 30 + "\r", end="", flush=True)

            if response_type == "text":
                print(f"Assistant : {content}\n")
                conversation_history.append({"role": "assistant", "content": raw_response})
                break

            elif response_type == "tool_use":
                conversation_history.append({"role": "assistant", "content": raw_response})

                tool_results_list = []
                for tool_call in content:
                    if engine == "anthropic":
                        tool_name = tool_call.name
                        tool_input = tool_call.input
                        tool_use_id = tool_call.id
                    else:
                        tool_name = tool_call.function.name
                        tool_input = json.loads(tool_call.function.arguments)
                        tool_use_id = tool_call.id

                    print(f"\n🔧 Outil : {tool_name}")
                    result = process_tool_call(tool_name, tool_input, conversation_history)

                    # Print document path for immediate feedback
                    try:
                        result_data = json.loads(result)
                        if result_data.get("status") == "success" and "file_path" in result_data:
                            print(f"   📄 {result_data['file_path']}")
                    except Exception:
                        pass

                    tool_results_list.append(format_tool_result(engine, tool_use_id, result))

                if engine == "anthropic":
                    conversation_history.append({
                        "role": "user",
                        "content": tool_results_list
                    })
                else:
                    for result in tool_results_list:
                        conversation_history.append(result)

            else:
                print(f"Type de réponse inattendu : {response_type}")
                break


if __name__ == "__main__":
    travel_planner_agent()
