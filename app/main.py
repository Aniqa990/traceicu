from fastapi import FastAPI, HTTPException, Query

from app.database import get_connection
from app.timeline import (
    ScopeNotFoundError,
    get_patient_timeline,
)

app = FastAPI(
    title="TraceICU API",
    version="0.1.0",
)


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/test-db")
def test_db():
    conn = get_connection()

    try:
        result = conn.execute(
            "SELECT COUNT(*) FROM patients"
        ).fetchone()

        return {
            "patients": result[0]
        }

    finally:
        conn.close()


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

    conn = get_connection()

    try:

        # If only hadm_id was supplied, resolve its patient.
        if subject_id is None:

            row = conn.execute(
                """
                SELECT subject_id
                FROM admissions
                WHERE hadm_id = ?
                """,
                [hadm_id],
            ).fetchone()

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No admission found with hadm_id={hadm_id}.",
                )

            subject_id = row[0]

        try:
            timeline = get_patient_timeline(
                conn,
                subject_id,
            )

        except ScopeNotFoundError as e:
            raise HTTPException(
                status_code=404,
                detail=str(e),
            )

        events = timeline.events[
            offset: offset + limit
        ]

        return {
            "subject_id": subject_id,
            "hadm_id": hadm_id,
            "limit": limit,
            "offset": offset,
            "total_events": len(timeline.events),
            "events": [
                event.model_dump(
                    mode="json",
                    exclude_none=True,
                )
                for event in events
            ],
        }

    finally:
        conn.close()