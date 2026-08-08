"""
Quick CLI for exercising the timeline builder without a web framework.

    python main.py --subject-id 10006
    python main.py --subject-id 10006 --hadm-id 25208949
    python main.py --subject-id 10006 --stay-id 94667 --no-icu-observations

Prints the resulting Timeline as JSON. Once you're ready to wire this
into FastAPI, get_patient_timeline() is the one function you call from
a route handler -- db.get_connection() should be created once at app
startup and reused across requests.
"""

from __future__ import annotations

import argparse
import json
import sys

from db import get_connection
from timeline import ScopeNotFoundError, get_patient_timeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct a MIMIC-IV patient timeline.")
    parser.add_argument("--subject-id", type=int, required=True)
    parser.add_argument("--hadm-id", type=int, default=None)
    parser.add_argument("--stay-id", type=int, default=None)
    parser.add_argument(
        "--no-icu-observations",
        action="store_true",
        help="Skip chartevents (fast, admission/transfer/lab/med/dx/procedure timeline only).",
    )
    args = parser.parse_args()

    con = get_connection()
    try:
        timeline = get_patient_timeline(
            con,
            subject_id=args.subject_id,
            hadm_id=args.hadm_id,
            stay_id=args.stay_id,
            include_icu_observations=not args.no_icu_observations,
        )
    except ScopeNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    print(timeline.model_dump_json(indent=2, exclude_none=True))


if __name__ == "__main__":
    main()