"""
Deterministic, parameterized retrieval for each whitelisted intent.

The LLM decides WHAT to ask for (intent / concept / time_scope); this
module decides HOW to fetch it. No string built from model output is
ever interpolated into SQL here -- only fixed query templates with
bound parameters (`?`). This is the layer that gives you provenance
coverage and structured-fact accuracy "for free": every row returned
here becomes an Evidence object with its source table and full row.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import duckdb

from app.models import Evidence
from app.ai.concepts import get_concept_index


class RetrievalResult:
    def __init__(self, facts: list[dict[str, Any]], evidence: list[Evidence],
                 searched_tables: list[str]):
        self.facts = facts
        self.evidence = evidence
        self.searched_tables = searched_tables

    @property
    def has_evidence(self) -> bool:
        return len(self.evidence) > 0


# ============================================================================
# Scope resolution
# ============================================================================

def resolve_scope(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int | None,
    stay_id: int | None,
) -> tuple[int | None, int | None]:
    """
    Fill in hadm_id / stay_id when the caller didn't specify them,
    defaulting to the patient's most recent admission / ICU stay. This
    default is always echoed back in the response's query_plan, so it's
    never a silent assumption -- the user can see exactly which
    encounter was queried and override it with hadm_id/stay_id.
    """
    if hadm_id is None:
        row = con.execute(
            "SELECT hadm_id FROM admissions WHERE subject_id = ? "
            "ORDER BY admittime DESC LIMIT 1",
            [subject_id],
        ).fetchone()
        hadm_id = row[0] if row else None

    if stay_id is None and hadm_id is not None:
        row = con.execute(
            "SELECT stay_id FROM icustays WHERE subject_id = ? AND hadm_id = ? "
            "ORDER BY intime DESC LIMIT 1",
            [subject_id, hadm_id],
        ).fetchone()
        stay_id = row[0] if row else None

    return hadm_id, stay_id


# ============================================================================
# first / last measurement
# ============================================================================

def measurement_extreme(con, subject_id, hadm_id, stay_id, concept, domain, which):
    itemid = get_concept_index().resolve(concept, domain or "lab")
    if itemid is None:
        return RetrievalResult([], [], [])

    order = "ASC" if which == "first" else "DESC"

    if domain == "icu_observation":
        if stay_id is None:
            return RetrievalResult([], [], ["icustays"])
        rows = con.execute(f"""
            SELECT c.subject_id, c.hadm_id, c.stay_id, c.itemid, c.charttime,
                   c.value, c.valuenum, c.valueuom, d.label
            FROM chartevents c
            LEFT JOIN d_items d ON c.itemid = d.itemid
            WHERE c.subject_id = ? AND c.stay_id = ? AND c.itemid = ?
              AND c.charttime IS NOT NULL
            ORDER BY c.charttime {order}
            LIMIT 1
        """, [subject_id, stay_id, itemid]).fetchall()
        cols = ["subject_id", "hadm_id", "stay_id", "itemid", "charttime",
                "value", "valuenum", "valueuom", "label"]
        table = "chartevents"
    else:
        rows = con.execute(f"""
            SELECT l.subject_id, l.hadm_id, l.itemid, l.charttime,
                   l.value, l.valuenum, l.valueuom, l.flag, d.label
            FROM labevents l
            LEFT JOIN d_labitems d ON l.itemid = d.itemid
            WHERE l.subject_id = ? AND l.hadm_id = ? AND l.itemid = ?
              AND l.charttime IS NOT NULL
            ORDER BY l.charttime {order}
            LIMIT 1
        """, [subject_id, hadm_id, itemid]).fetchall()
        cols = ["subject_id", "hadm_id", "itemid", "charttime",
                "value", "valuenum", "valueuom", "flag", "label"]
        table = "labevents"

    if not rows:
        return RetrievalResult([], [], [table])

    r = dict(zip(cols, rows[0]))
    return RetrievalResult([r], [Evidence(source_table=table, source_fields=r)], [table])


# ============================================================================
# measurements in a time range
# ============================================================================

def measurements_in_range(con, subject_id, hadm_id, stay_id, concept, domain,
                           start: datetime | None, end: datetime | None):
    itemid = get_concept_index().resolve(concept, domain or "lab")
    if itemid is None:
        return RetrievalResult([], [], [])

    start = start or datetime.min
    end = end or datetime.max

    if domain == "icu_observation":
        if stay_id is None:
            return RetrievalResult([], [], ["icustays"])
        rows = con.execute("""
            SELECT c.subject_id, c.hadm_id, c.stay_id, c.itemid, c.charttime,
                   c.value, c.valuenum, c.valueuom, d.label
            FROM chartevents c
            LEFT JOIN d_items d ON c.itemid = d.itemid
            WHERE c.subject_id = ? AND c.stay_id = ? AND c.itemid = ?
              AND c.charttime BETWEEN ? AND ?
            ORDER BY c.charttime
            LIMIT 200
        """, [subject_id, stay_id, itemid, start, end]).fetchall()
        cols = ["subject_id", "hadm_id", "stay_id", "itemid", "charttime",
                "value", "valuenum", "valueuom", "label"]
        table = "chartevents"
    else:
        rows = con.execute("""
            SELECT l.subject_id, l.hadm_id, l.itemid, l.charttime,
                   l.value, l.valuenum, l.valueuom, l.flag, d.label
            FROM labevents l
            LEFT JOIN d_labitems d ON l.itemid = d.itemid
            WHERE l.subject_id = ? AND l.hadm_id = ? AND l.itemid = ?
              AND l.charttime BETWEEN ? AND ?
            ORDER BY l.charttime
            LIMIT 200
        """, [subject_id, hadm_id, itemid, start, end]).fetchall()
        cols = ["subject_id", "hadm_id", "itemid", "charttime",
                "value", "valuenum", "valueuom", "flag", "label"]
        table = "labevents"

    facts = [dict(zip(cols, row)) for row in rows]
    evidence = [Evidence(source_table=table, source_fields=f) for f in facts]
    return RetrievalResult(facts, evidence, [table])


# ============================================================================
# medications (eMAR)
# ============================================================================

def medications(con, subject_id, hadm_id, concept, start, end):
    query = """
        SELECT emar_id, subject_id, hadm_id, medication, charttime, event_txt
        FROM emar
        WHERE subject_id = ? AND hadm_id = ? AND charttime IS NOT NULL
    """
    params: list[Any] = [subject_id, hadm_id]

    if concept:
        query += " AND lower(medication) LIKE ?"
        params.append(f"%{concept.lower()}%")
    if start:
        query += " AND charttime >= ?"
        params.append(start)
    if end:
        query += " AND charttime <= ?"
        params.append(end)

    query += " ORDER BY charttime LIMIT 200"

    rows = con.execute(query, params).fetchall()
    cols = ["emar_id", "subject_id", "hadm_id", "medication", "charttime", "event_txt"]
    facts = [dict(zip(cols, row)) for row in rows]
    evidence = [Evidence(source_table="emar", source_fields=f) for f in facts]
    return RetrievalResult(facts, evidence, ["emar"])


# ============================================================================
# procedures
# ============================================================================

def procedures(con, subject_id, hadm_id):
    rows = con.execute("""
        SELECT p.subject_id, p.hadm_id, p.seq_num, p.chartdate,
               p.icd_code, p.icd_version, d.long_title
        FROM procedures_icd p
        LEFT JOIN d_icd_procedures d
            ON p.icd_code = d.icd_code AND p.icd_version = d.icd_version
        WHERE p.subject_id = ? AND p.hadm_id = ?
        ORDER BY p.chartdate
    """, [subject_id, hadm_id]).fetchall()
    cols = ["subject_id", "hadm_id", "seq_num", "chartdate", "icd_code",
            "icd_version", "long_title"]
    facts = [dict(zip(cols, row)) for row in rows]
    evidence = [Evidence(source_table="procedures_icd", source_fields=f) for f in facts]
    return RetrievalResult(facts, evidence, ["procedures_icd"])


# ============================================================================
# transfers
# ============================================================================

def transfers(con, subject_id, hadm_id):
    rows = con.execute("""
        SELECT transfer_id, subject_id, hadm_id, eventtype, careunit, intime, outtime
        FROM transfers
        WHERE subject_id = ? AND hadm_id = ?
        ORDER BY intime
    """, [subject_id, hadm_id]).fetchall()
    cols = ["transfer_id", "subject_id", "hadm_id", "eventtype", "careunit", "intime", "outtime"]
    facts = [dict(zip(cols, row)) for row in rows]
    evidence = [Evidence(source_table="transfers", source_fields=f) for f in facts]
    return RetrievalResult(facts, evidence, ["transfers"])


# ============================================================================
# ICU stay info
# ============================================================================

def icu_stay_info(con, subject_id, hadm_id, stay_id):
    query = (
        "SELECT stay_id, subject_id, hadm_id, first_careunit, last_careunit, "
        "intime, outtime, los FROM icustays WHERE subject_id = ? AND hadm_id = ?"
    )
    params: list[Any] = [subject_id, hadm_id]
    if stay_id:
        query += " AND stay_id = ?"
        params.append(stay_id)

    rows = con.execute(query, params).fetchall()
    cols = ["stay_id", "subject_id", "hadm_id", "first_careunit", "last_careunit",
            "intime", "outtime", "los"]
    facts = [dict(zip(cols, row)) for row in rows]
    evidence = [Evidence(source_table="icustays", source_fields=f) for f in facts]
    return RetrievalResult(facts, evidence, ["icustays"])


# ============================================================================
# event count
# ============================================================================

TABLE_BY_DOMAIN = {
    "lab": ("labevents", "hadm_id"),
    "icu_observation": ("chartevents", "stay_id"),
    "medication": ("emar", "hadm_id"),
    "procedure": ("procedures_icd", "hadm_id"),
    "transfer": ("transfers", "hadm_id"),
}


def event_count(con, subject_id, hadm_id, stay_id, domain):
    if domain not in TABLE_BY_DOMAIN:
        return RetrievalResult([], [], [])

    table, scope_col = TABLE_BY_DOMAIN[domain]
    scope_val = stay_id if scope_col == "stay_id" else hadm_id
    if scope_val is None:
        return RetrievalResult([], [], [table])

    row = con.execute(
        f"SELECT COUNT(*) FROM {table} WHERE subject_id = ? AND {scope_col} = ?",
        [subject_id, scope_val],
    ).fetchone()
    count = row[0] if row else 0

    fact = {"table": table, "count": count, "subject_id": subject_id, scope_col: scope_val}
    evidence = [Evidence(source_table=table, source_fields=fact)] if count > 0 else []
    return RetrievalResult([fact], evidence, [table])