import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from app.database import get_connection
from app.timeline import ScopeNotFoundError, get_patient_timeline
from app.cache import timeline_cache

from app.timeline import ScopeNotFoundError, get_patient_timeline, find_event
from app.subjects import search_subjects, get_subject_overview

from app.ai.concepts import init_concept_index
from app.ai.llm import get_llm_client
from app.ai.intents import extract_query_plan, ALLOWED_INTENTS
from app.ai.retrieval import (
    RetrievalResult,
    resolve_scope,
    measurement_extreme,
    measurements_in_range,
    medications,
    procedures,
    transfers,
    icu_stay_info,
    event_count,
)
from app.ai.answer import build_answer, out_of_scope_response, unsupported_response
from app.ai.schema import AskRequest, AskResponse, QueryPlan


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One read-only DuckDB connection for the life of the process. DuckDB
    # connections support cheap `.cursor()` calls for thread-safe reuse
    # across requests, so we avoid re-opening the file on every call.
    conn = get_connection()

    # Preload d_labitems / d_items into memory once -- see app/ai/concepts.py.
    init_concept_index(conn)

    # Validate HF_TOKEN / build the InferenceClient once at startup, so a
    # missing token fails loudly here instead of on someone's first /ask.
    get_llm_client()

    app.state.db = conn
    yield
    conn.close()

def _serialize_event_summary(event) -> dict:
    """
    Strip `children` from a cluster event for the Level-1 journey
    response, keeping only a count. Individual events are unaffected
    (they never had children) and keep their embedded `evidence`, so
    the provenance drawer for a non-clustered event still needs zero
    extra requests.
    """
    data = event.model_dump(mode="json", exclude_none=True, exclude={"children"})
    if event.children:
        data["child_count"] = len(event.children)
    return data

app = FastAPI(
    title="TraceICU API",
    version="0.1.0",
    lifespan=lifespan,
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/test-db")
def test_db():
    conn = app.state.db.cursor()
    result = conn.execute("SELECT COUNT(*) FROM patients").fetchone()
    return {"patients": result[0]}


@app.get("/api/v1/subjects/search")
def subjects_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=25),
):
    conn = app.state.db.cursor()
    results = search_subjects(conn, q, limit)
    return {"results": [r.model_dump() for r in results]}


@app.get("/api/v1/subjects/{subject_id}")
def subject_overview(subject_id: int):
    conn = app.state.db.cursor()
    overview = get_subject_overview(conn, subject_id)
    if overview is None:
        raise HTTPException(
            status_code=404,
            detail=f"No patient found with subject_id={subject_id}.",
        )
    return overview.model_dump()


# ==========================================================================
# Timeline (Level 1) — now lightweight
# ==========================================================================

@app.get("/api/v1/timeline")
def timeline(
    subject_id: int | None = Query(None),
    hadm_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    if subject_id is None and hadm_id is None:
        raise HTTPException(
            status_code=400,
            detail="Provide either subject_id or hadm_id.",
        )

    conn = app.state.db.cursor()

    if subject_id is None:
        row = conn.execute(
            "SELECT subject_id FROM admissions WHERE hadm_id = ?",
            [hadm_id],
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"No admission found with hadm_id={hadm_id}.")
        subject_id = row[0]

    cached = timeline_cache.get(subject_id)
    if cached is not None:
        tl = cached
    else:
        try:
            tl = get_patient_timeline(conn, subject_id)
        except ScopeNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        timeline_cache.set(subject_id, tl)

    events = tl.events[offset: offset + limit]

    return {
        "subject_id": subject_id,
        "hadm_id": hadm_id,
        "limit": limit,
        "offset": offset,
        "total_events": len(tl.events),
        "events": [_serialize_event_summary(event) for event in events],
    }


# ==========================================================================
# Event drill-down (Level 2 / Level 3)
# ==========================================================================

@app.get("/api/v1/events/{event_id}")
def event_detail(
    event_id: str,
    subject_id: int = Query(...),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    """
    - Cluster event (is_derived=True): returns the cluster's own
      metadata plus a paginated slice of its children. Each child
      already carries its own Evidence (source_table + source_fields =
      the exact raw row), so no further request is needed to populate
      the provenance drawer for any row shown here.
    - Non-cluster event: returned as-is, evidence included. Present so
      the frontend can hit one endpoint uniformly, and so a direct
      link to a single event (e.g. from a chat citation) works without
      the Level-1 payload already being loaded client-side.
    """
    conn = app.state.db.cursor()

    cached = timeline_cache.get(subject_id)
    if cached is None:
        try:
            cached = get_patient_timeline(conn, subject_id)
        except ScopeNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        timeline_cache.set(subject_id, cached)

    event = find_event(cached.events, event_id)
    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"No event found with event_id={event_id} for subject_id={subject_id}.",
        )

    data = event.model_dump(mode="json", exclude_none=True, exclude={"children"})

    if event.children:
        total = len(event.children)
        page = event.children[offset: offset + limit]
        data["children"] = [
            child.model_dump(mode="json", exclude_none=True)
            for child in page
        ]
        data["children_total"] = total
        data["children_limit"] = limit
        data["children_offset"] = offset

    return data


@app.post("/api/v1/ask", response_model=AskResponse)
def ask(request: AskRequest):
    """
    Evidence-first Q&A over a single patient's structured record.

    Flow: question -> LLM produces a whitelisted intent (JSON, no SQL)
    -> deterministic parameterized query against DuckDB -> template
    answer built ONLY from retrieved rows -> every row cited as
    Evidence. If nothing is retrieved, the endpoint abstains instead of
    guessing.
    """
    t0 = time.perf_counter()
    conn = app.state.db.cursor()

    patient = conn.execute(
        "SELECT subject_id FROM patients WHERE subject_id = ?",
        [request.subject_id],
    ).fetchone()
    if patient is None:
        raise HTTPException(
            status_code=404,
            detail=f"No patient found with subject_id={request.subject_id}.",
        )

    hadm_id, stay_id = resolve_scope(conn, request.subject_id, request.hadm_id, request.stay_id)

    plan_dict = extract_query_plan(request.question)
    intent = plan_dict.get("intent")

    plan = QueryPlan(
        intent=intent,
        domain=plan_dict.get("domain"),
        concept=plan_dict.get("concept"),
        time_scope=plan_dict.get("time_scope"),
        start_time=plan_dict.get("start_time"),
        end_time=plan_dict.get("end_time"),
        hadm_id=hadm_id,
        stay_id=stay_id,
    )

    if intent == "out_of_scope":
        response = out_of_scope_response(plan)

    elif intent not in ALLOWED_INTENTS:
        response = unsupported_response(plan)

    elif hadm_id is None:
        # No admissions on record for this patient at all.
        response = unsupported_response(plan)

    else:
        result: RetrievalResult | None

        if intent in ("first_measurement", "last_measurement"):
            which = "first" if intent == "first_measurement" else "last"
            result = measurement_extreme(
                conn, request.subject_id, hadm_id, stay_id, plan.concept, plan.domain, which
            )

        elif intent == "measurements_in_range":
            result = measurements_in_range(
                conn, request.subject_id, hadm_id, stay_id,
                plan.concept, plan.domain, plan.start_time, plan.end_time,
            )

        elif intent == "medications":
            result = medications(conn, request.subject_id, hadm_id, plan.concept, plan.start_time, plan.end_time)

        elif intent == "procedures":
            result = procedures(conn, request.subject_id, hadm_id)

        elif intent == "transfers":
            result = transfers(conn, request.subject_id, hadm_id)

        elif intent == "icu_stay_info":
            result = icu_stay_info(conn, request.subject_id, hadm_id, stay_id)

        elif intent == "event_count":
            result = event_count(conn, request.subject_id, hadm_id, stay_id, plan.domain)

        elif intent == "timeline":
            cached = timeline_cache.get(request.subject_id)
            if cached is None:
                cached = get_patient_timeline(conn, request.subject_id)
                timeline_cache.set(request.subject_id, cached)

            facts = [
                {"event_type": e.event_type, "label": e.label, "charttime": e.event_time}
                for e in cached.events
            ]
            evidence = [ev for e in cached.events for ev in e.evidence][:50]
            result = RetrievalResult(facts, evidence, cached.tables_used)

        else:
            result = None

        response = build_answer(intent, plan.domain, plan.concept, result, plan) if result is not None else unsupported_response(plan)

    response.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    return response