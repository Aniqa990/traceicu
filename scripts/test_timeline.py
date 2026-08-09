from __future__ import annotations

import sys
from pathlib import Path
from datetime import date, datetime

# Project root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb

from app.timeline import get_patient_timeline


PATIENT_ID = 10000032
DB_PATH = ROOT / "database" / "mimic.duckdb"


def get_value(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def event_timestamp(event):
    return get_value(event, "event_time")


def event_end_timestamp(event):
    return get_value(event, "event_end_time")


def get_children(node):
    children = get_value(node, "children", [])
    return children if isinstance(children, list) else []


def get_events(node):
    events = get_value(node, "events", [])
    return events if isinstance(events, list) else []


def walk_nodes(node):
    yield node

    for child in get_children(node):
        yield from walk_nodes(child)


def walk_events(node):
    for event in get_events(node):
        yield event

    for child in get_children(node):
        yield from walk_events(child)


def main():
    print("=" * 80)
    print("TIMELINE TEST")
    print("=" * 80)
    print(f"Patient: {PATIENT_ID}")
    print(f"Database: {DB_PATH}")
    print()

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"DuckDB database not found: {DB_PATH}"
        )

    con = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        timeline = get_patient_timeline(con, PATIENT_ID)

        print("=" * 80)
        print("RETURN TYPE")
        print("=" * 80)
        print(type(timeline))
        print()

        # Timeline is expected to contain top-level Event objects.
        top_level = get_children(timeline)

        # Some implementations may expose events directly.
        if not top_level:
            top_level = get_events(timeline)

        print("=" * 80)
        print("PATIENT JOURNEY")
        print("=" * 80)

        print(f"Top-level nodes: {len(top_level)}")

        all_nodes = []
        all_events = []

        for node in top_level:
            all_nodes.extend(list(walk_nodes(node)))
            all_events.extend(list(walk_events(node)))

        print(f"Total timeline nodes: {len(all_nodes)}")
        print(f"Total individual events: {len(all_events)}")
        print()

        # ------------------------------------------------------------------
        # Print hierarchy
        # ------------------------------------------------------------------

        def print_node(node, depth=0):
            indent = "  " * depth

            event_type = get_value(node, "event_type", "UNKNOWN")
            label = get_value(node, "label", "")

            event_time = event_timestamp(node)
            event_end = event_end_timestamp(node)

            events = get_events(node)
            children = get_children(node)

            line = (
                f"{indent}{event_type} | {label}"
            )

            if event_time is not None:
                line += f" | {event_time}"

            if event_end is not None:
                line += f" -> {event_end}"

            if events:
                line += f" | events={len(events)}"

            if children:
                line += f" | children={len(children)}"

            print(line)

            for child in children:
                print_node(child, depth + 1)

        for node in top_level:
            print_node(node)

        # ------------------------------------------------------------------
        # Timestamp validation
        # ------------------------------------------------------------------

        print()
        print("=" * 80)
        print("TIMESTAMP CHECK")
        print("=" * 80)

        timestamped = 0
        with_end_time = 0
        without_timestamp = 0

        for event in all_events:
            start = event_timestamp(event)
            end = event_end_timestamp(event)

            if start is not None:
                timestamped += 1
            else:
                without_timestamp += 1

            if end is not None:
                with_end_time += 1

        print(f"Individual events:       {len(all_events)}")
        print(f"With event_time:         {timestamped}")
        print(f"Without event_time:      {without_timestamp}")
        print(f"With event_end_time:     {with_end_time}")

        if all_events:
            coverage = timestamped / len(all_events) * 100
            print(f"Timestamp coverage:      {coverage:.1f}%")

        # ------------------------------------------------------------------
        # Event detail inspection
        # ------------------------------------------------------------------

        print()
        print("=" * 80)
        print("EVENT DETAIL CHECK")
        print("=" * 80)

        if not all_events:
            print("WARNING: No individual events were found.")
        else:
            first_event = all_events[0]

            print("First individual event:")
            print(first_event)
            print()

            print("First event fields:")

            if hasattr(first_event, "model_dump"):
                data = first_event.model_dump()
                for key, value in data.items():
                    print(f"  {key}: {value}")

            elif hasattr(first_event, "__dict__"):
                for key, value in vars(first_event).items():
                    print(f"  {key}: {value}")

            elif isinstance(first_event, dict):
                for key, value in first_event.items():
                    print(f"  {key}: {value}")

            else:
                print(first_event)

        # ------------------------------------------------------------------
        # Evidence check
        # ------------------------------------------------------------------

        print()
        print("=" * 80)
        print("EVIDENCE CHECK")
        print("=" * 80)

        evidence_count = 0
        events_with_evidence = 0

        for event in all_events:
            evidence = get_value(event, "evidence")

            if evidence:
                events_with_evidence += 1

                if isinstance(evidence, list):
                    evidence_count += len(evidence)
                else:
                    evidence_count += 1

        print(f"Events with evidence:    {events_with_evidence}")
        print(f"Evidence objects:        {evidence_count}")

        # ------------------------------------------------------------------
        # ICU hierarchy check
        # ------------------------------------------------------------------

        print()
        print("=" * 80)
        print("ICU HIERARCHY CHECK")
        print("=" * 80)

        icu_stays = [
            node
            for node in all_nodes
            if get_value(node, "event_type") == "ICU_STAY"
        ]

        print(f"ICU stays found: {len(icu_stays)}")
        print()

        for index, stay in enumerate(icu_stays, start=1):
            print(f"ICU Stay #{index}")

            print(
                f"  label: "
                f"{get_value(stay, 'label', '')}"
            )

            print(
                f"  stay_id: "
                f"{get_value(stay, 'stay_id')}"
            )

            print(
                f"  event_time: "
                f"{event_timestamp(stay)}"
            )

            print(
                f"  event_end_time: "
                f"{event_end_timestamp(stay)}"
            )

            print(
                f"  children: "
                f"{len(get_children(stay))}"
            )

            for child in get_children(stay):
                print(
                    f"    ├── "
                    f"{get_value(child, 'event_type', 'UNKNOWN')} | "
                    f"{get_value(child, 'label', '')} | "
                    f"events={len(get_events(child))}"
                )

        # ------------------------------------------------------------------
        # Top-level type counts
        # ------------------------------------------------------------------

        print()
        print("=" * 80)
        print("TOP-LEVEL TYPE COUNTS")
        print("=" * 80)

        counts = {}

        for node in top_level:
            event_type = get_value(
                node,
                "event_type",
                "UNKNOWN",
            )

            counts[event_type] = counts.get(event_type, 0) + 1

        for event_type in sorted(counts):
            print(f"{event_type}: {counts[event_type]}")

        # ------------------------------------------------------------------
        # Frontend readiness
        # ------------------------------------------------------------------

        print()
        print("=" * 80)
        print("FRONTEND READINESS")
        print("=" * 80)

        checks = {
            "Timeline returned": timeline is not None,
            "Top-level nodes exist": len(top_level) > 0,
            "Individual events exist": len(all_events) > 0,
            "Events have timestamps": timestamped > 0,
            "Evidence exists": evidence_count > 0,
            "ICU hierarchy exists": len(icu_stays) > 0,
        }

        for name, passed in checks.items():
            print(
                f"[{'PASS' if passed else 'FAIL'}] "
                f"{name}"
            )

        print()
        print("=" * 80)
        print("TIMELINE TEST COMPLETE")
        print("=" * 80)

    finally:
        con.close()


if __name__ == "__main__":
    main()