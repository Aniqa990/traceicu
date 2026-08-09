"""
Subject search and overview queries for the search page and the
timeline page header.

These intentionally never touch the high-volume tables (labevents /
chartevents / emar) with anything but COUNT(*), so they stay fast even
though the full timeline reconstruction (app/timeline.py) is never
invoked here.
"""
from __future__ import annotations

import duckdb
from pydantic import BaseModel


class SubjectSearchResult(BaseModel):
    subject_id: int
    gender: str | None = None
    anchor_age: int | None = None
    admission_count: int
    icu_stay_count: int


class EncounterSummary(BaseModel):
    hadm_id: int
    admittime: str | None = None
    dischtime: str | None = None
    admission_type: str | None = None
    admission_location: str | None = None
    discharge_location: str | None = None
    icu_stay_count: int


class SubjectOverview(BaseModel):
    subject_id: int
    gender: str | None = None
    anchor_age: int | None = None
    anchor_year_group: str | None = None
    encounters: list[EncounterSummary]


def search_subjects(
    con: duckdb.DuckDBPyConnection,
    q: str,
    limit: int = 10,
) -> list[SubjectSearchResult]:
    """
    MIMIC demo subject_ids are 8-digit integers with no other
    searchable identifying text (names are de-identified out), so
    "search" here means numeric prefix match on subject_id, not a
    text search.
    """
    q = q.strip()
    if not q or not q.isdigit():
        return []

    rows = con.execute(
        """
        SELECT
            p.subject_id,
            p.gender,
            p.anchor_age,
            COUNT(DISTINCT a.hadm_id) AS admission_count,
            COUNT(DISTINCT i.stay_id) AS icu_stay_count
        FROM patients p
        LEFT JOIN admissions a ON a.subject_id = p.subject_id
        LEFT JOIN icustays i ON i.subject_id = p.subject_id
        WHERE CAST(p.subject_id AS VARCHAR) LIKE ? || '%'
        GROUP BY p.subject_id, p.gender, p.anchor_age
        ORDER BY p.subject_id
        LIMIT ?
        """,
        [q, limit],
    ).fetchall()

    return [
        SubjectSearchResult(
            subject_id=r[0],
            gender=r[1],
            anchor_age=r[2],
            admission_count=r[3],
            icu_stay_count=r[4],
        )
        for r in rows
    ]


def get_subject_overview(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
) -> SubjectOverview | None:

    patient = con.execute(
        """
        SELECT subject_id, gender, anchor_age, anchor_year_group
        FROM patients
        WHERE subject_id = ?
        """,
        [subject_id],
    ).fetchone()

    if patient is None:
        return None

    encounters = con.execute(
        """
        SELECT
            a.hadm_id,
            a.admittime,
            a.dischtime,
            a.admission_type,
            a.admission_location,
            a.discharge_location,
            COUNT(DISTINCT i.stay_id) AS icu_stay_count
        FROM admissions a
        LEFT JOIN icustays i
            ON i.subject_id = a.subject_id
           AND i.hadm_id = a.hadm_id
        WHERE a.subject_id = ?
        GROUP BY
            a.hadm_id, a.admittime, a.dischtime,
            a.admission_type, a.admission_location, a.discharge_location
        ORDER BY a.admittime
        """,
        [subject_id],
    ).fetchall()

    return SubjectOverview(
        subject_id=patient[0],
        gender=patient[1],
        anchor_age=patient[2],
        anchor_year_group=patient[3],
        encounters=[
            EncounterSummary(
                hadm_id=e[0],
                admittime=str(e[1]) if e[1] is not None else None,
                dischtime=str(e[2]) if e[2] is not None else None,
                admission_type=e[3],
                admission_location=e[4],
                discharge_location=e[5],
                icu_stay_count=e[6],
            )
            for e in encounters
        ],
    )