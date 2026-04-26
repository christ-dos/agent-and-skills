#!/usr/bin/env python3
"""LLM Client abstraction — support for Anthropic, Ollama, and Gemini APIs."""

import os
import json
import anthropic
from openai import OpenAI


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
    else:  # ollama
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        return OpenAI(base_url=base_url, api_key="ollama"), "ollama"


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
