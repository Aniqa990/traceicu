"""
Thin wrapper around Hugging Face's hosted Inference Providers API.

No local model download, no torch/transformers install, nothing runs
on your machine -- every call is an HTTPS request to
https://router.huggingface.co, authenticated with your free HF_TOKEN.

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
    1. Create a free account at https://huggingface.co
    2. Create a token at https://huggingface.co/settings/tokens (Read scope)
    3. Set it as an environment variable: HF_TOKEN=hf_xxxxxxxxxxxx
    4. pip install -r requirements-ai.txt   (just huggingface_hub, nothing else)
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from app.config import HF_PROVIDER, HF_TOKEN, LLM_MODEL_ID


class LLMConfigError(RuntimeError):
    """Raised when HF_TOKEN is missing -- fail loudly and early, not on first request."""


class LLMClient:
    def __init__(self, model_id: str = LLM_MODEL_ID, provider: str | None = HF_PROVIDER,
                 token: str | None = HF_TOKEN):
        if not token:
            raise LLMConfigError(
                "HF_TOKEN is not set. Get a free token at "
                "https://huggingface.co/settings/tokens and set it as an "
                "environment variable before starting the app, e.g.\n"
                "  Windows (PowerShell): $env:HF_TOKEN = \"hf_xxxxxxxxxxxx\"\n"
                "  macOS/Linux:          export HF_TOKEN=hf_xxxxxxxxxxxx"
            )

        self.model_id = model_id
        self.provider = provider
        self.token = token
        self._client = None

    def _client_lazy(self):
        if self._client is not None:
            return self._client

        from huggingface_hub import InferenceClient

        kwargs = {"api_key": self.token}
        if self.provider:
            kwargs["provider"] = self.provider

        self._client = InferenceClient(**kwargs)
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
            temperature=0,
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