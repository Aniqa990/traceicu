from app.database import get_connection


TIMELINE_QUERY = """
SELECT
    'admission-' || CAST(a.hadm_id AS VARCHAR) AS event_id,
    a.subject_id,
    a.hadm_id,
    NULL::BIGINT AS stay_id,
    a.admittime AS event_time,
    'admission' AS event_type,
    'Hospital admission' AS concept,
    NULL::BIGINT AS item_id,
    NULL::VARCHAR AS value_raw,
    NULL::DOUBLE AS value_numeric,
    NULL::VARCHAR AS unit,
    'admissions' AS source_table,
    CAST(a.hadm_id AS VARCHAR) AS source_row_id,
    'admittime' AS source_time_field
FROM admissions a
WHERE a.hadm_id = ?

UNION ALL

SELECT
    'transfer-' || CAST(t.transfer_id AS VARCHAR),
    t.subject_id,
    t.hadm_id,
    NULL::BIGINT,
    t.intime,
    'transfer',
    COALESCE(t.careunit, t.eventtype),
    NULL::BIGINT,
    t.careunit,
    NULL::DOUBLE,
    NULL::VARCHAR,
    'transfers',
    CAST(t.transfer_id AS VARCHAR),
    'intime'
FROM transfers t
WHERE t.hadm_id = ?
AND t.intime IS NOT NULL

UNION ALL

SELECT
    'icu-' || CAST(i.stay_id AS VARCHAR),
    i.subject_id,
    i.hadm_id,
    i.stay_id,
    i.intime,
    'icu_stay',
    i.first_careunit,
    NULL::BIGINT,
    i.first_careunit,
    NULL::DOUBLE,
    NULL::VARCHAR,
    'icustays',
    CAST(i.stay_id AS VARCHAR),
    'intime'
FROM icustays i
WHERE i.hadm_id = ?
AND i.intime IS NOT NULL

UNION ALL

SELECT
    'lab-' || CAST(l.labevent_id AS VARCHAR),
    l.subject_id,
    l.hadm_id,
    NULL::BIGINT,
    l.charttime,
    'lab',
    d.label,
    l.itemid,
    l.value,
    l.valuenum,
    l.valueuom,
    'labevents',
    CAST(l.labevent_id AS VARCHAR),
    'charttime'
FROM labevents l
LEFT JOIN d_labitems d
    ON l.itemid = d.itemid
WHERE l.hadm_id = ?
AND l.charttime IS NOT NULL

UNION ALL

SELECT
    'emar-' || CAST(e.emar_id AS VARCHAR),
    e.subject_id,
    e.hadm_id,
    NULL::BIGINT,
    e.charttime,
    'medication',
    e.medication,
    NULL::BIGINT,
    e.event_txt,
    NULL::DOUBLE,
    NULL::VARCHAR,
    'emar',
    CAST(e.emar_id AS VARCHAR),
    'charttime'
FROM emar e
WHERE e.hadm_id = ?
AND e.charttime IS NOT NULL

UNION ALL

SELECT
    'procedure-' ||
    CAST(p.subject_id AS VARCHAR) || '-' ||
    CAST(p.hadm_id AS VARCHAR) || '-' ||
    CAST(p.seq_num AS VARCHAR),
    p.subject_id,
    p.hadm_id,
    NULL::BIGINT,
    CAST(p.chartdate AS TIMESTAMP),
    'procedure',
    d.long_title,
    NULL::BIGINT,
    p.icd_code,
    NULL::DOUBLE,
    NULL::VARCHAR,
    'procedures_icd',
    CAST(p.subject_id AS VARCHAR) || '-' ||
    CAST(p.hadm_id AS VARCHAR) || '-' ||
    CAST(p.seq_num AS VARCHAR),
    'chartdate'
FROM procedures_icd p
LEFT JOIN d_icd_procedures d
    ON p.icd_code = d.icd_code
    AND p.icd_version = d.icd_version
WHERE p.hadm_id = ?
AND p.chartdate IS NOT NULL

UNION ALL

SELECT
    'chartevent-' ||
    CAST(c.subject_id AS VARCHAR) || '-' ||
    CAST(c.hadm_id AS VARCHAR) || '-' ||
    CAST(c.stay_id AS VARCHAR) || '-' ||
    CAST(c.charttime AS VARCHAR) || '-' ||
    CAST(c.itemid AS VARCHAR),
    c.subject_id,
    c.hadm_id,
    c.stay_id,
    c.charttime,
    'icu_observation',
    d.label,
    c.itemid,
    c.value,
    c.valuenum,
    COALESCE(c.valueuom, d.unitname),
    'chartevents',
    CAST(c.subject_id AS VARCHAR) || '-' ||
    CAST(c.hadm_id AS VARCHAR) || '-' ||
    CAST(c.stay_id AS VARCHAR) || '-' ||
    CAST(c.charttime AS VARCHAR) || '-' ||
    CAST(c.itemid AS VARCHAR),
    'charttime'
FROM chartevents c
LEFT JOIN d_items d
    ON c.itemid = d.itemid
WHERE c.hadm_id = ?
AND c.charttime IS NOT NULL

ORDER BY event_time, event_type, event_id
LIMIT ? OFFSET ?
"""


def get_timeline(hadm_id: int, limit: int = 50, offset: int = 0):
    conn = get_connection()

    try:
        params = [hadm_id] * 7 + [limit, offset]

        rows = conn.execute(
            TIMELINE_QUERY,
            params
        ).fetchall()

        columns = [
            "event_id",
            "subject_id",
            "hadm_id",
            "stay_id",
            "event_time",
            "event_type",
            "concept",
            "item_id",
            "value_raw",
            "value_numeric",
            "unit",
            "source_table",
            "source_row_id",
            "source_time_field",
        ]

        events = []

        for row in rows:
            event = dict(zip(columns, row))

            # Convert datetime objects to strings
            if event["event_time"] is not None:
                event["event_time"] = event["event_time"].isoformat()

            events.append(event)

        return events

    finally:
        conn.close()