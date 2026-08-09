# """
# Whitelisted intents + LLM-based intent extraction.

# The model NEVER writes SQL and never picks a table. It returns a small
# JSON object chosen from a fixed vocabulary; app/ai/retrieval.py turns
# that into parameterized query templates. Anything outside the whitelist
# is routed to "out_of_scope" or "unsupported" before it ever touches the
# database -- this is the abstention/guardrail layer the track explicitly
# asks for.
# """
# from __future__ import annotations

# from typing import Any

# from app.ai.llm import get_llm_client

# ALLOWED_INTENTS = {
#     "timeline",              # what happened during the stay (uses cached Timeline)
#     "first_measurement",     # earliest lab/chart value for a concept
#     "last_measurement",      # latest lab/chart value for a concept
#     "measurements_in_range", # labs/chart values within a time window
#     "medications",           # eMAR medication administration events
#     "procedures",            # procedures_icd events
#     "transfers",             # ward/ICU transfer events
#     "icu_stay_info",         # ICU stay admit/discharge details
#     "event_count",           # "how many X events happened"
# }

# ALLOWED_DOMAINS = {
#     "lab", "icu_observation", "medication", "procedure", "transfer", "admission",
# }

# # Cheap, zero-latency guardrail: catch obviously out-of-scope questions
# # (diagnosis / treatment / clinical notes) before spending a model call.
# OUT_OF_SCOPE_MARKERS = (
#     "diagnos", "should i", "should the patient", "should this patient",
#     "treat", "prognosis", "recommend", "clinical note", "physician wrote",
#     "doctor said", "notes say", "what did the doctor", "what did the nurse",
# )

# SYSTEM_PROMPT = f"""You convert a user's question about ONE patient's structured hospital record into a JSON query plan. You do not answer the question yourself -- only decide how to look it up.

# Return ONLY a JSON object, no prose, no markdown fences, with exactly these fields:
#   intent: one of {sorted(ALLOWED_INTENTS)}
#   domain: one of {sorted(ALLOWED_DOMAINS)}, or null
#   concept: a short clinical term the user is asking about (e.g. "sodium", "heart rate", "furosemide"), or null
#   time_scope: "stay" | "admission" | "all", or null
#   start_time: ISO-8601 datetime string, or null
#   end_time: ISO-8601 datetime string, or null

# Rules:
# - If the question asks for a diagnosis, a treatment recommendation, a prognosis, or anything from a clinical note (this dataset has NO free-text notes), set intent to "out_of_scope".
# - If the question cannot be mapped to any listed intent, set intent to "unsupported".
# - Never invent a concept, table, or fact. You are only classifying the question.

# Examples:
# Q: "When was the first sodium measurement during this ICU stay?"
# A: {{"intent": "first_measurement", "domain": "lab", "concept": "sodium", "time_scope": "stay", "start_time": null, "end_time": null}}

# Q: "What medications were given during the admission?"
# A: {{"intent": "medications", "domain": "medication", "concept": null, "time_scope": "admission", "start_time": null, "end_time": null}}

# Q: "Should this patient receive antibiotics?"
# A: {{"intent": "out_of_scope", "domain": null, "concept": null, "time_scope": null, "start_time": null, "end_time": null}}

# Q: "What did the physician write in the clinical note?"
# A: {{"intent": "out_of_scope", "domain": null, "concept": null, "time_scope": null, "start_time": null, "end_time": null}}
# """


# def quick_out_of_scope_check(question: str) -> bool:
#     q = question.lower()
#     return any(marker in q for marker in OUT_OF_SCOPE_MARKERS)


# def extract_query_plan(question: str) -> dict[str, Any]:
#     """
#     Returns a dict with keys: intent, domain, concept, time_scope,
#     start_time, end_time. Falls back to "unsupported" if the model
#     output can't be parsed, and to "out_of_scope" immediately for
#     obviously out-of-scope phrasing (saves a model call).
#     """
#     if quick_out_of_scope_check(question):
#         return {
#             "intent": "out_of_scope", "domain": None, "concept": None,
#             "time_scope": None, "start_time": None, "end_time": None,
#         }

#     llm = get_llm_client()
#     raw = llm.generate(SYSTEM_PROMPT, question, max_new_tokens=150)
#     plan = llm.extract_json(raw)

#     if plan is None:
#         return {
#             "intent": "unsupported", "domain": None, "concept": None,
#             "time_scope": None, "start_time": None, "end_time": None,
#         }

#     intent = plan.get("intent")
#     if intent not in ALLOWED_INTENTS and intent not in {"out_of_scope", "unsupported"}:
#         plan["intent"] = "unsupported"

#     return plan

"""
Whitelisted intents + LLM-based intent extraction.

The model NEVER writes SQL and never picks a table. It returns a small
JSON object chosen from a fixed vocabulary; app/ai/retrieval.py turns
that into parameterized query templates.

Deterministic rules handle high-confidence query patterns before the LLM
is called. This is intentional: questions such as "how many laboratory
events" or "what was the ICU length of stay" should not depend on an LLM
guessing between similar intents.

Anything outside the whitelist is routed to "out_of_scope" or
"unsupported" before it ever touches the database.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.llm import get_llm_client


# ============================================================================
# Allowed vocabulary
# ============================================================================

ALLOWED_INTENTS = {
    "timeline",
    "first_measurement",
    "last_measurement",
    "measurements_in_range",
    "medications",
    "procedures",
    "transfers",
    "icu_stay_info",
    "event_count",
}

ALLOWED_DOMAINS = {
    "lab",
    "icu_observation",
    "medication",
    "procedure",
    "transfer",
    "admission",
}


# ============================================================================
# Cheap out-of-scope guardrail
# ============================================================================

OUT_OF_SCOPE_MARKERS = (
    "diagnos",
    "should i",
    "should the patient",
    "should this patient",
    "should we",
    "recommend",
    "recommendation",
    "prognosis",
    "clinical outcome",
    "likely outcome",
    "appropriate treatment",
    "best treatment",
    "what treatment",
    "which treatment",
    "what should the clinical team",
    "what should the doctor",
    "what should the clinician",
    "change the patient's treatment",
    "physician wrote",
    "physician document",
    "physician's narrative",
    "physician said",
    "doctor wrote",
    "doctor said",
    "clinical note",
    "clinical notes",
    "narrative note",
    "narrative notes",
    "nurse document",
    "nurse documented",
    "what did the nurse",
    "what did the doctor",
    "what did the physician",
    "what did the clinician write",
    "what did the clinician say",
    "patient report",
    "patient reported",
    "patient say",
    "patient said",
    "patient express",
    "patient expressed",
    "why did the clinician",
    "why did the doctor",
    "why did the physician",
    "why was the medication chosen",
)


def _empty_plan(intent: str) -> dict[str, Any]:
    """Return a normalized query-plan skeleton."""
    return {
        "intent": intent,
        "domain": None,
        "concept": None,
        "time_scope": None,
        "start_time": None,
        "end_time": None,
    }


def quick_out_of_scope_check(question: str) -> bool:
    """
    Catch obviously unsupported clinical reasoning / narrative questions
    without spending an LLM call.
    """
    q = " ".join(question.lower().split())

    return any(marker in q for marker in OUT_OF_SCOPE_MARKERS)


# ============================================================================
# Deterministic intent rules
# ============================================================================

def _deterministic_icu_stay_info(question: str) -> dict[str, Any] | None:
    """
    Detect questions whose answer comes directly from icustays.

    These should never be left to the LLM because "ICU stay length",
    "when did the ICU stay begin", etc. have an unambiguous structured
    source.
    """
    q = " ".join(question.lower().split())

    stay_patterns = (
        # length / LOS
        r"\b(length|duration|los)\b.*\b(icu stay|icu|stay)\b",
        r"\b(icu stay|stay)\b.*\b(length|duration|los)\b",
        r"\bhow many days\b.*\b(icu|stay)\b",
        r"\bhow long\b.*\b(icu|stay)\b",

        # start
        r"\bwhen did\b.*\b(icu stay|icu)\b.*\b(begin|start)\b",
        r"\bwhen did\b.*\b(icu stay|icu)\b.*\b(admit|admission)\b",
        r"\bwhen was\b.*\b(icu stay|icu)\b.*\b(started|begun)\b",

        # end / discharge
        r"\bwhen did\b.*\b(icu stay|icu)\b.*\b(end|finish)\b",
        r"\bwhen was\b.*\b(icu stay|icu)\b.*\b(discharge|discharged)\b",

        # care unit
        r"\b(first|initial)\b.*\bcare unit\b",
        r"\b(last|final)\b.*\bcare unit\b",
        r"\bwhich care unit\b.*\b(icu|stay)\b",
    )

    if any(re.search(pattern, q) for pattern in stay_patterns):
        return _empty_plan("icu_stay_info")

    return None


def _deterministic_event_count(question: str) -> dict[str, Any] | None:
    """
    Detect explicit event-count questions.

    This is deliberately stricter than simply looking for "how many".
    We only classify it here when the event type is clear.
    """
    q = " ".join(question.lower().split())

    if not re.search(
        r"\b(how many|number of|count of|count)\b",
        q,
    ):
        return None

    # ------------------------------------------------------------------------
    # Laboratory events
    # ------------------------------------------------------------------------

    if re.search(
        r"\b("
        r"laboratory|lab|lab events|laboratory events|"
        r"lab results|laboratory results|lab measurements|"
        r"laboratory measurements"
        r")\b",
        q,
    ):
        plan = _empty_plan("event_count")
        plan["domain"] = "lab"

        if "admission" in q:
            plan["time_scope"] = "admission"
        elif "icu stay" in q or "icu" in q:
            plan["time_scope"] = "stay"
        else:
            plan["time_scope"] = "all"

        return plan

    # ------------------------------------------------------------------------
    # Medication administration events
    # ------------------------------------------------------------------------

    if re.search(
        r"\b("
        r"medication events|medication administrations|"
        r"medication administration events|medications given|"
        r"medications administered|emar"
        r")\b",
        q,
    ):
        plan = _empty_plan("event_count")
        plan["domain"] = "medication"

        if "admission" in q:
            plan["time_scope"] = "admission"
        elif "icu stay" in q or "icu" in q:
            plan["time_scope"] = "stay"
        else:
            plan["time_scope"] = "all"

        return plan

    # ------------------------------------------------------------------------
    # Transfer events
    # ------------------------------------------------------------------------

    if re.search(
        r"\b("
        r"transfer records|transfers|transfer events|"
        r"transfer history"
        r")\b",
        q,
    ):
        plan = _empty_plan("event_count")
        plan["domain"] = "transfer"

        if "icu stay" in q or "icu" in q:
            plan["time_scope"] = "stay"
        elif "admission" in q:
            plan["time_scope"] = "admission"
        else:
            plan["time_scope"] = "all"

        return plan

    # ------------------------------------------------------------------------
    # Procedure events
    # ------------------------------------------------------------------------

    if re.search(
        r"\b("
        r"procedure events|procedures|procedures recorded|"
        r"procedures documented"
        r")\b",
        q,
    ):
        plan = _empty_plan("event_count")
        plan["domain"] = "procedure"
        plan["time_scope"] = "admission" if "admission" in q else "all"
        return plan

    return None


def _deterministic_measurement(question: str) -> dict[str, Any] | None:
    """
    Detect obvious first/last measurement questions.

    The LLM is still used for unusual concepts, but common lab names are
    extracted deterministically so that wording such as "first sodium" does
    not randomly become a different intent.
    """
    q = " ".join(question.lower().split())

    if not re.search(
        r"\b(first|earliest|initial|last|latest|most recent)\b",
        q,
    ):
        return None

    # Common structured lab concepts.
    concepts = (
        "sodium",
        "potassium",
        "chloride",
        "bicarbonate",
        "co2",
        "creatinine",
        "urea",
        "bun",
        "glucose",
        "hemoglobin",
        "hematocrit",
        "platelet",
        "platelets",
        "white blood cell",
        "wbc",
        "calcium",
        "magnesium",
        "phosphate",
        "bilirubin",
        "albumin",
        "lactate",
        "troponin",
        "inr",
        "pt",
        "ptt",
        "ast",
        "alt",
    )

    concept = next(
        (name for name in concepts if re.search(rf"\b{re.escape(name)}\b", q)),
        None,
    )

    if concept is None:
        return None

    if re.search(r"\b(first|earliest|initial)\b", q):
        intent = "first_measurement"
    else:
        intent = "last_measurement"

    plan = _empty_plan(intent)
    plan["domain"] = "lab"
    plan["concept"] = concept

    if "admission" in q:
        plan["time_scope"] = "admission"
    elif "icu stay" in q or "during this icu" in q:
        plan["time_scope"] = "stay"
    else:
        plan["time_scope"] = "all"

    return plan


# ============================================================================
# LLM prompt
# ============================================================================

SYSTEM_PROMPT = f"""
You convert a user's question about ONE patient's structured hospital
record into a JSON query plan.

You do not answer the question yourself.

You do not write SQL.

You do not select database tables.

Return ONLY a JSON object with exactly these fields:

intent: one of {sorted(ALLOWED_INTENTS)} or "out_of_scope" or "unsupported"
domain: one of {sorted(ALLOWED_DOMAINS)} or null
concept: a short clinical term the user is asking about, or null
time_scope: "stay" | "admission" | "all" | null
start_time: ISO-8601 datetime string or null
end_time: ISO-8601 datetime string or null

IMPORTANT INTENT RULES:

1. ICU STAY INFORMATION

Questions about:
- when the ICU stay began
- when the ICU stay ended
- ICU admission/discharge
- ICU length of stay
- ICU duration
- LOS
- first/last ICU care unit

MUST use:

intent = "icu_stay_info"
domain = "admission"

Do NOT use "event_count".

Example:
Q: "What was the recorded length of this ICU stay in days?"
A:
{{
  "intent": "icu_stay_info",
  "domain": "admission",
  "concept": null,
  "time_scope": "stay",
  "start_time": null,
  "end_time": null
}}

2. EVENT COUNTS

Use "event_count" ONLY when the user explicitly asks HOW MANY
events/records/results are present.

Examples:

Q: "How many laboratory events are recorded during this ICU stay?"
A:
{{
  "intent": "event_count",
  "domain": "lab",
  "concept": null,
  "time_scope": "stay",
  "start_time": null,
  "end_time": null
}}

Q: "How many medication administration events are recorded during this ICU stay?"
A:
{{
  "intent": "event_count",
  "domain": "medication",
  "concept": null,
  "time_scope": "stay",
  "start_time": null,
  "end_time": null
}}

Q: "How many transfer records are documented for this admission?"
A:
{{
  "intent": "event_count",
  "domain": "transfer",
  "concept": null,
  "time_scope": "admission",
  "start_time": null,
  "end_time": null
}}

3. LAB MEASUREMENTS

Use:
- "first_measurement" for first/earliest/initial value
- "last_measurement" for last/latest/most recent value
- "measurements_in_range" for values within an explicit time window

For a laboratory concept, use:
domain = "lab"

Example:
Q: "What was the first recorded sodium measurement during this ICU stay?"
A:
{{
  "intent": "first_measurement",
  "domain": "lab",
  "concept": "sodium",
  "time_scope": "stay",
  "start_time": null,
  "end_time": null
}}

4. MEDICATIONS

Questions asking which medications were administered should use:
intent = "medications"
domain = "medication"

5. PROCEDURES

Questions asking about ICD-coded procedures should use:
intent = "procedures"
domain = "procedure"

6. TRANSFERS

Questions asking for transfer history should use:
intent = "transfers"
domain = "transfer"

7. OUT OF SCOPE

The dataset has NO free-text clinical notes.

Return "out_of_scope" for:
- physician/nurse narrative
- what the patient said/reported
- diagnosis
- prognosis
- clinical outcome
- treatment recommendations
- whether treatment was appropriate
- what treatment should have been given
- what clinicians should have done
- clinical reasoning that requires information not represented by
  the supported structured query types

8. UNSUPPORTED

Return "unsupported" when the question is not out of scope but
cannot be mapped to one of the supported intents.

Never invent a concept, table, value, or fact.
"""


# ============================================================================
# Query-plan normalization
# ============================================================================

def _normalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize and validate an LLM-produced plan.

    This provides a second safety layer after the deterministic rules.
    """
    normalized = _empty_plan("unsupported")

    intent = plan.get("intent")
    domain = plan.get("domain")
    concept = plan.get("concept")
    time_scope = plan.get("time_scope")
    start_time = plan.get("start_time")
    end_time = plan.get("end_time")

    allowed_intents = ALLOWED_INTENTS | {"out_of_scope", "unsupported"}

    if intent not in allowed_intents:
        return normalized

    normalized["intent"] = intent

    if domain in ALLOWED_DOMAINS:
        normalized["domain"] = domain

    if isinstance(concept, str):
        concept = concept.strip()
        normalized["concept"] = concept or None

    if time_scope in {"stay", "admission", "all"}:
        normalized["time_scope"] = time_scope

    normalized["start_time"] = start_time
    normalized["end_time"] = end_time

    # ------------------------------------------------------------------------
    # Intent-specific normalization
    # ------------------------------------------------------------------------

    if intent == "icu_stay_info":
        normalized["domain"] = "admission"
        normalized["concept"] = None

    elif intent == "event_count":
        # Event count without a valid domain is unsafe.
        if normalized["domain"] not in {
            "lab",
            "medication",
            "procedure",
            "transfer",
            "icu_observation",
        }:
            return _empty_plan("unsupported")

    elif intent in {
        "first_measurement",
        "last_measurement",
        "measurements_in_range",
    }:
        # Measurements need a domain.
        if normalized["domain"] not in {"lab", "icu_observation"}:
            return _empty_plan("unsupported")

    elif intent == "medications":
        normalized["domain"] = "medication"

    elif intent == "procedures":
        normalized["domain"] = "procedure"

    elif intent == "transfers":
        normalized["domain"] = "transfer"

    return normalized


# ============================================================================
# Public API
# ============================================================================

def extract_query_plan(question: str) -> dict[str, Any]:
    """
    Convert a user question into a safe structured query plan.

    Resolution order:

        1. obvious out-of-scope guardrail
        2. deterministic ICU-stay detection
        3. deterministic event-count detection
        4. deterministic common-lab detection
        5. LLM classification
        6. strict plan normalization

    The deterministic layers are important because these query classes
    have unambiguous meanings and should not vary between LLM calls.
    """
    if not question or not question.strip():
        return _empty_plan("unsupported")

    # ------------------------------------------------------------------------
    # 1. Out-of-scope guardrail
    # ------------------------------------------------------------------------

    if quick_out_of_scope_check(question):
        return _empty_plan("out_of_scope")

    # ------------------------------------------------------------------------
    # 2. ICU stay information
    # ------------------------------------------------------------------------

    plan = _deterministic_icu_stay_info(question)
    if plan is not None:
        return plan

    # ------------------------------------------------------------------------
    # 3. Explicit event counts
    # ------------------------------------------------------------------------

    plan = _deterministic_event_count(question)
    if plan is not None:
        return plan

    # ------------------------------------------------------------------------
    # 4. Common first/last laboratory measurements
    # ------------------------------------------------------------------------

    plan = _deterministic_measurement(question)
    if plan is not None:
        return plan

    # ------------------------------------------------------------------------
    # 5. LLM classification
    # ------------------------------------------------------------------------

    llm = get_llm_client()

    raw = llm.generate(
        SYSTEM_PROMPT,
        question,
        max_new_tokens=150,
    )

    plan = llm.extract_json(raw)

    if plan is None:
        return _empty_plan("unsupported")

    # ------------------------------------------------------------------------
    # 6. Strict normalization
    # ------------------------------------------------------------------------

    return _normalize_plan(plan)