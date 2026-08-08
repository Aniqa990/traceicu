from fastapi import FastAPI, Query
from app.database import get_connection
from app.timeline import get_timeline

app = FastAPI(
    title="TraceICU API",
    version="0.1.0"
)


@app.get("/api/v1/health")
def health():
    return {
        "status": "ok"
    }


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

@app.get("/api/v1/encounters/{hadm_id}/timeline")
def timeline(
    hadm_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    events = get_timeline(
        hadm_id=hadm_id,
        limit=limit,
        offset=offset
    )

    return {
        "hadm_id": hadm_id,
        "limit": limit,
        "offset": offset,
        "events": events
    }