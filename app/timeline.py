"""
Hierarchical patient timeline reconstruction for MIMIC-IV.

Public entry point:
    get_patient_timeline(con, subject_id)

The timeline is reconstructed from the tables already loaded into
database/mimic.duckdb.

Hierarchy:

    Patient Journey
    ├── Admission
    ├── Transfer
    ├── ICU Stay
    │   ├── Labs
    │   │   └── individual lab events
    │   ├── ICU observations
    │   │   └── individual observation events
    │   └── Medications
    │       └── individual medication events
    ├── Procedure
    └── Discharge

Important:
    - No timeline table is created in DuckDB.
    - Source rows remain the source of truth.
    - Derived category groups use Event.children.
    - Every individual event retains its Evidence.
    - Labs and medications are associated with an ICU stay by
      checking whether their event time falls within the ICU stay.
    - Events outside an ICU stay remain top-level journey events.
"""

from __future__ import annotations

from datetime import date, datetime

import duckdb

from app.config import MAX_ICU_OBSERVATIONS
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


def _event_inside_icu(
    event: Event,
    icu_event: Event,
) -> bool:
    """
    Return True when an event belongs inside an ICU stay.

    An event belongs to the ICU stay when its event_time falls between
    the ICU admission and discharge timestamps.

    If the ICU discharge time is missing, the ICU stay is treated as
    open-ended.
    """

    if event.event_time is None:
        return False

    if icu_event.event_time is None:
        return False

    if event.event_time < icu_event.event_time:
        return False

    if (
        icu_event.event_end_time is not None
        and event.event_time > icu_event.event_end_time
    ):
        return False

    return True


def _make_category_cluster(
    *,
    subject_id: int,
    hadm_id: int,
    stay_id: int,
    event_type: str,
    label: str,
    events: list[Event],
) -> Event | None:
    """
    Create a semantic category group.

    Example:

        Labs · 142
            ├── Sodium
            ├── WBC
            └── ...

    The individual source events remain untouched in children.
    """

    if not events:
        return None

    events = sorted(
        events,
        key=lambda event: (
            event.event_time or datetime.max,
            event.event_id,
        ),
    )

    return Event(
        event_id=(
            f"{event_type.lower()}-"
            f"{hadm_id}-"
            f"{stay_id}"
        ),
        subject_id=subject_id,
        hadm_id=hadm_id,
        stay_id=stay_id,
        event_time=events[0].event_time,
        event_end_time=events[-1].event_time,
        event_type=event_type,
        label=f"{label} · {len(events)}",
        is_derived=True,
        derivation_rule=(
            f"Grouped {len(events)} individual {label.lower()} "
            f"events belonging to ICU stay {stay_id}."
        ),
        children=events,
        evidence=[],
    )


# ==========================================================================
# Admission / discharge events
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

        if r.get("admittime") is not None:
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

        if r.get("intime") is None:
            continue

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
                    or "Transfer"
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
                    or "Medication"
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
          AND p.chartdate IS NOT NULL
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
                    or "Procedure"
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
                event_end_time=_to_dt(r["outtime"]),
                event_type="ICU_STAY",
                event_subtype="admission",
                label=(
                    f"ICU Stay "
                    f"({r.get('first_careunit') or 'unknown unit'})"
                ),
                value=r.get("first_careunit"),
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

    truncated = len(rows) > MAX_ICU_OBSERVATIONS

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
# Hierarchy construction
# ==========================================================================


def _attach_icu_children(
    *,
    subject_id: int,
    hadm_id: int,
    icu_event: Event,
    labs: list[Event],
    observations: list[Event],
    medications: list[Event],
) -> Event:
    """
    Attach category groups to an ICU stay.

    The resulting structure is:

        ICU_STAY
        ├── LAB_CLUSTER
        ├── ICU_OBSERVATION_CLUSTER
        └── MEDICATION_CLUSTER
    """

    stay_id = icu_event.stay_id

    if stay_id is None:
        return icu_event

    icu_labs = [
        event
        for event in labs
        if _event_inside_icu(event, icu_event)
    ]

    icu_observations = [
        event
        for event in observations
        if _event_inside_icu(event, icu_event)
    ]

    icu_medications = [
        event
        for event in medications
        if _event_inside_icu(event, icu_event)
    ]

    lab_group = _make_category_cluster(
        subject_id=subject_id,
        hadm_id=hadm_id,
        stay_id=stay_id,
        event_type="LAB_CLUSTER",
        label="Labs",
        events=icu_labs,
    )

    observation_group = _make_category_cluster(
        subject_id=subject_id,
        hadm_id=hadm_id,
        stay_id=stay_id,
        event_type="ICU_OBSERVATION_CLUSTER",
        label="ICU observations",
        events=icu_observations,
    )

    medication_group = _make_category_cluster(
        subject_id=subject_id,
        hadm_id=hadm_id,
        stay_id=stay_id,
        event_type="MEDICATION_CLUSTER",
        label="Medications",
        events=icu_medications,
    )

    children = [
        group
        for group in (
            lab_group,
            observation_group,
            medication_group,
        )
        if group is not None
    ]

    children.sort(
        key=lambda event: (
            event.event_time or datetime.max,
            event.event_type,
        )
    )

    icu_event.children = children

    return icu_event


# ==========================================================================
# Public timeline function
# ==========================================================================

def get_patient_timeline(
    con: duckdb.DuckDBPyConnection,
    subject_id: int,
) -> Timeline:
    """
    Reconstruct the hierarchical patient journey.

    Hierarchy:

        PATIENT JOURNEY
        ├── Admission
        ├── Transfer
        ├── ICU Stay
        │   ├── Labs · N
        │   │   ├── individual lab
        │   │   └── ...
        │   ├── ICU observations · N
        │   │   ├── individual observation
        │   │   └── ...
        │   └── Medications · N
        │       ├── individual medication
        │       └── ...
        ├── Procedure
        └── Discharge

    Events are assigned to an ICU stay only when their event_time
    falls inside that ICU stay's intime -> outtime interval.

    Events outside an ICU stay remain at the patient-journey level.
    """

    # ------------------------------------------------------------------
    # Validate patient
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Get all admissions
    # ------------------------------------------------------------------

    admission_rows = con.execute(
        """
        SELECT hadm_id
        FROM admissions
        WHERE subject_id = ?
        ORDER BY admittime
        """,
        [subject_id],
    ).fetchall()

    hadm_ids = [row[0] for row in admission_rows]

    top_level_events: list[Event] = []

    # ------------------------------------------------------------------
    # Process every admission
    # ------------------------------------------------------------------

    for hadm_id in hadm_ids:

        # --------------------------------------------------------------
        # Major journey events
        # --------------------------------------------------------------

        admission_events = _admission_events(
            con,
            subject_id,
            hadm_id,
        )

        transfer_events = _transfer_events(
            con,
            subject_id,
            hadm_id,
        )

        procedure_events = _procedure_events(
            con,
            subject_id,
            hadm_id,
        )

        # --------------------------------------------------------------
        # High-volume sources
        # --------------------------------------------------------------

        labs = _lab_events(
            con,
            subject_id,
            hadm_id,
        )

        medications = _emar_events(
            con,
            subject_id,
            hadm_id,
        )

        # --------------------------------------------------------------
        # ICU stays
        # --------------------------------------------------------------

        icu_stays, stay_ids = _icu_stay_events(
            con,
            subject_id,
            hadm_id,
        )

        # --------------------------------------------------------------
        # Collect ICU observations
        # --------------------------------------------------------------

        all_observations: list[Event] = []

        for stay_id in stay_ids:

            observations, truncated = _icu_observation_events(
                con,
                subject_id,
                stay_id,
            )

            if truncated:
                for event in observations:
                    event.derivation_rule = (
                        (event.derivation_rule or "")
                        + (
                            f" [NOTE: ICU observations were capped "
                            f"at {MAX_ICU_OBSERVATIONS} for "
                            f"stay_id={stay_id}.]"
                        )
                    ).strip()

            all_observations.extend(observations)

        # --------------------------------------------------------------
        # Track events assigned underneath ICU stays
        # --------------------------------------------------------------

        assigned_lab_ids: set[str] = set()
        assigned_observation_ids: set[str] = set()
        assigned_medication_ids: set[str] = set()

        # --------------------------------------------------------------
        # Build ICU hierarchy
        # --------------------------------------------------------------

        for icu_event in icu_stays:

            _attach_icu_children(
                subject_id=subject_id,
                hadm_id=hadm_id,
                icu_event=icu_event,
                labs=labs,
                observations=all_observations,
                medications=medications,
            )

            for child_group in icu_event.children:

                if child_group.event_type == "LAB_CLUSTER":
                    assigned_lab_ids.update(
                        child.event_id
                        for child in child_group.children
                    )

                elif (
                    child_group.event_type
                    == "ICU_OBSERVATION_CLUSTER"
                ):
                    assigned_observation_ids.update(
                        child.event_id
                        for child in child_group.children
                    )

                elif child_group.event_type == "MEDICATION_CLUSTER":
                    assigned_medication_ids.update(
                        child.event_id
                        for child in child_group.children
                    )

        # --------------------------------------------------------------
        # Find high-volume events that were NOT placed under ICU
        # --------------------------------------------------------------

        remaining_labs = [
            event
            for event in labs
            if event.event_id not in assigned_lab_ids
        ]

        remaining_observations = [
            event
            for event in all_observations
            if event.event_id not in assigned_observation_ids
        ]

        remaining_medications = [
            event
            for event in medications
            if event.event_id not in assigned_medication_ids
        ]

        # --------------------------------------------------------------
        # Add major events to patient journey
        # --------------------------------------------------------------

        top_level_events.extend(admission_events)
        top_level_events.extend(transfer_events)
        top_level_events.extend(procedure_events)

        # ICU_STAY is itself a top-level journey event.
        #
        # Its children contain:
        #
        #   LAB_CLUSTER
        #   ICU_OBSERVATION_CLUSTER
        #   MEDICATION_CLUSTER
        #
        # Therefore the hierarchy becomes:
        #
        # ICU_STAY
        #   ├── LAB_CLUSTER
        #   ├── ICU_OBSERVATION_CLUSTER
        #   └── MEDICATION_CLUSTER
        #
        top_level_events.extend(icu_stays)

        # --------------------------------------------------------------
        # Remaining events stay at journey level
        # --------------------------------------------------------------

        remaining_lab_group = _make_category_cluster(
            subject_id=subject_id,
            hadm_id=hadm_id,
            stay_id=None,
            event_type="LAB_CLUSTER",
            label="Labs",
            events=remaining_labs,
        )

        remaining_observation_group = _make_category_cluster(
            subject_id=subject_id,
            hadm_id=hadm_id,
            stay_id=None,
            event_type="ICU_OBSERVATION_CLUSTER",
            label="ICU observations",
            events=remaining_observations,
        )

        remaining_medication_group = _make_category_cluster(
            subject_id=subject_id,
            hadm_id=hadm_id,
            stay_id=None,
            event_type="MEDICATION_CLUSTER",
            label="Medications",
            events=remaining_medications,
        )

        top_level_events.extend(
            group
            for group in (
                remaining_lab_group,
                remaining_observation_group,
                remaining_medication_group,
            )
            if group is not None
        )

    # ------------------------------------------------------------------
    # Sort patient journey
    # ------------------------------------------------------------------

    top_level_events.sort(
        key=lambda event: (
            event.event_time or datetime.max,
            event.event_type,
            event.event_id,
        )
    )

    # ------------------------------------------------------------------
    # Return Timeline
    # ------------------------------------------------------------------

    return Timeline(
        subject_id=subject_id,
        hadm_id=None,
        stay_id=None,
        events=top_level_events,
        event_count=sum(
            _count(event)
            for event in top_level_events
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
    Count an event and all descendants.

    A derived group counts as one event plus all of its children.
    """

    return (
        1
        + sum(
            _count(child)
            for child in event.children
        )
    )

# ==========================================================================
# Event lookup (drill-down)
# ==========================================================================

def find_event(events: list[Event], event_id: str) -> Event | None:
    """
    Recursively search a reconstructed timeline for event_id, including
    inside cluster children. Used by GET /api/v1/events/{event_id} to
    serve both Level 2 (cluster -> members) and Level 3 (single leaf
    event -> its own evidence) from one endpoint, without re-querying
    DuckDB -- the cached Timeline already has everything.
    """
    for event in events:
        if event.event_id == event_id:
            return event
        found = find_event(event.children, event_id)
        if found is not None:
            return found
    return None