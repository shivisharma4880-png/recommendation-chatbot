from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from openai import OpenAI

from src.prompts import PARSE_SYSTEM_PROMPT, REPLY_USER_TEMPLATE, SHOPPING_SYSTEM_PROMPT, format_products_block

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
XAI_BASE_URL = "https://api.x.ai/v1"
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))


class GrokClient:
    """LLM client. Prefers Groq (openai/gpt-oss-120b), then xAI Grok."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.provider = "none"
        self.model = model or ""
        self.api_key = None
        self._client: Optional[OpenAI] = None

        if os.getenv("DISABLE_LLM", "").lower() in {"1", "true", "yes"}:
            return

        groq_key = os.getenv("GROQ_API_KEY")
        xai_key = os.getenv("XAI_API_KEY")
        if api_key:
            self.api_key = api_key
            self.base_url = base_url or GROQ_BASE_URL
            self.provider = "groq" if "groq.com" in self.base_url else "custom"
            self.model = model or os.getenv("GROQ_MODEL", GROQ_DEFAULT_MODEL)
        elif groq_key:
            self.api_key = groq_key
            self.base_url = base_url or os.getenv("GROQ_BASE_URL", GROQ_BASE_URL)
            self.provider = "groq"
            self.model = model or os.getenv("GROQ_MODEL", GROQ_DEFAULT_MODEL)
        elif xai_key:
            self.api_key = xai_key
            self.base_url = base_url or os.getenv("XAI_BASE_URL", XAI_BASE_URL)
            self.provider = "xai"
            self.model = model or os.getenv("XAI_MODEL", "grok-4.7")
        else:
            return

        if self.api_key:
            # short timeout + a single retry: a slow/unavailable LLM must not freeze the chat
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=LLM_TIMEOUT_SECONDS, max_retries=1)

    @property
    def available(self) -> bool:
        return self._client is not None

    def _chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        if not self._client:
            raise RuntimeError("No LLM API key is configured (set GROQ_API_KEY)")
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": 1500,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if self.provider == "groq" and self.model.startswith("openai/gpt-oss"):
            kwargs["extra_body"] = {"reasoning_effort": "low"}
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception:
            # some models reject response_format / reasoning_effort: retry once without them
            kwargs.pop("extra_body", None)
            kwargs.pop("response_format", None)
            response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        # never fall back to ``message.reasoning``: it is the model's private chain of thought,
        # not something to show to a shopper.
        return (message.content or "").strip()

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                return json.loads(m.group(0))
            raise

    def parse_message(self, message: str, context: dict) -> dict[str, Any]:
        user = f"Previous context:\n{json.dumps(context, ensure_ascii=False)}\n\nShopper message:\n{message}"
        raw = self._chat(PARSE_SYSTEM_PROMPT, user, temperature=0.0, json_mode=True)
        try:
            parsed = self._extract_json(raw)
        except (json.JSONDecodeError, TypeError):
            raw = self._chat(PARSE_SYSTEM_PROMPT + "\nReturn strict JSON only.", user, temperature=0.0, json_mode=True)
            parsed = self._extract_json(raw)
        if not isinstance(parsed, dict):
            raise ValueError("LLM parse result is not a JSON object")
        return parsed

    def compose_reply(self, context: dict, products: list[dict], instruction: str) -> str:
        user = REPLY_USER_TEMPLATE.format(
            context=json.dumps(context, ensure_ascii=False, indent=2),
            products=format_products_block(products),
            instruction=instruction,
        )
        return self._chat(SHOPPING_SYSTEM_PROMPT, user, temperature=0.3)
