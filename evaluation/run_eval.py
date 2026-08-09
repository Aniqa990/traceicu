"""
Evaluate the bigger TraceICU project's current AI stack against the local
50-question benchmark.

Unlike the smaller project's evaluator, this runner does NOT import
``app.pipeline`` or ``app.data_loader``. It calls the bigger project's
actual AI components (``app.ai.intents``, ``app.ai.retrieval`` and
``app.ai.answer``) and grades the returned AskResponse using the evidence
objects produced by that stack.

The ground-truth answer key is loaded only by this evaluator and is never
passed to the model.

Usage (from the project root):
    python -m evaluation.run_eval

Outputs:
    evaluation/results.csv
    evaluation/report.json
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.ai.answer import build_answer, out_of_scope_response, unsupported_response
from app.ai.concepts import init_concept_index
from app.ai.intents import ALLOWED_INTENTS, extract_query_plan
from app.ai.llm import get_llm_client
from app.ai.retrieval import (
    RetrievalResult,
    event_count,
    icu_stay_info,
    measurement_extreme,
    measurements_in_range,
    medications,
    procedures,
    resolve_scope,
    transfers,
)
from app.ai.schema import QueryPlan
from app.cache import timeline_cache
from app.database import get_connection
from app.timeline import get_patient_timeline

BASE_DIR = Path(__file__).resolve().parent


def load_benchmark() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    questions = json.loads((BASE_DIR / "questions.json").read_text())
    ground_truth_list = json.loads((BASE_DIR / "ground_truth.json").read_text())
    ground_truth = {item["id"]: item for item in ground_truth_list}
    return questions, ground_truth


def numbers_close(a: Any, b: Any, tol: float = 0.01) -> bool:
    try:
        return math.isclose(float(a), float(b), abs_tol=tol, rel_tol=0.0)
    except (TypeError, ValueError):
        return str(a) == str(b)


def _as_text(value: Any) -> str:
    return "" if value is None else str(value)


def _same_time(a: Any, b: Any) -> bool:
    """Compare MIMIC timestamps loosely, ignoring seconds when necessary."""
    if a is None or b is None:
        return False
    sa = _as_text(a)
    sb = _as_text(b)

    # Exact string / first-minute match covers the benchmark's timestamp style.
    if sa == sb or sa[:16] == sb[:16]:
        return True

    try:
        da = datetime.fromisoformat(sa.replace("Z", "+00:00"))
        db = datetime.fromisoformat(sb.replace("Z", "+00:00"))
        return da.replace(second=0, microsecond=0) == db.replace(second=0, microsecond=0)
    except ValueError:
        return False


def _evidence_fields(response) -> list[dict[str, Any]]:
    return [e.source_fields for e in response.evidence]


def _evidence_tables(response) -> set[str]:
    return {e.source_table for e in response.evidence}


def grade_supported(response, gt: dict[str, Any]) -> dict[str, Any]:
    """Grade supported questions from structured evidence, not answer prose."""
    expected = gt.get("ground_truth", {}).get("expected_answer", {}) or {}
    source = gt.get("ground_truth", {}).get("source", {}) or {}
    fields = _evidence_fields(response)
    tables = _evidence_tables(response)

    checks: dict[str, Any] = {
        "status_correct": response.status == "supported",
        "fact_accuracy": False,
        "temporal_accuracy": None,
        "provenance_correct": False,
    }

    if response.status != "supported" or not fields:
        return checks

    expected_value = expected.get("value")
    if expected_value is not None:
        checks["fact_accuracy"] = any(
            numbers_close(f.get("valuenum"), expected_value)
            or numbers_close(f.get("value"), expected_value)
            for f in fields
        )
    elif expected.get("intime") is not None:
        checks["fact_accuracy"] = any(
            _same_time(f.get("intime"), expected["intime"]) for f in fields
        )
    elif expected.get("count") is not None:
        checks["fact_accuracy"] = any(
            numbers_close(f.get("count"), expected["count"]) for f in fields
        )
    else:
        # Some benchmark answers are categorical/textual. Compare the expected
        # answer against evidence values when present.
        expected_text = expected.get("text") or expected.get("value")
        if expected_text is not None:
            checks["fact_accuracy"] = any(
                _as_text(expected_text).lower() in _as_text(v).lower()
                for f in fields
                for v in f.values()
            )
        else:
            checks["fact_accuracy"] = bool(fields)

    expected_time = expected.get("charttime") or expected.get("intime")
    if expected_time is not None:
        checks["temporal_accuracy"] = any(
            _same_time(f.get("charttime"), expected_time)
            or _same_time(f.get("intime"), expected_time)
            for f in fields
        )

    expected_table = source.get("table")
    if expected_table is None:
        expected_tables = set(gt.get("ground_truth", {}).get("source_tables", []))
        checks["provenance_correct"] = bool(tables & expected_tables) if expected_tables else bool(fields)
    else:
        # Require the expected table plus the expected row identity whenever
        # the benchmark gives us one. This prevents a merely related row from
        # receiving full provenance credit.
        table_ok = expected_table in tables
        identity_fields = [
            key for key in ("labevent_id", "itemid", "stay_id", "transfer_id", "emar_id", "seq_num")
            if key in source
        ]
        if not identity_fields:
            row_ok = True
        else:
            row_ok = any(
                all(_as_text(f.get(key)) == _as_text(source.get(key)) for key in identity_fields)
                for f in fields
            )
        checks["provenance_correct"] = table_ok and row_ok

    return checks


def _ask(conn, question: dict[str, Any]):
    """Run exactly the same deterministic AI/retrieval flow as app/main.py."""
    t0 = time.perf_counter()
    subject_id = question["subject_id"]

    patient = conn.execute(
        "SELECT subject_id FROM patients WHERE subject_id = ?", [subject_id]
    ).fetchone()
    if patient is None:
        raise RuntimeError(f"No patient found with subject_id={subject_id}.")

    hadm_id, stay_id = resolve_scope(
        conn, subject_id, question.get("hadm_id"), question.get("stay_id")
    )

    plan_dict = extract_query_plan(question["question"])
    plan = QueryPlan(
        intent=plan_dict.get("intent"),
        domain=plan_dict.get("domain"),
        concept=plan_dict.get("concept"),
        time_scope=plan_dict.get("time_scope"),
        start_time=plan_dict.get("start_time"),
        end_time=plan_dict.get("end_time"),
        hadm_id=hadm_id,
        stay_id=stay_id,
    )

    intent = plan_dict.get("intent")
    if intent == "out_of_scope":
        response = out_of_scope_response(plan)
    elif intent not in ALLOWED_INTENTS:
        response = unsupported_response(plan)
    elif hadm_id is None:
        response = unsupported_response(plan)
    elif intent in ("first_measurement", "last_measurement"):
        which = "first" if intent == "first_measurement" else "last"
        result = measurement_extreme(
            conn, subject_id, hadm_id, stay_id,
            plan.concept, plan.domain, which,
        )
        response = build_answer(intent, plan.domain, plan.concept, result, plan)
    elif intent == "measurements_in_range":
        result = measurements_in_range(
            conn, subject_id, hadm_id, stay_id,
            plan.concept, plan.domain, plan.start_time, plan.end_time,
        )
        response = build_answer(intent, plan.domain, plan.concept, result, plan)
    elif intent == "medications":
        result = medications(
            conn, subject_id, hadm_id, plan.concept,
            plan.start_time, plan.end_time,
        )
        response = build_answer(intent, plan.domain, plan.concept, result, plan)
    elif intent == "procedures":
        result = procedures(conn, subject_id, hadm_id)
        response = build_answer(intent, plan.domain, plan.concept, result, plan)
    elif intent == "transfers":
        result = transfers(conn, subject_id, hadm_id)
        response = build_answer(intent, plan.domain, plan.concept, result, plan)
    elif intent == "icu_stay_info":
        result = icu_stay_info(conn, subject_id, hadm_id, stay_id)
        response = build_answer(intent, plan.domain, plan.concept, result, plan)
    elif intent == "event_count":
        result = event_count(conn, subject_id, hadm_id, stay_id, plan.domain)
        response = build_answer(intent, plan.domain, plan.concept, result, plan)
    elif intent == "timeline":
        cached = timeline_cache.get(subject_id)
        if cached is None:
            cached = get_patient_timeline(conn, subject_id)
            timeline_cache.set(subject_id, cached)
        facts = [
            {"event_type": e.event_type, "label": e.label, "charttime": e.event_time}
            for e in cached.events
        ]
        evidence = [ev for e in cached.events for ev in e.evidence][:50]
        result = RetrievalResult(facts, evidence, cached.tables_used)
        response = build_answer(intent, plan.domain, plan.concept, result, plan)
    else:
        response = unsupported_response(plan)

    response.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    return response


def run() -> None:
    questions, ground_truth = load_benchmark()

    # Match the API startup path: concept dictionary and LLM client are
    # initialized once before evaluation begins.
    conn = get_connection()
    init_concept_index(conn)
    get_llm_client()

    rows: list[dict[str, Any]] = []
    try:
        for q in questions:
            gt = ground_truth[q["id"]]
            try:
                response = _ask(conn, q)
                expected_status = gt["expected_status"].lower()
                got_status = response.status

                row: dict[str, Any] = {
                    "id": q["id"],
                    "question": q["question"],
                    "expected_status": expected_status,
                    "got_status": got_status,
                    "status_correct": got_status == expected_status,
                    "latency_ms": response.latency_ms,
                    "evidence_coverage": response.evidence_coverage,
                    "grounding_fallback": None,
                    "searched_tables": ";".join(response.searched_tables),
                    "reason": response.reason,
                    "answer": response.answer,
                    "intent": response.query_plan.intent if response.query_plan else None,
                    "concept": response.query_plan.concept if response.query_plan else None,
                }

                if expected_status == "supported":
                    row.update(grade_supported(response, gt))
                elif expected_status == "abstain":
                    row["abstain_correct"] = got_status == "abstain"
                elif expected_status == "out_of_scope":
                    row["out_of_scope_correct"] = got_status == "out_of_scope"

            except Exception as exc:  # keep the full benchmark running
                row = {
                    "id": q["id"],
                    "question": q["question"],
                    "expected_status": gt["expected_status"].lower(),
                    "got_status": "ERROR",
                    "status_correct": False,
                    "latency_ms": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }

            rows.append(row)
            print(
                f"{q['id']}: expected={row['expected_status']:12s} "
                f"got={row['got_status']:12s} "
                f"({row.get('latency_ms', 0) or 0:.0f}ms)"
            )
    finally:
        conn.close()

    write_report(rows)


def write_report(rows: list[dict[str, Any]]) -> None:
    results_path = BASE_DIR / "results.csv"
    report_path = BASE_DIR / "report.json"

    fieldnames = sorted({key for row in rows for key in row})
    with results_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    supported = [r for r in rows if r["expected_status"] == "supported"]
    unsupported = [r for r in rows if r["expected_status"] == "abstain"]
    out_of_scope = [r for r in rows if r["expected_status"] == "out_of_scope"]
    latencies = [
        float(r["latency_ms"])
        for r in rows
        if isinstance(r.get("latency_ms"), (int, float))
    ]

    def rate(items: list[dict[str, Any]], key: str):
        values = [item[key] for item in items if item.get(key) is not None]
        return sum(bool(v) for v in values) / len(values) if values else None

    report = {
        "n_total": len(rows),
        "n_supported": len(supported),
        "n_unsupported": len(unsupported),
        "n_out_of_scope": len(out_of_scope),
        "status_accuracy": rate(rows, "status_correct"),
        "structured_fact_accuracy": rate(supported, "fact_accuracy"),
        "temporal_accuracy": rate(supported, "temporal_accuracy"),
        "provenance_coverage": rate(supported, "provenance_correct"),
        "abstention_accuracy": rate(unsupported, "abstain_correct"),
        "out_of_scope_rejection_accuracy": rate(out_of_scope, "out_of_scope_correct"),
        "evidence_coverage_mean": (
            statistics.mean(
                float(r["evidence_coverage"])
                for r in rows
                if isinstance(r.get("evidence_coverage"), (int, float))
            )
            if any(isinstance(r.get("evidence_coverage"), (int, float)) for r in rows)
            else None
        ),
        "latency_ms_median": statistics.median(latencies) if latencies else None,
        "latency_ms_p95": (
            statistics.quantiles(latencies, n=20)[18]
            if len(latencies) >= 20
            else max(latencies)
        ) if latencies else None,
        "errors": sum(1 for r in rows if r.get("got_status") == "ERROR"),
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== SUMMARY ===")
    print(json.dumps(report, indent=2))
    print(f"\nFull per-question results: {results_path}")
    print(f"Aggregate report: {report_path}")


if __name__ == "__main__":
    run()
