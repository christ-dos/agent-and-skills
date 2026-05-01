#!/usr/bin/env python3
"""LLM Client abstraction — support for Anthropic, Ollama, and Gemini APIs."""

import os
import json
import anthropic
from openai import OpenAI
import requests


def build_client(engine: str):
    if engine == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY non définie dans l'environnement")
        return anthropic.Anthropic(api_key=api_key), "anthropic"
    elif engine == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY non définie dans l'environnement")
        return OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=api_key
        ), "gemini"
    elif engine == "gemma":
        # Gemma cloud mapping — allow GEMMA_BASE_URL or fallback to OLLAMA_BASE_URL for local proxies
        base_url = os.getenv("GEMMA_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
        api_key = os.getenv("GEMMA_API_KEY", "")
        return OpenAI(base_url=base_url, api_key=api_key), "gemma"
    elif engine == "glm":
        # GLM mapping — allow GLM_BASE_URL or fallback to OLLAMA_BASE_URL for local proxies
        base_url = os.getenv("GLM_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
        api_key = os.getenv("GLM_API_KEY", "")
        return OpenAI(base_url=base_url, api_key=api_key), "glm"
    else:  # ollama
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        return OpenAI(base_url=base_url, api_key="ollama"), "ollama"


# --- helper functions to detect models on local servers (Ollama/GLM) ---

def _base_for_engine(engine: str):
    if engine == "gemma":
        return os.getenv("GEMMA_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    if engine == "glm":
        return os.getenv("GLM_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    if engine == "ollama":
        return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    return None


def list_remote_models(base_url: str):
    endpoints = [
        f"{base_url.rstrip('/')}/models",
        f"{base_url.rstrip('/')}/v1/models",
        f"{base_url.rstrip('/')}/v1/engines",
        f"{base_url.rstrip('/')}/engines",
    ]
    for ep in endpoints:
        try:
            resp = requests.get(ep, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    names = []
                    for item in data:
                        if isinstance(item, dict) and 'name' in item:
                            names.append(item['name'])
                        elif isinstance(item, dict) and 'id' in item:
                            names.append(item['id'])
                        else:
                            names.append(str(item))
                    return names
                if isinstance(data, dict):
                    if 'data' in data and isinstance(data['data'], list):
                        return [d.get('id') for d in data['data'] if isinstance(d, dict) and d.get('id')]
                    if 'models' in data and isinstance(data['models'], list):
                        return [m.get('name') for m in data['models'] if isinstance(m, dict) and m.get('name')]
                    return list(data.keys())
        except Exception:
            continue
    return []


def ensure_model_available(engine: str, desired_model: str):
    base_url = _base_for_engine(engine)
    if not base_url:
        raise ValueError(f"Impossible de déterminer base_url pour engine '{engine}'")
    models = list_remote_models(base_url)
    if not models:
        raise ValueError(f"Aucun modèle trouvé sur le serveur '{base_url}'. Vérifiez que le service (Ollama) est accessible.")
    if desired_model in models:
        return desired_model
    prefix = desired_model.split(':')[0]
    candidates = [m for m in models if m.startswith(prefix) or prefix in m]
    if candidates:
        return candidates[0]
    if 'glm' in desired_model:
        c2 = [m for m in models if 'glm' in m]
        if c2:
            return c2[0]
    raise ValueError(f"Modèle '{desired_model}' non trouvé sur '{base_url}'. Modèles disponibles : {', '.join(models[:20])}")


def to_openai_tools(tools):
    """Convert Anthropic tool format to OpenAI/Gemini format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"]
            }
        }
        for t in tools
    ]


def call_llm(client, engine, model, system_prompt, tools, messages):
    if engine == "anthropic":
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            tools=tools,
            messages=messages
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, 'text')), "")
            return "text", text, response.content
        elif response.stop_reason == "tool_use":
            tool_calls = [b for b in response.content if b.type == "tool_use"]
            return "tool_use", tool_calls, response.content

    else:  # ollama or gemini — both OpenAI-compatible
        messages_with_system = [{"role": "system", "content": system_prompt}] + messages
        response = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            tools=to_openai_tools(tools),
            messages=messages_with_system
        )

        choice = response.choices[0]
        if choice.finish_reason == "stop":
            return "text", choice.message.content or "", choice.message
        elif choice.finish_reason == "tool_calls":
            return "tool_use", choice.message.tool_calls, choice.message


def format_tool_result(engine: str, tool_use_id: str, result: str):
    if engine == "anthropic":
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result
                }
            ]
        }
    else:  # ollama or gemini
        return {
            "role": "tool",
            "tool_call_id": tool_use_id,
            "content": result
        }
