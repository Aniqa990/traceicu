"""
Thin wrapper around Groq's Chat API with llama-3.1-8b-instant.

No local model download, no torch/transformers install, nothing runs
on your machine -- every call is an HTTPS request to
https://api.groq.com, authenticated with your free GROQ_API_KEY.

IMPORTANT: this model is used ONLY to turn a natural-language question
into a structured JSON query plan (see app/ai/intents.py). It never sees
raw patient rows, never writes SQL, and never states a fact on its own
-- the answer sentence in app/ai/answer.py is built from a fixed
template applied to whatever DuckDB actually returned. If the model
misfires, the worst case is "unsupported intent -> abstain", never a
fabricated clinical fact. Since only the QUESTION TEXT is sent over the
network (never patient rows), this is safe even though the model call
is remote.

Setup (one-time):
    1. Create a free account at https://console.groq.com
    2. Create an API key at https://console.groq.com/keys
    3. Set it as an environment variable: GROQ_API_KEY=gsk_xxxxxxxxxxxx
    4. pip install groq
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from app.config import GROQ_API_KEY, LLM_MODEL_ID


class LLMConfigError(RuntimeError):
    """Raised when HF_TOKEN is missing -- fail loudly and early, not on first request."""


class LLMClient:
    def __init__(self, model_id: str = LLM_MODEL_ID,
                 api_key: str | None = GROQ_API_KEY):
        if not api_key:
            raise LLMConfigError(
                "GROQ_API_KEY is not set. Get a free API key at "
                "https://console.groq.com/keys and set it as an "
                "environment variable before starting the app, e.g.\n"
                "  Windows (PowerShell): $env:GROQ_API_KEY = \"gsk_xxxxxxxxxxxx\"\n"
                "  macOS/Linux:          export GROQ_API_KEY=gsk_xxxxxxxxxxxx"
            )

        self.model_id = model_id
        self.api_key = api_key
        self._client = None

    def _client_lazy(self):
        if self._client is not None:
            return self._client

        from groq import Groq

        self._client = Groq(api_key=self.api_key)
        return self._client

    # ------------------------------------------------------------------
    def generate(self, system: str, user: str, max_new_tokens: int = 200) -> str:
        client = self._client_lazy()

        completion = client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_new_tokens,
            temperature=0.0,
        )
        return completion.choices[0].message.content

    # ------------------------------------------------------------------
    @staticmethod
    def extract_json(text: str) -> dict | None:
        """Best-effort extraction of a single JSON object from model output."""
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """
    Singleton so the InferenceClient (and its connection pool) is created
    once per process, not per request. Raises LLMConfigError immediately
    if HF_TOKEN isn't set -- see app/main.py, which calls this eagerly at
    startup so a missing token fails fast instead of on the first /ask.
    """
    return LLMClient()