"""
Whitelisted intents + LLM-based intent extraction.

The model NEVER writes SQL and never picks a table. It returns a small
JSON object chosen from a fixed vocabulary; app/ai/retrieval.py turns
that into parameterized query templates. Anything outside the whitelist
is routed to "out_of_scope" or "unsupported" before it ever touches the
database -- this is the abstention/guardrail layer the track explicitly
asks for.
"""
from __future__ import annotations

from typing import Any

from app.ai.llm import get_llm_client

ALLOWED_INTENTS = {
    "timeline",              # what happened during the stay (uses cached Timeline)
    "first_measurement",     # earliest lab/chart value for a concept
    "last_measurement",      # latest lab/chart value for a concept
    "measurements_in_range", # labs/chart values within a time window
    "medications",           # eMAR medication administration events
    "procedures",            # procedures_icd events
    "transfers",             # ward/ICU transfer events
    "icu_stay_info",         # ICU stay admit/discharge details
    "event_count",           # "how many X events happened"
}

ALLOWED_DOMAINS = {
    "lab", "icu_observation", "medication", "procedure", "transfer", "admission",
}

# Cheap, zero-latency guardrail: catch obviously out-of-scope questions
# (diagnosis / treatment / clinical notes) before spending a model call.
OUT_OF_SCOPE_MARKERS = (
    "diagnos", "should i", "should the patient", "should this patient",
    "treat", "prognosis", "recommend", "clinical note", "physician wrote",
    "doctor said", "notes say", "what did the doctor", "what did the nurse",
)

SYSTEM_PROMPT = f"""You convert a user's question about ONE patient's structured hospital record into a JSON query plan. You do not answer the question yourself -- only decide how to look it up.

Return ONLY a JSON object, no prose, no markdown fences, with exactly these fields:
  intent: one of {sorted(ALLOWED_INTENTS)}
  domain: one of {sorted(ALLOWED_DOMAINS)}, or null
  concept: a short clinical term the user is asking about (e.g. "sodium", "heart rate", "furosemide"), or null
  time_scope: "stay" | "admission" | "all", or null
  start_time: ISO-8601 datetime string, or null
  end_time: ISO-8601 datetime string, or null

Rules:
- If the question asks for a diagnosis, a treatment recommendation, a prognosis, or anything from a clinical note (this dataset has NO free-text notes), set intent to "out_of_scope".
- If the question cannot be mapped to any listed intent, set intent to "unsupported".
- Never invent a concept, table, or fact. You are only classifying the question.

Examples:
Q: "When was the first sodium measurement during this ICU stay?"
A: {{"intent": "first_measurement", "domain": "lab", "concept": "sodium", "time_scope": "stay", "start_time": null, "end_time": null}}

Q: "What medications were given during the admission?"
A: {{"intent": "medications", "domain": "medication", "concept": null, "time_scope": "admission", "start_time": null, "end_time": null}}

Q: "Should this patient receive antibiotics?"
A: {{"intent": "out_of_scope", "domain": null, "concept": null, "time_scope": null, "start_time": null, "end_time": null}}

Q: "What did the physician write in the clinical note?"
A: {{"intent": "out_of_scope", "domain": null, "concept": null, "time_scope": null, "start_time": null, "end_time": null}}
"""


def quick_out_of_scope_check(question: str) -> bool:
    q = question.lower()
    return any(marker in q for marker in OUT_OF_SCOPE_MARKERS)


def extract_query_plan(question: str) -> dict[str, Any]:
    """
    Returns a dict with keys: intent, domain, concept, time_scope,
    start_time, end_time. Falls back to "unsupported" if the model
    output can't be parsed, and to "out_of_scope" immediately for
    obviously out-of-scope phrasing (saves a model call).
    """
    if quick_out_of_scope_check(question):
        return {
            "intent": "out_of_scope", "domain": None, "concept": None,
            "time_scope": None, "start_time": None, "end_time": None,
        }

    llm = get_llm_client()
    raw = llm.generate(SYSTEM_PROMPT, question, max_new_tokens=150)
    plan = llm.extract_json(raw)

    if plan is None:
        return {
            "intent": "unsupported", "domain": None, "concept": None,
            "time_scope": None, "start_time": None, "end_time": None,
        }

    intent = plan.get("intent")
    if intent not in ALLOWED_INTENTS and intent not in {"out_of_scope", "unsupported"}:
        plan["intent"] = "unsupported"

    return plan