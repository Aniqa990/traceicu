"""
In-memory concept dictionaries for label -> itemid resolution.

d_labitems and d_items are small and static for the life of the process
(a few thousand rows total in the demo dataset), so they're loaded once
at app startup instead of being queried on every /ask call. This is the
single cheapest latency win available: it turns "resolve 'sodium' to an
itemid" from a DB round trip into an in-memory dict lookup.
"""
from __future__ import annotations

import difflib

import duckdb


class ConceptIndex:
    def __init__(self):
        self.lab_labels: dict[str, int] = {}
        self.chart_labels: dict[str, int] = {}

    def load(self, con: duckdb.DuckDBPyConnection) -> None:
        self.lab_labels = {
            label.lower(): itemid
            for label, itemid in con.execute(
                "SELECT label, itemid FROM d_labitems WHERE label IS NOT NULL"
            ).fetchall()
        }
        self.chart_labels = {
            label.lower(): itemid
            for label, itemid in con.execute(
                "SELECT label, itemid FROM d_items WHERE label IS NOT NULL"
            ).fetchall()
        }

    def resolve(self, concept: str | None, domain: str) -> int | None:
        """
        Resolve a free-text concept (from the LLM's query plan) to a
        MIMIC itemid. Exact match -> substring match -> fuzzy match,
        in that order, entirely in-memory.
        """
        if not concept:
            return None

        table = self.lab_labels if domain == "lab" else self.chart_labels
        concept_l = concept.lower().strip()

        if concept_l in table:
            return table[concept_l]

        candidates = [label for label in table if concept_l in label or label in concept_l]
        if candidates:
            # Prefer the shortest matching label (closest to an exact match).
            return table[min(candidates, key=len)]

        close = difflib.get_close_matches(concept_l, table.keys(), n=1, cutoff=0.75)
        if close:
            return table[close[0]]

        return None


_concept_index = ConceptIndex()


def init_concept_index(con: duckdb.DuckDBPyConnection) -> None:
    """Call once at app startup (see app/main.py lifespan)."""
    _concept_index.load(con)


def get_concept_index() -> ConceptIndex:
    return _concept_index