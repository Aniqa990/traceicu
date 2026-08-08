"""
Reconstructs a patient's encounter into a chronological, evidence-linked
event stream (Track 1: Structured Patient Timeline & Evidence Retrieval).

Public entry point: get_patient_timeline(con, subject_id, hadm_id=None, stay_id=None)

Design:
  - Each source table gets its own small builder function that returns a
    flat list of Event objects, each carrying an Evidence pointer back to
    its source row.
  - High-volume point events (labs, ICU chartevents) are then grouped by
    time proximity into *_CLUSTER events via a single generic clustering
    function. The raw events are never discarded -- they live on as
    `.children` and keep their own evidence.
  - Nothing here calls an LLM. This module is pure retrieval/reshaping of
    the structured record, which is exactly what the AI layer (built
    separately) is expected to sit on top of and never override.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import duckdb

from config import CLUSTER_WINDOW_MINUTES, MAX_ICU_OBSERVATIONS
from db import loaded_tables, query
from models import Event, Evidence, Timeline


class ScopeNotFoundError(ValueError):
    """Raised when subject_id/hadm_id/stay_id don't resolve to a real record."""


# --------------------------------------------------------------------------
# Scope resolution
# --------------------------------------------------------------------------

def resolve_scope(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int | None = None,
    stay_id: int | None = None,
) -> tuple[int | None, int | None]:
    """Fills in hadm_id/stay_id from each other where possible and
    validates that everything actually belongs to subject_id. Raises
    ScopeNotFoundError instead of silently returning an empty timeline --
    an explicit "this doesn't exist" beats a quietly empty page."""

    patient_rows = query(con, "SELECT subject_id FROM patients WHERE subject_id = ?", [subject_id])
    if not patient_rows:
        raise ScopeNotFoundError(f"No patient found with subject_id={subject_id}")

    if stay_id is not None:
        rows = query(
            con,
            "SELECT hadm_id, subject_id FROM icustays WHERE stay_id = ?",
            [stay_id],
        )
        if not rows:
            raise ScopeNotFoundError(f"No ICU stay found with stay_id={stay_id}")
        if rows[0]["subject_id"] != subject_id:
            raise ScopeNotFoundError(f"stay_id={stay_id} does not belong to subject_id={subject_id}")
        resolved_hadm = rows[0]["hadm_id"]
        if hadm_id is not None and hadm_id != resolved_hadm:
            raise ScopeNotFoundError(
                f"stay_id={stay_id} belongs to hadm_id={resolved_hadm}, not hadm_id={hadm_id}"
            )
        hadm_id = resolved_hadm

    if hadm_id is not None:
        rows = query(con, "SELECT subject_id FROM admissions WHERE hadm_id = ?", [hadm_id])
        if not rows:
            raise ScopeNotFoundError(f"No admission found with hadm_id={hadm_id}")
        if rows[0]["subject_id"] != subject_id:
            raise ScopeNotFoundError(f"hadm_id={hadm_id} does not belong to subject_id={subject_id}")

    return hadm_id, stay_id


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _to_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return None


def _scope_clause(field: str, hadm_id, stay_id, use_stay: bool) -> tuple[str, list]:
    """Builds a 'WHERE ...' fragment scoping a query to hadm_id (or
    stay_id, for ICU tables), falling back gracefully when one is None."""
    if use_stay and stay_id is not None:
        return f"{field} = ?", [stay_id]
    if hadm_id is not None:
        return f"{field} = ?", [hadm_id]
    return "1=1", []


# --------------------------------------------------------------------------
# Per-table event builders
# --------------------------------------------------------------------------

def _admission_events(con, subject_id: int, hadm_id: int) -> list[Event]:
    rows = query(
        con,
        """
        SELECT hadm_id, admittime, dischtime, admission_type,
               admission_location, discharge_location, insurance,
               hospital_expire_flag
        FROM admissions
        WHERE subject_id = ? AND hadm_id = ?
        """,
        [subject_id, hadm_id],
    )
    events: list[Event] = []
    for r in rows:
        base_evidence = [Evidence(source_table="admissions", source_fields=r)]
        events.append(Event(
            event_id=f"admission-start-{r['hadm_id']}",
            subject_id=subject_id,
            hadm_id=r["hadm_id"],
            event_time=_to_dt(r["admittime"]),
            event_type="ADMISSION",
            event_subtype=r.get("admission_type"),
            label=f"Admitted ({r.get('admission_type') or 'unknown type'})",
            value=r.get("admission_location"),
            evidence=base_evidence,
        ))
        if r.get("dischtime") is not None:
            events.append(Event(
                event_id=f"admission-end-{r['hadm_id']}",
                subject_id=subject_id,
                hadm_id=r["hadm_id"],
                event_time=_to_dt(r["dischtime"]),
                event_type="DISCHARGE",
                label="Discharged" + (" (expired)" if r.get("hospital_expire_flag") else ""),
                value=r.get("discharge_location"),
                evidence=base_evidence,
            ))
    return events


def _transfer_events(con, subject_id: int, hadm_id: int) -> list[Event]:
    rows = query(
        con,
        """
        SELECT transfer_id, eventtype, careunit, intime, outtime
        FROM transfers
        WHERE subject_id = ? AND hadm_id = ?
        ORDER BY intime
        """,
        [subject_id, hadm_id],
    )
    events = []
    for r in rows:
        events.append(Event(
            event_id=f"transfer-{r['transfer_id']}",
            subject_id=subject_id,
            hadm_id=hadm_id,
            event_time=_to_dt(r["intime"]),
            event_end_time=_to_dt(r["outtime"]),
            event_type="TRANSFER",
            event_subtype=r.get("eventtype"),
            label=r.get("careunit") or (r.get("eventtype") or "transfer"),
            evidence=[Evidence(source_table="transfers", source_fields=r)],
        ))
    return events


def _lab_events(con, subject_id: int, hadm_id: int) -> list[Event]:
    rows = query(
        con,
        """
        SELECT l.labevent_id, l.itemid, l.charttime, l.value, l.valuenum,
               l.valueuom, l.ref_range_lower, l.ref_range_upper, l.flag,
               d.label
        FROM labevents l
        LEFT JOIN d_labitems d ON l.itemid = d.itemid
        WHERE l.subject_id = ? AND l.hadm_id = ?
        ORDER BY l.charttime
        """,
        [subject_id, hadm_id],
    )
    events = []
    for r in rows:
        flag = r.get("flag")
        events.append(Event(
            event_id=f"lab-{r['labevent_id']}",
            subject_id=subject_id,
            hadm_id=hadm_id,
            event_time=_to_dt(r["charttime"]),
            event_type="LAB",
            event_subtype="abnormal" if flag else "normal",
            label=r.get("label") or f"itemid {r['itemid']}",
            value=r.get("value") if r.get("valuenum") is None else str(r.get("valuenum")),
            unit=r.get("valueuom"),
            evidence=[Evidence(source_table="labevents", source_fields=r)],
        ))
    return events


def _medication_events(con, subject_id: int, hadm_id: int) -> list[Event]:
    rows = query(
        con,
        """
        SELECT pharmacy_id, drug, starttime, stoptime, dose_val_rx,
               dose_unit_rx, route
        FROM prescriptions
        WHERE subject_id = ? AND hadm_id = ?
        ORDER BY starttime
        """,
        [subject_id, hadm_id],
    )
    events = []
    for i, r in enumerate(rows):
        events.append(Event(
            event_id=f"rx-{r.get('pharmacy_id', i)}-{i}",
            subject_id=subject_id,
            hadm_id=hadm_id,
            event_time=_to_dt(r["starttime"]),
            event_end_time=_to_dt(r["stoptime"]),
            event_type="MEDICATION",
            event_subtype=r.get("route"),
            label=r.get("drug") or "medication",
            value=r.get("dose_val_rx"),
            unit=r.get("dose_unit_rx"),
            evidence=[Evidence(source_table="prescriptions", source_fields=r)],
        ))
    return events


def _diagnosis_events(con, subject_id: int, hadm_id: int) -> list[Event]:
    """diagnoses_icd has no timestamp -- codes are assigned for the whole
    admission, typically finalized at discharge. We anchor these events at
    dischtime and say so explicitly rather than implying a real time."""
    admit = query(con, "SELECT dischtime, admittime FROM admissions WHERE hadm_id = ?", [hadm_id])
    anchor_time = None
    if admit:
        anchor_time = admit[0].get("dischtime") or admit[0].get("admittime")

    rows = query(
        con,
        """
        SELECT dx.seq_num, dx.icd_code, dx.icd_version, d.long_title
        FROM diagnoses_icd dx
        LEFT JOIN d_icd_diagnoses d
          ON dx.icd_code = d.icd_code AND dx.icd_version = d.icd_version
        WHERE dx.subject_id = ? AND dx.hadm_id = ?
        ORDER BY dx.seq_num
        """,
        [subject_id, hadm_id],
    )
    events = []
    for r in rows:
        events.append(Event(
            event_id=f"dx-{hadm_id}-{r['seq_num']}",
            subject_id=subject_id,
            hadm_id=hadm_id,
            event_time=_to_dt(anchor_time),
            event_type="DIAGNOSIS",
            event_subtype=f"ICD-{r.get('icd_version')}",
            label=r.get("long_title") or r.get("icd_code"),
            value=r.get("icd_code"),
            is_derived=True,
            derivation_rule=(
                "diagnoses_icd has no timestamp; this event is anchored to "
                "the admission's discharge time (or admit time if missing) "
                "as a placeholder, not a literal diagnosis time."
            ),
            evidence=[Evidence(source_table="diagnoses_icd", source_fields=r)],
        ))
    return events


def _procedure_events(con, subject_id: int, hadm_id: int) -> list[Event]:
    rows = query(
        con,
        """
        SELECT p.seq_num, p.chartdate, p.icd_code, p.icd_version, d.long_title
        FROM procedures_icd p
        LEFT JOIN d_icd_procedures d
          ON p.icd_code = d.icd_code AND p.icd_version = d.icd_version
        WHERE p.subject_id = ? AND p.hadm_id = ?
        ORDER BY p.chartdate
        """,
        [subject_id, hadm_id],
    )
    events = []
    for r in rows:
        events.append(Event(
            event_id=f"proc-{hadm_id}-{r['seq_num']}",
            subject_id=subject_id,
            hadm_id=hadm_id,
            event_time=_to_dt(r["chartdate"]),
            event_type="PROCEDURE",
            event_subtype=f"ICD-{r.get('icd_version')}",
            label=r.get("long_title") or r.get("icd_code"),
            value=r.get("icd_code"),
            evidence=[Evidence(source_table="procedures_icd", source_fields=r)],
        ))
    return events


def _icu_stay_events(con, subject_id: int, hadm_id: int) -> tuple[list[Event], list[int]]:
    rows = query(
        con,
        """
        SELECT stay_id, first_careunit, last_careunit, intime, outtime, los
        FROM icustays
        WHERE subject_id = ? AND hadm_id = ?
        ORDER BY intime
        """,
        [subject_id, hadm_id],
    )
    events = []
    stay_ids = []
    for r in rows:
        stay_ids.append(r["stay_id"])
        events.append(Event(
            event_id=f"icu-start-{r['stay_id']}",
            subject_id=subject_id,
            hadm_id=hadm_id,
            stay_id=r["stay_id"],
            event_time=_to_dt(r["intime"]),
            event_type="ICU_STAY",
            event_subtype="admission",
            label=f"ICU admission ({r.get('first_careunit')})",
            evidence=[Evidence(source_table="icustays", source_fields=r)],
        ))
        if r.get("outtime") is not None:
            events.append(Event(
                event_id=f"icu-end-{r['stay_id']}",
                subject_id=subject_id,
                hadm_id=hadm_id,
                stay_id=r["stay_id"],
                event_time=_to_dt(r["outtime"]),
                event_type="ICU_STAY",
                event_subtype="discharge",
                label=f"ICU discharge ({r.get('last_careunit')})",
                evidence=[Evidence(source_table="icustays", source_fields=r)],
            ))
    return events, stay_ids


def _icu_observation_events(con, subject_id: int, stay_id: int) -> tuple[list[Event], bool]:
    """Returns (events, truncated) -- truncated is True if we hit
    MAX_ICU_OBSERVATIONS and stopped early. Chartevents volume can be
    large even in the 100-patient demo, so this is capped defensively;
    raise MAX_ICU_OBSERVATIONS once the API paginates properly."""
    rows = query(
        con,
        """
        SELECT c.charttime, c.itemid, c.value, c.valuenum, c.valueuom, c.warning, d.label, d.category
        FROM chartevents c
        LEFT JOIN d_items d ON c.itemid = d.itemid
        WHERE c.subject_id = ? AND c.stay_id = ?
        ORDER BY c.charttime
        LIMIT ?
        """,
        [subject_id, stay_id, MAX_ICU_OBSERVATIONS + 1],
    )
    truncated = len(rows) > MAX_ICU_OBSERVATIONS
    rows = rows[:MAX_ICU_OBSERVATIONS]

    events = []
    for i, r in enumerate(rows):
        events.append(Event(
            event_id=f"chart-{stay_id}-{i}-{r['itemid']}",
            subject_id=subject_id,
            stay_id=stay_id,
            event_time=_to_dt(r["charttime"]),
            event_type="ICU_OBSERVATION",
            event_subtype=r.get("category"),
            label=r.get("label") or f"itemid {r['itemid']}",
            value=r.get("value") if r.get("valuenum") is None else str(r.get("valuenum")),
            unit=r.get("valueuom"),
            evidence=[Evidence(source_table="chartevents", source_fields=r)],
        ))
    return events, truncated


# --------------------------------------------------------------------------
# Clustering
# --------------------------------------------------------------------------

def _cluster_by_time(
    events: list[Event],
    cluster_type: str,
    window_minutes: int = CLUSTER_WINDOW_MINUTES,
) -> list[Event]:
    """Groups consecutive point events of the same kind into a single
    derived cluster event when they fall within `window_minutes` of the
    previous event in the group. Singletons pass through unchanged. The
    original events are preserved as `.children`, each keeping its own
    evidence -- nothing is summarized away."""
    if not events:
        return []

    timed = sorted(
        (e for e in events if e.event_time is not None),
        key=lambda e: e.event_time,
    )
    untimed = [e for e in events if e.event_time is None]

    clusters: list[list[Event]] = []
    current: list[Event] = []
    for ev in timed:
        if current and (ev.event_time - current[-1].event_time) > timedelta(minutes=window_minutes):
            clusters.append(current)
            current = []
        current.append(ev)
    if current:
        clusters.append(current)

    grouped: list[Event] = []
    for c in clusters:
        if len(c) == 1:
            grouped.append(c[0])
            continue
        grouped.append(Event(
            event_id=f"{cluster_type.lower()}-cluster-{c[0].event_id}",
            subject_id=c[0].subject_id,
            hadm_id=c[0].hadm_id,
            stay_id=c[0].stay_id,
            event_time=c[0].event_time,
            event_end_time=c[-1].event_time,
            event_type=f"{cluster_type}_CLUSTER",
            label=f"{cluster_type.title().replace('_', ' ')} cluster ({len(c)} observations)",
            is_derived=True,
            derivation_rule=(
                f"Grouped {len(c)} {cluster_type} events occurring within "
                f"{window_minutes}-minute windows of one another, by time proximity."
            ),
            children=c,
        ))
    return grouped + untimed


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------

def get_patient_timeline(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int | None = None,
    stay_id: int | None = None,
    include_icu_observations: bool = True,
) -> Timeline:
    """Reconstructs the chronological event stream for a patient.

    Scope rules:
      - subject_id is required.
      - If hadm_id is omitted but stay_id is given, hadm_id is resolved
        from icustays.
      - If both are omitted, every admission for the patient is included
        (useful for a whole-patient overview; can be large).
    """
    hadm_id, stay_id = resolve_scope(con, subject_id, hadm_id, stay_id)

    available = set(loaded_tables(con))
    tables_used: set[str] = set()
    empty_sources: list[str] = []
    events: list[Event] = []

    hadm_ids: list[int]
    if hadm_id is not None:
        hadm_ids = [hadm_id]
    else:
        hadm_ids = [
            r["hadm_id"]
            for r in query(con, "SELECT hadm_id FROM admissions WHERE subject_id = ? ORDER BY admittime", [subject_id])
        ]

    for hid in hadm_ids:
        builders = [
            ("admissions", _admission_events),
            ("transfers", _transfer_events),
            ("prescriptions", _medication_events),
            ("diagnoses_icd", _diagnosis_events),
            ("procedures_icd", _procedure_events),
        ]
        for table_name, builder in builders:
            if table_name not in available:
                continue
            result = builder(con, subject_id, hid)
            tables_used.add(table_name)
            if not result:
                empty_sources.append(f"{table_name} (hadm_id={hid})")
            events.extend(result)

        if "labevents" in available:
            labs = _lab_events(con, subject_id, hid)
            tables_used.add("labevents")
            if not labs:
                empty_sources.append(f"labevents (hadm_id={hid})")
            events.extend(_cluster_by_time(labs, "LAB"))

        if "icustays" in available:
            icu_events, stay_ids_for_hadm = _icu_stay_events(con, subject_id, hid)
            tables_used.add("icustays")
            events.extend(icu_events)

            target_stays = [stay_id] if stay_id is not None else stay_ids_for_hadm
            if include_icu_observations and "chartevents" in available:
                for sid in target_stays:
                    if sid is None:
                        continue
                    obs, truncated = _icu_observation_events(con, subject_id, sid)
                    tables_used.add("chartevents")
                    if not obs:
                        empty_sources.append(f"chartevents (stay_id={sid})")
                    clustered = _cluster_by_time(obs, "ICU_OBSERVATION")
                    if truncated:
                        for e in clustered:
                            e.derivation_rule = (
                                (e.derivation_rule or "")
                                + f" [NOTE: capped at {MAX_ICU_OBSERVATIONS} rows for stay_id={sid}; more exist.]"
                            ).strip()
                    events.extend(clustered)

    events.sort(key=lambda e: e.event_time or datetime.max)

    return Timeline(
        subject_id=subject_id,
        hadm_id=hadm_id,
        stay_id=stay_id,
        events=events,
        event_count=sum(_count(e) for e in events),
        tables_used=sorted(tables_used),
        empty_sources=empty_sources,
    )


def _count(event: Event) -> int:
    return 1 + sum(_count(c) for c in event.children)