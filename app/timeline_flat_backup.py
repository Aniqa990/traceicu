"""
Patient timeline reconstruction for MIMIC-IV.

Public entry point:
    get_patient_timeline(con, subject_id)

The timeline is reconstructed from the tables already loaded into
database/mimic.duckdb.

Included tables:
    - patients
    - admissions
    - transfers
    - labevents
    - d_labitems
    - emar
    - procedures_icd
    - d_icd_procedures
    - icustays
    - chartevents
    - d_items

The timeline contains:
    - Admission / discharge events
    - Transfer events
    - Laboratory events
    - Medication administration events from eMAR
    - Procedure events
    - ICU stay events
    - ICU observation events from chartevents

High-volume laboratory and ICU observation events are clustered by
time proximity.

Pagination is handled by the API layer after the complete timeline
has been reconstructed and sorted.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import duckdb

from app.config import CLUSTER_WINDOW_MINUTES, MAX_ICU_OBSERVATIONS
from app.models import Event, Evidence, Timeline


class ScopeNotFoundError(ValueError):
    """Raised when the requested subject_id does not exist."""


# ==========================================================================
# Helpers
# ==========================================================================

def _to_dt(value) -> datetime | None:
    """Convert DuckDB date/datetime values to datetime."""

    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return datetime(
            value.year,
            value.month,
            value.day,
        )

    return None


# ==========================================================================
# Admission events
# ==========================================================================

def _admission_events(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int,
) -> list[Event]:

    rows = con.execute(
        """
        SELECT
            hadm_id,
            admittime,
            dischtime,
            admission_type,
            admission_location,
            discharge_location,
            insurance,
            hospital_expire_flag
        FROM admissions
        WHERE subject_id = ?
          AND hadm_id = ?
        """,
        [subject_id, hadm_id],
    ).fetchall()

    columns = [
        "hadm_id",
        "admittime",
        "dischtime",
        "admission_type",
        "admission_location",
        "discharge_location",
        "insurance",
        "hospital_expire_flag",
    ]

    events = []

    for row in rows:

        r = dict(zip(columns, row))

        evidence = [
            Evidence(
                source_table="admissions",
                source_fields=r,
            )
        ]

        # Admission event
        events.append(
            Event(
                event_id=f"admission-start-{r['hadm_id']}",
                subject_id=subject_id,
                hadm_id=r["hadm_id"],
                event_time=_to_dt(r["admittime"]),
                event_type="ADMISSION",
                event_subtype=r.get("admission_type"),
                label=(
                    f"Admitted "
                    f"({r.get('admission_type') or 'unknown type'})"
                ),
                value=r.get("admission_location"),
                evidence=evidence,
            )
        )

        # Discharge event
        if r.get("dischtime") is not None:

            events.append(
                Event(
                    event_id=f"admission-end-{r['hadm_id']}",
                    subject_id=subject_id,
                    hadm_id=r["hadm_id"],
                    event_time=_to_dt(r["dischtime"]),
                    event_type="DISCHARGE",
                    label=(
                        "Discharged"
                        + (
                            " (expired)"
                            if r.get("hospital_expire_flag")
                            else ""
                        )
                    ),
                    value=r.get("discharge_location"),
                    evidence=evidence,
                )
            )

    return events


# ==========================================================================
# Transfer events
# ==========================================================================

def _transfer_events(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int,
) -> list[Event]:

    rows = con.execute(
        """
        SELECT
            transfer_id,
            eventtype,
            careunit,
            intime,
            outtime
        FROM transfers
        WHERE subject_id = ?
          AND hadm_id = ?
        ORDER BY intime
        """,
        [subject_id, hadm_id],
    ).fetchall()

    columns = [
        "transfer_id",
        "eventtype",
        "careunit",
        "intime",
        "outtime",
    ]

    events = []

    for row in rows:

        r = dict(zip(columns, row))

        events.append(
            Event(
                event_id=f"transfer-{r['transfer_id']}",
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_time=_to_dt(r["intime"]),
                event_end_time=_to_dt(r["outtime"]),
                event_type="TRANSFER",
                event_subtype=r.get("eventtype"),
                label=(
                    r.get("careunit")
                    or r.get("eventtype")
                    or "transfer"
                ),
                evidence=[
                    Evidence(
                        source_table="transfers",
                        source_fields=r,
                    )
                ],
            )
        )

    return events


# ==========================================================================
# Laboratory events
# ==========================================================================

def _lab_events(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int,
) -> list[Event]:

    rows = con.execute(
        """
        SELECT
            l.labevent_id,
            l.itemid,
            l.charttime,
            l.value,
            l.valuenum,
            l.valueuom,
            l.ref_range_lower,
            l.ref_range_upper,
            l.flag,
            d.label
        FROM labevents l
        LEFT JOIN d_labitems d
            ON l.itemid = d.itemid
        WHERE l.subject_id = ?
          AND l.hadm_id = ?
          AND l.charttime IS NOT NULL
        ORDER BY l.charttime
        """,
        [subject_id, hadm_id],
    ).fetchall()

    columns = [
        "labevent_id",
        "itemid",
        "charttime",
        "value",
        "valuenum",
        "valueuom",
        "ref_range_lower",
        "ref_range_upper",
        "flag",
        "label",
    ]

    events = []

    for row in rows:

        r = dict(zip(columns, row))

        value = (
            r.get("value")
            if r.get("valuenum") is None
            else str(r.get("valuenum"))
        )

        events.append(
            Event(
                event_id=f"lab-{r['labevent_id']}",
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_time=_to_dt(r["charttime"]),
                event_type="LAB",
                event_subtype=(
                    "abnormal"
                    if r.get("flag")
                    else "normal"
                ),
                label=(
                    r.get("label")
                    or f"itemid {r['itemid']}"
                ),
                value=value,
                unit=r.get("valueuom"),
                evidence=[
                    Evidence(
                        source_table="labevents",
                        source_fields=r,
                    )
                ],
            )
        )

    return events


# ==========================================================================
# eMAR medication events
# ==========================================================================

def _emar_events(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int,
) -> list[Event]:

    """
    Reconstruct medication administration/documentation events from eMAR.

    MIMIC-IV eMAR does not contain an event_type column. The event_txt
    column describes the medication administration/documentation event,
    so it is used as the event subtype.
    """

    rows = con.execute(
        """
        SELECT
            emar_id,
            medication,
            charttime,
            event_txt,
            scheduletime,
            storetime,
            enter_provider_id,
            emar_seq,
            poe_id,
            pharmacy_id
        FROM emar
        WHERE subject_id = ?
          AND hadm_id = ?
          AND charttime IS NOT NULL
        ORDER BY charttime
        """,
        [subject_id, hadm_id],
    ).fetchall()

    columns = [
        "emar_id",
        "medication",
        "charttime",
        "event_txt",
        "scheduletime",
        "storetime",
        "enter_provider_id",
        "emar_seq",
        "poe_id",
        "pharmacy_id",
    ]

    events = []

    for row in rows:

        r = dict(zip(columns, row))

        events.append(
            Event(
                event_id=f"emar-{r['emar_id']}",
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_time=_to_dt(r["charttime"]),
                event_type="MEDICATION_ADMIN",
                event_subtype=r.get("event_txt"),
                label=(
                    r.get("medication")
                    or "medication"
                ),
                value=r.get("event_txt"),
                evidence=[
                    Evidence(
                        source_table="emar",
                        source_fields=r,
                    )
                ],
            )
        )

    return events

# ==========================================================================
# Procedure events
# ==========================================================================

def _procedure_events(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int,
) -> list[Event]:

    rows = con.execute(
        """
        SELECT
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
        ORDER BY p.chartdate
        """,
        [subject_id, hadm_id],
    ).fetchall()

    columns = [
        "seq_num",
        "chartdate",
        "icd_code",
        "icd_version",
        "long_title",
    ]

    events = []

    for row in rows:

        r = dict(zip(columns, row))

        events.append(
            Event(
                event_id=(
                    f"proc-{hadm_id}-{r['seq_num']}"
                ),
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_time=_to_dt(r["chartdate"]),
                event_type="PROCEDURE",
                event_subtype=(
                    f"ICD-{r.get('icd_version')}"
                ),
                label=(
                    r.get("long_title")
                    or r.get("icd_code")
                ),
                value=r.get("icd_code"),
                evidence=[
                    Evidence(
                        source_table="procedures_icd",
                        source_fields=r,
                    )
                ],
            )
        )

    return events


# ==========================================================================
# ICU stay events
# ==========================================================================

def _icu_stay_events(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    hadm_id: int,
) -> tuple[list[Event], list[int]]:

    rows = con.execute(
        """
        SELECT
            stay_id,
            first_careunit,
            last_careunit,
            intime,
            outtime,
            los
        FROM icustays
        WHERE subject_id = ?
          AND hadm_id = ?
        ORDER BY intime
        """,
        [subject_id, hadm_id],
    ).fetchall()

    columns = [
        "stay_id",
        "first_careunit",
        "last_careunit",
        "intime",
        "outtime",
        "los",
    ]

    events = []
    stay_ids = []

    for row in rows:

        r = dict(zip(columns, row))

        stay_id = r["stay_id"]

        stay_ids.append(stay_id)

        events.append(
            Event(
                event_id=f"icu-start-{stay_id}",
                subject_id=subject_id,
                hadm_id=hadm_id,
                stay_id=stay_id,
                event_time=_to_dt(r["intime"]),
                event_type="ICU_STAY",
                event_subtype="admission",
                label=(
                    f"ICU admission "
                    f"({r.get('first_careunit')})"
                ),
                evidence=[
                    Evidence(
                        source_table="icustays",
                        source_fields=r,
                    )
                ],
            )
        )

        if r.get("outtime") is not None:

            events.append(
                Event(
                    event_id=f"icu-end-{stay_id}",
                    subject_id=subject_id,
                    hadm_id=hadm_id,
                    stay_id=stay_id,
                    event_time=_to_dt(r["outtime"]),
                    event_type="ICU_STAY",
                    event_subtype="discharge",
                    label=(
                        f"ICU discharge "
                        f"({r.get('last_careunit')})"
                    ),
                    evidence=[
                        Evidence(
                            source_table="icustays",
                            source_fields=r,
                        )
                    ],
                )
            )

    return events, stay_ids


# ==========================================================================
# ICU observation events
# ==========================================================================

def _icu_observation_events(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
    stay_id: int,
) -> tuple[list[Event], bool]:

    rows = con.execute(
        """
        SELECT
            c.charttime,
            c.itemid,
            c.value,
            c.valuenum,
            c.valueuom,
            c.warning,
            d.label,
            d.category
        FROM chartevents c
        LEFT JOIN d_items d
            ON c.itemid = d.itemid
        WHERE c.subject_id = ?
          AND c.stay_id = ?
          AND c.charttime IS NOT NULL
        ORDER BY c.charttime
        LIMIT ?
        """,
        [
            subject_id,
            stay_id,
            MAX_ICU_OBSERVATIONS + 1,
        ],
    ).fetchall()

    truncated = (
        len(rows) > MAX_ICU_OBSERVATIONS
    )

    rows = rows[:MAX_ICU_OBSERVATIONS]

    columns = [
        "charttime",
        "itemid",
        "value",
        "valuenum",
        "valueuom",
        "warning",
        "label",
        "category",
    ]

    events = []

    for index, row in enumerate(rows):

        r = dict(zip(columns, row))

        value = (
            r.get("value")
            if r.get("valuenum") is None
            else str(r.get("valuenum"))
        )

        events.append(
            Event(
                event_id=(
                    f"chart-{stay_id}-"
                    f"{index}-{r['itemid']}"
                ),
                subject_id=subject_id,
                stay_id=stay_id,
                event_time=_to_dt(r["charttime"]),
                event_type="ICU_OBSERVATION",
                event_subtype=r.get("category"),
                label=(
                    r.get("label")
                    or f"itemid {r['itemid']}"
                ),
                value=value,
                unit=r.get("valueuom"),
                evidence=[
                    Evidence(
                        source_table="chartevents",
                        source_fields=r,
                    )
                ],
            )
        )

    return events, truncated


# ==========================================================================
# Event clustering
# ==========================================================================

def _cluster_by_time(
    events: list[Event],
    cluster_type: str,
    window_minutes: int = CLUSTER_WINDOW_MINUTES,
) -> list[Event]:

    """
    Cluster consecutive events that occur within the configured
    time window.

    Original events remain inside the cluster's children field so
    no underlying evidence is lost.
    """

    if not events:
        return []

    timed = sorted(
        [
            event
            for event in events
            if event.event_time is not None
        ],
        key=lambda event: event.event_time,
    )

    untimed = [
        event
        for event in events
        if event.event_time is None
    ]

    clusters: list[list[Event]] = []
    current: list[Event] = []

    for event in timed:

        if (
            current
            and (
                event.event_time
                - current[-1].event_time
            )
            > timedelta(
                minutes=window_minutes
            )
        ):
            clusters.append(current)
            current = []

        current.append(event)

    if current:
        clusters.append(current)

    grouped: list[Event] = []

    for cluster in clusters:

        if len(cluster) == 1:
            grouped.append(cluster[0])
            continue

        grouped.append(
            Event(
                event_id=(
                    f"{cluster_type.lower()}-cluster-"
                    f"{cluster[0].event_id}"
                ),
                subject_id=cluster[0].subject_id,
                hadm_id=cluster[0].hadm_id,
                stay_id=cluster[0].stay_id,
                event_time=cluster[0].event_time,
                event_end_time=cluster[-1].event_time,
                event_type=(
                    f"{cluster_type}_CLUSTER"
                ),
                label=(
                    f"{cluster_type.title().replace('_', ' ')} "
                    f"cluster ({len(cluster)} observations)"
                ),
                is_derived=True,
                derivation_rule=(
                    f"Grouped {len(cluster)} "
                    f"{cluster_type} events occurring "
                    f"within {window_minutes}-minute "
                    f"windows of one another."
                ),
                children=cluster,
            )
        )

    return grouped + untimed


# ==========================================================================
# Public timeline function
# ==========================================================================

def get_patient_timeline(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
) -> Timeline:

    """
    Reconstruct the complete timeline for a patient.

    The public function intentionally accepts only subject_id.

    All hospital admissions belonging to that patient are included.
    """

    # ----------------------------------------------------------------------
    # Validate patient
    # ----------------------------------------------------------------------

    patient = con.execute(
        """
        SELECT subject_id
        FROM patients
        WHERE subject_id = ?
        """,
        [subject_id],
    ).fetchone()

    if patient is None:
        raise ScopeNotFoundError(
            f"No patient found with subject_id={subject_id}"
        )

    # ----------------------------------------------------------------------
    # Get all admissions for the patient
    # ----------------------------------------------------------------------

    admission_rows = con.execute(
        """
        SELECT hadm_id
        FROM admissions
        WHERE subject_id = ?
        ORDER BY admittime
        """,
        [subject_id],
    ).fetchall()

    hadm_ids = [
        row[0]
        for row in admission_rows
    ]

    events: list[Event] = []

    # ----------------------------------------------------------------------
    # Process every admission
    # ----------------------------------------------------------------------

    for hadm_id in hadm_ids:

        # Admission
        events.extend(
            _admission_events(
                con,
                subject_id,
                hadm_id,
            )
        )

        # Transfers
        events.extend(
            _transfer_events(
                con,
                subject_id,
                hadm_id,
            )
        )

        # Medication administration
        events.extend(
            _emar_events(
                con,
                subject_id,
                hadm_id,
            )
        )

        # Procedures
        events.extend(
            _procedure_events(
                con,
                subject_id,
                hadm_id,
            )
        )

        # ------------------------------------------------------------------
        # Laboratory events
        # ------------------------------------------------------------------

        labs = _lab_events(
            con,
            subject_id,
            hadm_id,
        )

        events.extend(
            _cluster_by_time(
                labs,
                "LAB",
            )
        )

        # ------------------------------------------------------------------
        # ICU events
        # ------------------------------------------------------------------

        icu_events, stay_ids = _icu_stay_events(
            con,
            subject_id,
            hadm_id,
        )

        events.extend(icu_events)

        # ------------------------------------------------------------------
        # ICU observations
        # ------------------------------------------------------------------

        for stay_id in stay_ids:

            observations, truncated = (
                _icu_observation_events(
                    con,
                    subject_id,
                    stay_id,
                )
            )

            clustered = _cluster_by_time(
                observations,
                "ICU_OBSERVATION",
            )

            if truncated:

                for event in clustered:

                    event.derivation_rule = (
                        (event.derivation_rule or "")
                        + (
                            f" [NOTE: capped at "
                            f"{MAX_ICU_OBSERVATIONS} "
                            f"observations for "
                            f"stay_id={stay_id}; "
                            f"more observations exist.]"
                        )
                    ).strip()

            events.extend(clustered)

    # ----------------------------------------------------------------------
    # Sort final timeline chronologically
    # ----------------------------------------------------------------------

    events.sort(
        key=lambda event: (
            event.event_time or datetime.max,
            event.event_type,
            event.event_id,
        )
    )

    # ----------------------------------------------------------------------
    # Return Timeline model
    # ----------------------------------------------------------------------

    return Timeline(
        subject_id=subject_id,
        hadm_id=None,
        stay_id=None,
        events=events,
        event_count=sum(
            _count(event)
            for event in events
        ),
        tables_used=[
            "patients",
            "admissions",
            "transfers",
            "labevents",
            "d_labitems",
            "emar",
            "procedures_icd",
            "d_icd_procedures",
            "icustays",
            "chartevents",
            "d_items",
        ],
        empty_sources=[],
    )


# ==========================================================================
# Event counting
# ==========================================================================

def _count(event: Event) -> int:
    """
    Count an event and all of its child events.

    This means event_count represents both:
        - top-level timeline events
        - underlying events preserved inside clusters
    """

    return (
        1
        + sum(
            _count(child)
            for child in event.children
        )
    )