# """
# Deterministic, parameterized retrieval for each whitelisted intent.

# The LLM decides WHAT to ask for (intent / concept / time_scope); this
# module decides HOW to fetch it. No string built from model output is
# ever interpolated into SQL here -- only fixed query templates with
# bound parameters (`?`). This is the layer that gives you provenance
# coverage and structured-fact accuracy "for free": every row returned
# here becomes an Evidence object with its source table and full row.
# """
# from __future__ import annotations

# from datetime import datetime
# from typing import Any

# import duckdb

# from app.models import Evidence
# from app.ai.concepts import get_concept_index


# class RetrievalResult:
#     def __init__(self, facts: list[dict[str, Any]], evidence: list[Evidence],
#                  searched_tables: list[str]):
#         self.facts = facts
#         self.evidence = evidence
#         self.searched_tables = searched_tables

#     @property
#     def has_evidence(self) -> bool:
#         return len(self.evidence) > 0


# # ============================================================================
# # Scope resolution
# # ============================================================================

# def resolve_scope(
#     con: duckdb.DuckDBPyConnection,
#     subject_id: int,
#     hadm_id: int | None,
#     stay_id: int | None,
# ) -> tuple[int | None, int | None]:
#     """
#     Fill in hadm_id / stay_id when the caller didn't specify them,
#     defaulting to the patient's most recent admission / ICU stay. This
#     default is always echoed back in the response's query_plan, so it's
#     never a silent assumption -- the user can see exactly which
#     encounter was queried and override it with hadm_id/stay_id.
#     """
#     if hadm_id is None:
#         row = con.execute(
#             "SELECT hadm_id FROM admissions WHERE subject_id = ? "
#             "ORDER BY admittime DESC LIMIT 1",
#             [subject_id],
#         ).fetchone()
#         hadm_id = row[0] if row else None

#     if stay_id is None and hadm_id is not None:
#         row = con.execute(
#             "SELECT stay_id FROM icustays WHERE subject_id = ? AND hadm_id = ? "
#             "ORDER BY intime DESC LIMIT 1",
#             [subject_id, hadm_id],
#         ).fetchone()
#         stay_id = row[0] if row else None

#     return hadm_id, stay_id


# # ============================================================================
# # first / last measurement
# # ============================================================================

# def measurement_extreme(con, subject_id, hadm_id, stay_id, concept, domain, which):
#     itemid = get_concept_index().resolve(concept, domain or "lab")
#     if itemid is None:
#         return RetrievalResult([], [], [])

#     order = "ASC" if which == "first" else "DESC"

#     if domain == "icu_observation":
#         if stay_id is None:
#             return RetrievalResult([], [], ["icustays"])
#         rows = con.execute(f"""
#             SELECT c.subject_id, c.hadm_id, c.stay_id, c.itemid, c.charttime,
#                    c.value, c.valuenum, c.valueuom, d.label
#             FROM chartevents c
#             LEFT JOIN d_items d ON c.itemid = d.itemid
#             WHERE c.subject_id = ? AND c.stay_id = ? AND c.itemid = ?
#               AND c.charttime IS NOT NULL
#             ORDER BY c.charttime {order}
#             LIMIT 1
#         """, [subject_id, stay_id, itemid]).fetchall()
#         cols = ["subject_id", "hadm_id", "stay_id", "itemid", "charttime",
#                 "value", "valuenum", "valueuom", "label"]
#         table = "chartevents"
#     else:
#         rows = con.execute(f"""
#             SELECT l.subject_id, l.hadm_id, l.itemid, l.charttime,
#                    l.value, l.valuenum, l.valueuom, l.flag, d.label
#             FROM labevents l
#             LEFT JOIN d_labitems d ON l.itemid = d.itemid
#             WHERE l.subject_id = ? AND l.hadm_id = ? AND l.itemid = ?
#               AND l.charttime IS NOT NULL
#             ORDER BY l.charttime {order}
#             LIMIT 1
#         """, [subject_id, hadm_id, itemid]).fetchall()
#         cols = ["subject_id", "hadm_id", "itemid", "charttime",
#                 "value", "valuenum", "valueuom", "flag", "label"]
#         table = "labevents"

#     if not rows:
#         return RetrievalResult([], [], [table])

#     r = dict(zip(cols, rows[0]))
#     return RetrievalResult([r], [Evidence(source_table=table, source_fields=r)], [table])


# # ============================================================================
# # measurements in a time range
# # ============================================================================

# def measurements_in_range(con, subject_id, hadm_id, stay_id, concept, domain,
#                            start: datetime | None, end: datetime | None):
#     itemid = get_concept_index().resolve(concept, domain or "lab")
#     if itemid is None:
#         return RetrievalResult([], [], [])

#     start = start or datetime.min
#     end = end or datetime.max

#     if domain == "icu_observation":
#         if stay_id is None:
#             return RetrievalResult([], [], ["icustays"])
#         rows = con.execute("""
#             SELECT c.subject_id, c.hadm_id, c.stay_id, c.itemid, c.charttime,
#                    c.value, c.valuenum, c.valueuom, d.label
#             FROM chartevents c
#             LEFT JOIN d_items d ON c.itemid = d.itemid
#             WHERE c.subject_id = ? AND c.stay_id = ? AND c.itemid = ?
#               AND c.charttime BETWEEN ? AND ?
#             ORDER BY c.charttime
#             LIMIT 200
#         """, [subject_id, stay_id, itemid, start, end]).fetchall()
#         cols = ["subject_id", "hadm_id", "stay_id", "itemid", "charttime",
#                 "value", "valuenum", "valueuom", "label"]
#         table = "chartevents"
#     else:
#         rows = con.execute("""
#             SELECT l.subject_id, l.hadm_id, l.itemid, l.charttime,
#                    l.value, l.valuenum, l.valueuom, l.flag, d.label
#             FROM labevents l
#             LEFT JOIN d_labitems d ON l.itemid = d.itemid
#             WHERE l.subject_id = ? AND l.hadm_id = ? AND l.itemid = ?
#               AND l.charttime BETWEEN ? AND ?
#             ORDER BY l.charttime
#             LIMIT 200
#         """, [subject_id, hadm_id, itemid, start, end]).fetchall()
#         cols = ["subject_id", "hadm_id", "itemid", "charttime",
#                 "value", "valuenum", "valueuom", "flag", "label"]
#         table = "labevents"

#     facts = [dict(zip(cols, row)) for row in rows]
#     evidence = [Evidence(source_table=table, source_fields=f) for f in facts]
#     return RetrievalResult(facts, evidence, [table])


# # ============================================================================
# # medications (eMAR)
# # ============================================================================

# def medications(con, subject_id, hadm_id, concept, start, end):
#     query = """
#         SELECT emar_id, subject_id, hadm_id, medication, charttime, event_txt
#         FROM emar
#         WHERE subject_id = ? AND hadm_id = ? AND charttime IS NOT NULL
#     """
#     params: list[Any] = [subject_id, hadm_id]

#     if concept:
#         query += " AND lower(medication) LIKE ?"
#         params.append(f"%{concept.lower()}%")
#     if start:
#         query += " AND charttime >= ?"
#         params.append(start)
#     if end:
#         query += " AND charttime <= ?"
#         params.append(end)

#     query += " ORDER BY charttime LIMIT 200"

#     rows = con.execute(query, params).fetchall()
#     cols = ["emar_id", "subject_id", "hadm_id", "medication", "charttime", "event_txt"]
#     facts = [dict(zip(cols, row)) for row in rows]
#     evidence = [Evidence(source_table="emar", source_fields=f) for f in facts]
#     return RetrievalResult(facts, evidence, ["emar"])


# # ============================================================================
# # procedures
# # ============================================================================

# def procedures(con, subject_id, hadm_id):
#     rows = con.execute("""
#         SELECT p.subject_id, p.hadm_id, p.seq_num, p.chartdate,
#                p.icd_code, p.icd_version, d.long_title
#         FROM procedures_icd p
#         LEFT JOIN d_icd_procedures d
#             ON p.icd_code = d.icd_code AND p.icd_version = d.icd_version
#         WHERE p.subject_id = ? AND p.hadm_id = ?
#         ORDER BY p.chartdate
#     """, [subject_id, hadm_id]).fetchall()
#     cols = ["subject_id", "hadm_id", "seq_num", "chartdate", "icd_code",
#             "icd_version", "long_title"]
#     facts = [dict(zip(cols, row)) for row in rows]
#     evidence = [Evidence(source_table="procedures_icd", source_fields=f) for f in facts]
#     return RetrievalResult(facts, evidence, ["procedures_icd"])


# # ============================================================================
# # transfers
# # ============================================================================

# def transfers(con, subject_id, hadm_id):
#     rows = con.execute("""
#         SELECT transfer_id, subject_id, hadm_id, eventtype, careunit, intime, outtime
#         FROM transfers
#         WHERE subject_id = ? AND hadm_id = ?
#         ORDER BY intime
#     """, [subject_id, hadm_id]).fetchall()
#     cols = ["transfer_id", "subject_id", "hadm_id", "eventtype", "careunit", "intime", "outtime"]
#     facts = [dict(zip(cols, row)) for row in rows]
#     evidence = [Evidence(source_table="transfers", source_fields=f) for f in facts]
#     return RetrievalResult(facts, evidence, ["transfers"])


# # ============================================================================
# # ICU stay info
# # ============================================================================

# def icu_stay_info(con, subject_id, hadm_id, stay_id):
#     query = (
#         "SELECT stay_id, subject_id, hadm_id, first_careunit, last_careunit, "
#         "intime, outtime, los FROM icustays WHERE subject_id = ? AND hadm_id = ?"
#     )
#     params: list[Any] = [subject_id, hadm_id]
#     if stay_id:
#         query += " AND stay_id = ?"
#         params.append(stay_id)

#     rows = con.execute(query, params).fetchall()
#     cols = ["stay_id", "subject_id", "hadm_id", "first_careunit", "last_careunit",
#             "intime", "outtime", "los"]
#     facts = [dict(zip(cols, row)) for row in rows]
#     evidence = [Evidence(source_table="icustays", source_fields=f) for f in facts]
#     return RetrievalResult(facts, evidence, ["icustays"])


# # ============================================================================
# # event count
# # ============================================================================

# TABLE_BY_DOMAIN = {
#     "lab": ("labevents", "hadm_id"),
#     "icu_observation": ("chartevents", "stay_id"),
#     "medication": ("emar", "hadm_id"),
#     "procedure": ("procedures_icd", "hadm_id"),
#     "transfer": ("transfers", "hadm_id"),
# }


# def event_count(con, subject_id, hadm_id, stay_id, domain):
#     if domain not in TABLE_BY_DOMAIN:
#         return RetrievalResult([], [], [])

#     table, scope_col = TABLE_BY_DOMAIN[domain]
#     scope_val = stay_id if scope_col == "stay_id" else hadm_id
#     if scope_val is None:
#         return RetrievalResult([], [], [table])

#     row = con.execute(
#         f"SELECT COUNT(*) FROM {table} WHERE subject_id = ? AND {scope_col} = ?",
#         [subject_id, scope_val],
#     ).fetchone()
#     count = row[0] if row else 0

#     fact = {"table": table, "count": count, "subject_id": subject_id, scope_col: scope_val}
#     evidence = [Evidence(source_table=table, source_fields=fact)] if count > 0 else []
#     return RetrievalResult([fact], evidence, [table])

"""
Deterministic, parameterized retrieval for TraceICU.

The LLM decides WHAT the user is asking for.

This module decides HOW to retrieve it.

Important guarantees:
---------------------
1. No model-generated SQL.
2. No model-generated table names.
3. No model-generated column names.
4. All user/model values are bound through DuckDB parameters.
5. ICU-scoped questions use icustays.intime/outtime.
6. Duplicate MIMIC itemids are handled correctly.
7. Every returned fact gets an Evidence object.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import duckdb

from app.models import Evidence
from app.ai.concepts import get_concept_index


# ============================================================================
# Result container
# ============================================================================


class RetrievalResult:
    def __init__(
        self,
        facts: list[dict[str, Any]],
        evidence: list[Evidence],
        searched_tables: list[str],
    ):
        self.facts = facts
        self.evidence = evidence
        self.searched_tables = searched_tables

    @property
    def has_evidence(self) -> bool:
        return bool(self.evidence)


# ============================================================================
# Generic helpers
# ============================================================================


def _result(
    table: str,
    facts: list[dict[str, Any]],
    *,
    searched_tables: list[str] | None = None,
) -> RetrievalResult:
    """
    Convert facts into Evidence objects consistently.
    """
    evidence = [
        Evidence(
            source_table=table,
            source_fields=fact,
        )
        for fact in facts
    ]

    return RetrievalResult(
        facts=facts,
        evidence=evidence,
        searched_tables=searched_tables or [table],
    )


def _placeholders(values: list[Any]) -> str:
    """
    Build a parameter placeholder list.

    Example:
        [1, 2, 3] -> "?, ?, ?"

    The values themselves are ALWAYS passed separately as bound
    parameters. Only the number of placeholders is generated here.
    """
    return ", ".join("?" for _ in values)


def _get_icu_window(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int | None,
    stay_id: int | None,
) -> tuple[datetime | None, datetime | None]:
    """
    Return ICU intime/outtime for the requested stay.

    If stay_id is supplied, it is authoritative.

    If stay_id is missing but hadm_id exists, use the most recent ICU
    stay for that admission.

    Returns:
        (intime, outtime)
    """
    if stay_id is not None:
        row = con.execute(
            """
            SELECT intime, outtime
            FROM icustays
            WHERE subject_id = ?
              AND stay_id = ?
            LIMIT 1
            """,
            [subject_id, stay_id],
        ).fetchone()

        if row:
            return row[0], row[1]

    if hadm_id is not None:
        row = con.execute(
            """
            SELECT intime, outtime
            FROM icustays
            WHERE subject_id = ?
              AND hadm_id = ?
            ORDER BY intime DESC
            LIMIT 1
            """,
            [subject_id, hadm_id],
        ).fetchone()

        if row:
            return row[0], row[1]

    return None, None


def _concept_itemids(
    concept: str | None,
    domain: str,
) -> list[int]:
    """
    Resolve a concept to ALL candidate MIMIC itemids.

    Returning [] means no concept could be resolved.
    """
    return get_concept_index().resolve_all(
        concept=concept,
        domain=domain,
    )


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
    Fill missing hadm_id / stay_id.

    Default:
        most recent admission
        -> most recent ICU stay inside that admission

    This keeps the existing TraceICU behavior while making the scope
    explicit in the returned QueryPlan.
    """
    if hadm_id is None:
        row = con.execute(
            """
            SELECT hadm_id
            FROM admissions
            WHERE subject_id = ?
            ORDER BY admittime DESC
            LIMIT 1
            """,
            [subject_id],
        ).fetchone()

        hadm_id = row[0] if row else None

    if stay_id is None and hadm_id is not None:
        row = con.execute(
            """
            SELECT stay_id
            FROM icustays
            WHERE subject_id = ?
              AND hadm_id = ?
            ORDER BY intime DESC
            LIMIT 1
            """,
            [subject_id, hadm_id],
        ).fetchone()

        stay_id = row[0] if row else None

    return hadm_id, stay_id


# ============================================================================
# First / last measurement
# ============================================================================


def measurement_extreme(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int | None,
    stay_id: int | None,
    concept: str | None,
    domain: str | None,
    which: str,
):
    """
    Retrieve the first or last measurement.

    Lab behavior:
        If an ICU stay exists, constrain charttime to ICU intime/outtime.

    ICU observation behavior:
        chartevents are already scoped by stay_id.

    Important improvement:
        concept=None is allowed for labs. This supports questions such
        as "What was the last laboratory event before ICU discharge?"
    """
    domain = (domain or "lab").casefold().strip()

    which = which.casefold().strip()

    if which not in {"first", "last"}:
        raise ValueError("which must be 'first' or 'last'")

    order = "ASC" if which == "first" else "DESC"

    # ------------------------------------------------------------------
    # ICU observations / chartevents
    # ------------------------------------------------------------------
    if domain == "icu_observation":
        if stay_id is None:
            return RetrievalResult(
                [],
                [],
                ["icustays", "chartevents"],
            )

        params: list[Any] = [
            subject_id,
            stay_id,
        ]

        where = """
            c.subject_id = ?
            AND c.stay_id = ?
            AND c.charttime IS NOT NULL
        """

        itemids = _concept_itemids(concept, domain)

        if concept and not itemids:
            return RetrievalResult(
                [],
                [],
                ["chartevents"],
            )

        if itemids:
            where += f" AND c.itemid IN ({_placeholders(itemids)})"
            params.extend(itemids)

        rows = con.execute(
            f"""
            SELECT
                c.subject_id,
                c.hadm_id,
                c.stay_id,
                c.itemid,
                c.charttime,
                c.value,
                c.valuenum,
                c.valueuom,
                d.label
            FROM chartevents c
            LEFT JOIN d_items d
                ON c.itemid = d.itemid
            WHERE {where}
            ORDER BY c.charttime {order}, c.itemid ASC
            LIMIT 1
            """,
            params,
        ).fetchall()

        cols = [
            "subject_id",
            "hadm_id",
            "stay_id",
            "itemid",
            "charttime",
            "value",
            "valuenum",
            "valueuom",
            "label",
        ]

        facts = [
            dict(zip(cols, row))
            for row in rows
        ]

        return _result(
            "chartevents",
            facts,
        )

    # ------------------------------------------------------------------
    # Laboratory events
    # ------------------------------------------------------------------

    if domain != "lab":
        return RetrievalResult([], [], [])

    params = [subject_id]

    where = """
        l.subject_id = ?
        AND l.charttime IS NOT NULL
    """

    if hadm_id is not None:
        where += " AND l.hadm_id = ?"
        params.append(hadm_id)

    itemids = _concept_itemids(concept, "lab")

    if concept and not itemids:
        return RetrievalResult(
            [],
            [],
            ["labevents", "d_labitems"],
        )

    if itemids:
        where += f" AND l.itemid IN ({_placeholders(itemids)})"
        params.extend(itemids)

    # If an ICU stay is known, enforce the actual ICU interval.
    #
    # This is the major temporal fix:
    #
    # old:
    #     entire admission
    #
    # new:
    #     ICU intime <= charttime <= ICU outtime
    #
    if stay_id is not None:
        where += """
            AND l.charttime >= (
                SELECT intime
                FROM icustays
                WHERE subject_id = ?
                  AND stay_id = ?
                LIMIT 1
            )
            AND l.charttime <= (
                SELECT outtime
                FROM icustays
                WHERE subject_id = ?
                  AND stay_id = ?
                LIMIT 1
            )
        """
        params.extend([
            subject_id,
            stay_id,
            subject_id,
            stay_id,
        ])

    rows = con.execute(
        f"""
        SELECT
            l.subject_id,
            l.hadm_id,
            l.itemid,
            l.charttime,
            l.value,
            l.valuenum,
            l.valueuom,
            l.flag,
            d.label
        FROM labevents l
        LEFT JOIN d_labitems d
            ON l.itemid = d.itemid
        WHERE {where}
        ORDER BY l.charttime {order}, l.itemid ASC
        LIMIT 1
        """,
        params,
    ).fetchall()

    cols = [
        "subject_id",
        "hadm_id",
        "itemid",
        "charttime",
        "value",
        "valuenum",
        "valueuom",
        "flag",
        "label",
    ]

    facts = [
        dict(zip(cols, row))
        for row in rows
    ]

    return _result(
        "labevents",
        facts,
    )


# ============================================================================
# Measurements in a time range
# ============================================================================


def measurements_in_range(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int | None,
    stay_id: int | None,
    concept: str | None,
    domain: str | None,
    start: datetime | None,
    end: datetime | None,
):
    """
    Retrieve measurements within a requested time range.

    If the question is scoped to an ICU stay, the requested range is
    additionally intersected with ICU intime/outtime.
    """
    domain = (domain or "lab").casefold().strip()

    start = start
    end = end

    # ------------------------------------------------------------------
    # ICU observations
    # ------------------------------------------------------------------
    if domain == "icu_observation":
        if stay_id is None:
            return RetrievalResult(
                [],
                [],
                ["icustays", "chartevents"],
            )

        params: list[Any] = [
            subject_id,
            stay_id,
        ]

        where = """
            c.subject_id = ?
            AND c.stay_id = ?
            AND c.charttime IS NOT NULL
        """

        itemids = _concept_itemids(concept, domain)

        if concept and not itemids:
            return RetrievalResult(
                [],
                [],
                ["chartevents"],
            )

        if itemids:
            where += f" AND c.itemid IN ({_placeholders(itemids)})"
            params.extend(itemids)

        if start is not None:
            where += " AND c.charttime >= ?"
            params.append(start)

        if end is not None:
            where += " AND c.charttime <= ?"
            params.append(end)

        rows = con.execute(
            f"""
            SELECT
                c.subject_id,
                c.hadm_id,
                c.stay_id,
                c.itemid,
                c.charttime,
                c.value,
                c.valuenum,
                c.valueuom,
                d.label
            FROM chartevents c
            LEFT JOIN d_items d
                ON c.itemid = d.itemid
            WHERE {where}
            ORDER BY c.charttime ASC, c.itemid ASC
            LIMIT 200
            """,
            params,
        ).fetchall()

        cols = [
            "subject_id",
            "hadm_id",
            "stay_id",
            "itemid",
            "charttime",
            "value",
            "valuenum",
            "valueuom",
            "label",
        ]

        facts = [
            dict(zip(cols, row))
            for row in rows
        ]

        return _result(
            "chartevents",
            facts,
        )

    # ------------------------------------------------------------------
    # Labs
    # ------------------------------------------------------------------

    if domain != "lab":
        return RetrievalResult([], [], [])

    params = [subject_id]

    where = """
        l.subject_id = ?
        AND l.charttime IS NOT NULL
    """

    if hadm_id is not None:
        where += " AND l.hadm_id = ?"
        params.append(hadm_id)

    itemids = _concept_itemids(concept, "lab")

    if concept and not itemids:
        return RetrievalResult(
            [],
            [],
            ["labevents", "d_labitems"],
        )

    if itemids:
        where += f" AND l.itemid IN ({_placeholders(itemids)})"
        params.extend(itemids)

    if start is not None:
        where += " AND l.charttime >= ?"
        params.append(start)

    if end is not None:
        where += " AND l.charttime <= ?"
        params.append(end)

    # Intersect explicit range with ICU stay when stay_id is known.
    if stay_id is not None:
        where += """
            AND l.charttime >= (
                SELECT intime
                FROM icustays
                WHERE subject_id = ?
                  AND stay_id = ?
                LIMIT 1
            )
            AND l.charttime <= (
                SELECT outtime
                FROM icustays
                WHERE subject_id = ?
                  AND stay_id = ?
                LIMIT 1
            )
        """
        params.extend([
            subject_id,
            stay_id,
            subject_id,
            stay_id,
        ])

    rows = con.execute(
        f"""
        SELECT
            l.subject_id,
            l.hadm_id,
            l.itemid,
            l.charttime,
            l.value,
            l.valuenum,
            l.valueuom,
            l.flag,
            d.label
        FROM labevents l
        LEFT JOIN d_labitems d
            ON l.itemid = d.itemid
        WHERE {where}
        ORDER BY l.charttime ASC, l.itemid ASC
        LIMIT 200
        """,
        params,
    ).fetchall()

    cols = [
        "subject_id",
        "hadm_id",
        "itemid",
        "charttime",
        "value",
        "valuenum",
        "valueuom",
        "flag",
        "label",
    ]

    facts = [
        dict(zip(cols, row))
        for row in rows
    ]

    return _result(
        "labevents",
        facts,
    )


# ============================================================================
# Medications / eMAR
# ============================================================================


def medications(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int | None,
    concept: str | None,
    start: datetime | None,
    end: datetime | None,
    stay_id: int | None = None,
    administered_only: bool = True,
):
    """
    Retrieve eMAR medication events.

    Default behavior is intentionally "administered only" because questions
    such as:

        "What was the first medication administered?"

    should not accidentally return held/cancelled/not-given events.

    stay_id is optional for backward compatibility with the existing main.py.
    If omitted, the most recent ICU stay for the admission is used when one
    exists.
    """
    if hadm_id is None:
        return RetrievalResult(
            [],
            [],
            ["emar"],
        )

    query = """
        SELECT
            e.mar_id AS emar_id,
            e.subject_id,
            e.hadm_id,
            e.medication,
            e.charttime,
            e.event_txt
        FROM emar e
        WHERE e.subject_id = ?
          AND e.hadm_id = ?
          AND e.charttime IS NOT NULL
    """

    params: list[Any] = [
        subject_id,
        hadm_id,
    ]

    # ------------------------------------------------------------
    # Medication concept filter
    # ------------------------------------------------------------
    if concept:
        query += """
            AND lower(e.medication) LIKE ?
        """
        params.append(
            f"%{concept.casefold().strip()}%"
        )

    # ------------------------------------------------------------
    # Administered-only filter
    # ------------------------------------------------------------
    if administered_only:
        query += """
            AND lower(trim(e.event_txt)) = 'administered'
        """

    # ------------------------------------------------------------
    # Explicit range
    # ------------------------------------------------------------
    if start is not None:
        query += " AND e.charttime >= ?"
        params.append(start)

    if end is not None:
        query += " AND e.charttime <= ?"
        params.append(end)

    # ------------------------------------------------------------
    # ICU scope
    #
    # If no stay_id is supplied, use the latest ICU stay in this
    # admission. This keeps compatibility with the current main.py.
    # ------------------------------------------------------------
    effective_stay_id = stay_id

    if effective_stay_id is None:
        row = con.execute(
            """
            SELECT stay_id
            FROM icustays
            WHERE subject_id = ?
              AND hadm_id = ?
            ORDER BY intime DESC
            LIMIT 1
            """,
            [subject_id, hadm_id],
        ).fetchone()

        if row:
            effective_stay_id = row[0]

    if effective_stay_id is not None:
        query += """
            AND e.charttime >= (
                SELECT intime
                FROM icustays
                WHERE subject_id = ?
                  AND stay_id = ?
                LIMIT 1
            )
            AND e.charttime <= (
                SELECT outtime
                FROM icustays
                WHERE subject_id = ?
                  AND stay_id = ?
                LIMIT 1
            )
        """

        params.extend([
            subject_id,
            effective_stay_id,
            subject_id,
            effective_stay_id,
        ])

    query += """
        ORDER BY e.charttime ASC, e.mar_id ASC
        LIMIT 200
    """

    rows = con.execute(query, params).fetchall()

    cols = [
        "emar_id",
        "subject_id",
        "hadm_id",
        "medication",
        "charttime",
        "event_txt",
    ]

    facts = [
        dict(zip(cols, row))
        for row in rows
    ]

    return _result(
        "emar",
        facts,
    )


# ============================================================================
# Procedures
# ============================================================================


def procedures(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int | None,
    which: str | None = None,
):
    """
    Retrieve ICD-coded procedures.

    which:
        None / "all" -> all procedures
        "first"      -> first procedure
        "last"       -> last procedure
    """
    if hadm_id is None:
        return RetrievalResult(
            [],
            [],
            ["procedures_icd"],
        )

    which = (which or "all").casefold().strip()

    if which not in {"all", "first", "last"}:
        raise ValueError(
            "which must be 'all', 'first', or 'last'"
        )

    order = "ASC" if which != "last" else "DESC"

    limit_clause = ""

    if which in {"first", "last"}:
        limit_clause = "LIMIT 1"

    rows = con.execute(
        f"""
        SELECT
            p.subject_id,
            p.hadm_id,
            p.seq_num,
            p.chartdate,
            p.icd_code,
            p.icd_version,
            d.long_title
        FROM procedures_icd p
        LEFT JOIN d_icd_procedures d
            ON p.icd_code = d.icd_code
           AND p.icd_version = d.icd_version
        WHERE p.subject_id = ?
          AND p.hadm_id = ?
        ORDER BY
            p.chartdate {order},
            p.seq_num ASC
        {limit_clause}
        """,
        [subject_id, hadm_id],
    ).fetchall()

    cols = [
        "subject_id",
        "hadm_id",
        "seq_num",
        "chartdate",
        "icd_code",
        "icd_version",
        "long_title",
    ]

    facts = [
        dict(zip(cols, row))
        for row in rows
    ]

    return _result(
        "procedures_icd",
        facts,
    )


# ============================================================================
# Transfers
# ============================================================================


def transfers(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int | None,
    which: str | None = None,
):
    """
    Retrieve admission transfer history.

    which:
        None / "all" -> all transfers
        "first"      -> first transfer
        "last"       -> last transfer
    """
    if hadm_id is None:
        return RetrievalResult(
            [],
            [],
            ["transfers"],
        )

    which = (which or "all").casefold().strip()

    if which not in {"all", "first", "last"}:
        raise ValueError(
            "which must be 'all', 'first', or 'last'"
        )

    order = "ASC" if which != "last" else "DESC"

    limit_clause = ""

    if which in {"first", "last"}:
        limit_clause = "LIMIT 1"

    rows = con.execute(
        f"""
        SELECT
            transfer_id,
            subject_id,
            hadm_id,
            eventtype,
            careunit,
            intime,
            outtime
        FROM transfers
        WHERE subject_id = ?
          AND hadm_id = ?
        ORDER BY
            intime {order},
            transfer_id ASC
        {limit_clause}
        """,
        [subject_id, hadm_id],
    ).fetchall()

    cols = [
        "transfer_id",
        "subject_id",
        "hadm_id",
        "eventtype",
        "careunit",
        "intime",
        "outtime",
    ]

    facts = [
        dict(zip(cols, row))
        for row in rows
    ]

    return _result(
        "transfers",
        facts,
    )


# ============================================================================
# ICU stay information
# ============================================================================


def icu_stay_info(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int | None,
    stay_id: int | None,
):
    """
    Return ICU stay metadata.

    If stay_id is provided, return that exact stay.
    Otherwise return the most recent ICU stay for the admission.
    """
    if hadm_id is None:
        return RetrievalResult(
            [],
            [],
            ["icustays"],
        )

    query = """
        SELECT
            stay_id,
            subject_id,
            hadm_id,
            first_careunit,
            last_careunit,
            intime,
            outtime,
            los
        FROM icustays
        WHERE subject_id = ?
          AND hadm_id = ?
    """

    params: list[Any] = [
        subject_id,
        hadm_id,
    ]

    if stay_id is not None:
        query += """
            AND stay_id = ?
        """
        params.append(stay_id)
    else:
        query += """
            ORDER BY intime DESC
            LIMIT 1
        """

    rows = con.execute(
        query,
        params,
    ).fetchall()

    cols = [
        "stay_id",
        "subject_id",
        "hadm_id",
        "first_careunit",
        "last_careunit",
        "intime",
        "outtime",
        "los",
    ]

    facts = [
        dict(zip(cols, row))
        for row in rows
    ]

    return _result(
        "icustays",
        facts,
    )


# ============================================================================
# Event count
# ============================================================================


TABLE_BY_DOMAIN = {
    "lab": ("labevents", "hadm_id"),
    "icu_observation": ("chartevents", "stay_id"),
    "medication": ("emar", "hadm_id"),
    "procedure": ("procedures_icd", "hadm_id"),
    "transfer": ("transfers", "hadm_id"),
}


def event_count(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int | None,
    stay_id: int | None,
    domain: str | None,
):
    """
    Count events for a supported domain.

    Important scope behavior:

    lab:
        If stay_id exists, count only labevents inside ICU intime/outtime.

    medication:
        Count administered eMAR events inside ICU intime/outtime when
        stay_id exists.

    chartevents:
        Already scoped directly by stay_id.

    procedures/transfers:
        Scoped to admission because their source tables are admission-level.
    """
    domain = (domain or "").casefold().strip()

    if domain not in TABLE_BY_DOMAIN:
        return RetrievalResult(
            [],
            [],
            [],
        )

    table, scope_col = TABLE_BY_DOMAIN[domain]

    # ------------------------------------------------------------------
    # ICU observations
    # ------------------------------------------------------------------
    if domain == "icu_observation":
        if stay_id is None:
            return RetrievalResult(
                [],
                [],
                ["chartevents", "icustays"],
            )

        row = con.execute(
            """
            SELECT COUNT(*)
            FROM chartevents
            WHERE subject_id = ?
              AND stay_id = ?
            """,
            [subject_id, stay_id],
        ).fetchone()

        count = int(row[0]) if row else 0

        fact = {
            "table": "chartevents",
            "count": count,
            "subject_id": subject_id,
            "stay_id": stay_id,
        }

        # A count of zero is still useful evidence that the query was
        # executed correctly, but the current answer.py treats evidence
        # as support. Preserve old behavior by only creating evidence
        # when rows exist.
        evidence = (
            [
                Evidence(
                    source_table="chartevents",
                    source_fields=fact,
                )
            ]
            if count > 0
            else []
        )

        return RetrievalResult(
            [fact],
            evidence,
            ["chartevents"],
        )

    # ------------------------------------------------------------------
    # Labs
    # ------------------------------------------------------------------
    if domain == "lab":
        if hadm_id is None:
            return RetrievalResult(
                [],
                [],
                ["labevents"],
            )

        query = """
            SELECT COUNT(*)
            FROM labevents l
            WHERE l.subject_id = ?
              AND l.hadm_id = ?
        """

        params: list[Any] = [
            subject_id,
            hadm_id,
        ]

        if stay_id is not None:
            query += """
                AND l.charttime IS NOT NULL
                AND l.charttime >= (
                    SELECT intime
                    FROM icustays
                    WHERE subject_id = ?
                      AND stay_id = ?
                    LIMIT 1
                )
                AND l.charttime <= (
                    SELECT outtime
                    FROM icustays
                    WHERE subject_id = ?
                      AND stay_id = ?
                    LIMIT 1
                )
            """

            params.extend([
                subject_id,
                stay_id,
                subject_id,
                stay_id,
            ])

        row = con.execute(
            query,
            params,
        ).fetchone()

        count = int(row[0]) if row else 0

        fact = {
            "table": "labevents",
            "count": count,
            "subject_id": subject_id,
            "hadm_id": hadm_id,
        }

        if stay_id is not None:
            fact["stay_id"] = stay_id
            fact["scope"] = "icu_stay"

        evidence = (
            [
                Evidence(
                    source_table="labevents",
                    source_fields=fact,
                )
            ]
            if count > 0
            else []
        )

        return RetrievalResult(
            [fact],
            evidence,
            ["labevents"],
        )

    # ------------------------------------------------------------------
    # Medications
    # ------------------------------------------------------------------
    if domain == "medication":
        if hadm_id is None:
            return RetrievalResult(
                [],
                [],
                ["emar"],
            )

        query = """
            SELECT COUNT(*)
            FROM emar e
            WHERE e.subject_id = ?
              AND e.hadm_id = ?
              AND e.charttime IS NOT NULL
              AND lower(trim(e.event_txt)) = 'administered'
        """

        params = [
            subject_id,
            hadm_id,
        ]

        effective_stay_id = stay_id

        if effective_stay_id is None:
            row = con.execute(
                """
                SELECT stay_id
                FROM icustays
                WHERE subject_id = ?
                  AND hadm_id = ?
                ORDER BY intime DESC
                LIMIT 1
                """,
                [subject_id, hadm_id],
            ).fetchone()

            if row:
                effective_stay_id = row[0]

        if effective_stay_id is not None:
            query += """
                AND e.charttime >= (
                    SELECT intime
                    FROM icustays
                    WHERE subject_id = ?
                      AND stay_id = ?
                    LIMIT 1
                )
                AND e.charttime <= (
                    SELECT outtime
                    FROM icustays
                    WHERE subject_id = ?
                      AND stay_id = ?
                    LIMIT 1
                )
            """

            params.extend([
                subject_id,
                effective_stay_id,
                subject_id,
                effective_stay_id,
            ])

        row = con.execute(
            query,
            params,
        ).fetchone()

        count = int(row[0]) if row else 0

        fact = {
            "table": "emar",
            "count": count,
            "subject_id": subject_id,
            "hadm_id": hadm_id,
            "event_filter": "Administered",
        }

        if effective_stay_id is not None:
            fact["stay_id"] = effective_stay_id
            fact["scope"] = "icu_stay"

        evidence = (
            [
                Evidence(
                    source_table="emar",
                    source_fields=fact,
                )
            ]
            if count > 0
            else []
        )

        return RetrievalResult(
            [fact],
            evidence,
            ["emar"],
        )

    # ------------------------------------------------------------------
    # Procedures / transfers
    # ------------------------------------------------------------------
    scope_val = hadm_id

    if scope_val is None:
        return RetrievalResult(
            [],
            [],
            [table],
        )

    row = con.execute(
        f"""
        SELECT COUNT(*)
        FROM {table}
        WHERE subject_id = ?
          AND {scope_col} = ?
        """,
        [subject_id, scope_val],
    ).fetchone()

    count = int(row[0]) if row else 0

    fact = {
        "table": table,
        "count": count,
        "subject_id": subject_id,
        scope_col: scope_val,
    }

    evidence = (
        [
            Evidence(
                source_table=table,
                source_fields=fact,
            )
        ]
        if count > 0
        else []
    )

    return RetrievalResult(
        [fact],
        evidence,
        [table],
    )