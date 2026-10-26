"""Anthropic Messages adapter for the retained QuantaAlpha APIBackend.

StepFun Step Plan uses this protocol; an OpenAI-compatible base URL must not
be substituted merely because the model is hosted by the same vendor.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse


class AnthropicMessagesTransport:
    def __init__(self):
        import anthropic
        key = os.getenv("AQR_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("AQR_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        if not key or not base_url:
            raise ValueError("Anthropic Messages requires an API binding and base URL")
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query:
            raise ValueError("Model base URL must be an HTTP(S) endpoint without embedded credentials")
        kwargs = {"base_url": base_url.rstrip("/"), "timeout": 120.0, "max_retries": 0}
        auth_mode = os.getenv("AQR_LLM_AUTH_MODE", "api_key")
        if auth_mode == "bearer":
            kwargs["auth_token"] = key
            kwargs["api_key"] = ""
            kwargs["default_headers"] = {"X-Api-Key": anthropic.omit}
        elif auth_mode == "api_key":
            kwargs["api_key"] = key
            kwargs["auth_token"] = ""
            kwargs["default_headers"] = {"Authorization": anthropic.omit}
        else:
            raise ValueError("AQR_LLM_AUTH_MODE must be api_key or bearer")
        self.client = anthropic.Anthropic(**kwargs)

    def complete(self, messages: list[dict], model: str, max_tokens: int, temperature: float, json_mode: bool):
        system = []
        conversation = []
        for message in messages:
            role, content = message.get("role"), message.get("content", "")
            if not isinstance(content, str):
                raise ValueError("This research transport expects text messages")
            if role in ("system", "developer"):
                system.append(content)
            elif role in ("user", "assistant"):
                if conversation and conversation[-1]["role"] == role:
                    conversation[-1]["content"] += "\n\n" + content
                else:
                    conversation.append({"role": role, "content": content})
            else:
                raise ValueError("Unsupported role in Anthropic research prompt")
        if json_mode:
            system.append("Return one valid JSON object only. Do not wrap it in Markdown fences.")
        if not conversation:
            raise ValueError("Research prompt requires a user message")
        response = self.client.messages.create(
            model=model, system="\n\n".join(system), messages=conversation,
            max_tokens=max_tokens, temperature=temperature,
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            raise ValueError("Model returned no text research proposal")
        finish = "length" if response.stop_reason == "max_tokens" else "stop"
        return text, finish
