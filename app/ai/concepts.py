# """
# In-memory concept dictionaries for label -> itemid resolution.

# d_labitems and d_items are small and static for the life of the process
# (a few thousand rows total in the demo dataset), so they're loaded once
# at app startup instead of being queried on every /ask call. This is the
# single cheapest latency win available: it turns "resolve 'sodium' to an
# itemid" from a DB round trip into an in-memory dict lookup.
# """
# from __future__ import annotations

# import difflib

# import duckdb


# class ConceptIndex:
#     def __init__(self):
#         self.lab_labels: dict[str, int] = {}
#         self.chart_labels: dict[str, int] = {}

#     def load(self, con: duckdb.DuckDBPyConnection) -> None:
#         self.lab_labels = {
#             label.lower(): itemid
#             for label, itemid in con.execute(
#                 "SELECT label, itemid FROM d_labitems WHERE label IS NOT NULL"
#             ).fetchall()
#         }
#         self.chart_labels = {
#             label.lower(): itemid
#             for label, itemid in con.execute(
#                 "SELECT label, itemid FROM d_items WHERE label IS NOT NULL"
#             ).fetchall()
#         }

#     def resolve(self, concept: str | None, domain: str) -> int | None:
#         """
#         Resolve a free-text concept (from the LLM's query plan) to a
#         MIMIC itemid. Exact match -> substring match -> fuzzy match,
#         in that order, entirely in-memory.
#         """
#         if not concept:
#             return None

#         table = self.lab_labels if domain == "lab" else self.chart_labels
#         concept_l = concept.lower().strip()

#         if concept_l in table:
#             return table[concept_l]

#         candidates = [label for label in table if concept_l in label or label in concept_l]
#         if candidates:
#             # Prefer the shortest matching label (closest to an exact match).
#             return table[min(candidates, key=len)]

#         close = difflib.get_close_matches(concept_l, table.keys(), n=1, cutoff=0.75)
#         if close:
#             return table[close[0]]

#         return None


# _concept_index = ConceptIndex()


# def init_concept_index(con: duckdb.DuckDBPyConnection) -> None:
#     """Call once at app startup (see app/main.py lifespan)."""
#     _concept_index.load(con)


# def get_concept_index() -> ConceptIndex:
#     return _concept_index

"""
In-memory concept resolution for MIMIC item dictionaries.

Important MIMIC detail:
-----------------------
A single human-readable label can map to MULTIPLE itemids.

The old implementation used:

    {"sodium": 52623}

which silently discarded every other Sodium itemid.

This implementation keeps ALL itemids:

    {"sodium": (50983, 52623)}

Retrieval code can then search the candidate itemids and let the actual
patient/stay data determine which records exist.

The dictionaries are loaded once at application startup, so concept
resolution remains an in-memory operation and does not require a DB
round trip for every /ask request.
"""
from __future__ import annotations

import difflib
import re
from collections import defaultdict

import duckdb


class ConceptIndex:
    def __init__(self) -> None:
        # label -> all matching itemids
        self.lab_labels: dict[str, tuple[int, ...]] = {}
        self.chart_labels: dict[str, tuple[int, ...]] = {}

    @staticmethod
    def _normalize(value: str) -> str:
        """
        Normalize free-text concepts and dictionary labels.

        Examples:
            "Sodium"       -> "sodium"
            "sodium level" -> "sodium level"
            "Heart-Rate"    -> "heart rate"
        """
        value = value.casefold().strip()
        value = re.sub(r"[_\-/]+", " ", value)
        value = re.sub(r"\s+", " ", value)
        return value

    @staticmethod
    def _build_index(rows: list[tuple[str, int]]) -> dict[str, tuple[int, ...]]:
        """
        Build:

            normalized label -> tuple(all itemids)

        without losing duplicate labels.
        """
        grouped: defaultdict[str, set[int]] = defaultdict(set)

        for label, itemid in rows:
            if label is None or itemid is None:
                continue

            normalized = ConceptIndex._normalize(str(label))

            if not normalized:
                continue

            grouped[normalized].add(int(itemid))

        return {
            label: tuple(sorted(itemids))
            for label, itemids in grouped.items()
        }

    def load(self, con: duckdb.DuckDBPyConnection) -> None:
        """
        Load d_labitems and d_items once at application startup.
        """
        lab_rows = con.execute(
            """
            SELECT label, itemid
            FROM d_labitems
            WHERE label IS NOT NULL
              AND itemid IS NOT NULL
            ORDER BY label, itemid
            """
        ).fetchall()

        chart_rows = con.execute(
            """
            SELECT label, itemid
            FROM d_items
            WHERE label IS NOT NULL
              AND itemid IS NOT NULL
            ORDER BY label, itemid
            """
        ).fetchall()

        self.lab_labels = self._build_index(lab_rows)
        self.chart_labels = self._build_index(chart_rows)

    def _table_for_domain(self, domain: str) -> dict[str, tuple[int, ...]]:
        """
        Return the correct concept dictionary.

        Lab concepts resolve against d_labitems.
        ICU observation concepts resolve against d_items.
        """
        domain = (domain or "").casefold().strip()

        if domain == "lab":
            return self.lab_labels

        if domain in {"icu_observation", "chart", "chartevent", "chartevents"}:
            return self.chart_labels

        # Keep old behavior for unknown chart-like domains.
        return self.chart_labels

    def resolve_all(
        self,
        concept: str | None,
        domain: str,
    ) -> list[int]:
        """
        Resolve a free-text concept to ALL plausible MIMIC itemids.

        Resolution order:

        1. exact normalized label
        2. substring match
        3. fuzzy match

        Unlike the old resolve() implementation, duplicate labels are
        never collapsed to a single arbitrary itemid.
        """
        if not concept:
            return []

        table = self._table_for_domain(domain)
        concept_l = self._normalize(concept)

        if not concept_l:
            return []

        # ------------------------------------------------------------
        # 1. Exact label match
        # ------------------------------------------------------------
        exact = table.get(concept_l)

        if exact:
            return list(exact)

        # ------------------------------------------------------------
        # 2. Substring match
        #
        # Prefer the shortest matching label because it is generally
        # the closest semantic match.
        # ------------------------------------------------------------
        candidates = [
            label
            for label in table
            if concept_l in label or label in concept_l
        ]

        if candidates:
            shortest_len = min(len(label) for label in candidates)

            shortest = sorted(
                label
                for label in candidates
                if len(label) == shortest_len
            )

            itemids: set[int] = set()

            for label in shortest:
                itemids.update(table[label])

            return sorted(itemids)

        # ------------------------------------------------------------
        # 3. Fuzzy match
        # ------------------------------------------------------------
        close = difflib.get_close_matches(
            concept_l,
            table.keys(),
            n=3,
            cutoff=0.75,
        )

        if close:
            # Only use the closest label(s). This prevents a broad fuzzy
            # search from accidentally merging unrelated concepts.
            best_ratio = max(
                difflib.SequenceMatcher(None, concept_l, label).ratio()
                for label in close
            )

            best_labels = [
                label
                for label in close
                if difflib.SequenceMatcher(
                    None,
                    concept_l,
                    label,
                ).ratio() >= best_ratio - 0.02
            ]

            itemids: set[int] = set()

            for label in best_labels:
                itemids.update(table[label])

            return sorted(itemids)

        return []

    def resolve(
        self,
        concept: str | None,
        domain: str,
    ) -> int | None:
        """
        Backward-compatible single-item resolver.

        New retrieval code should prefer resolve_all().

        This method exists so older callers do not break. When multiple
        itemids exist, the smallest deterministic itemid is returned
        rather than an arbitrary dictionary-overwrite result.
        """
        candidates = self.resolve_all(concept, domain)

        if not candidates:
            return None

        return candidates[0]

    def labels_for_itemids(
        self,
        itemids: list[int],
        domain: str,
    ) -> dict[int, str]:
        """
        Return itemid -> label for debugging / provenance.

        This is useful when multiple MIMIC itemids share a label.
        """
        table = self._table_for_domain(domain)
        result: dict[int, str] = {}

        wanted = set(itemids)

        for label, ids in table.items():
            for itemid in ids:
                if itemid in wanted:
                    result[itemid] = label

        return result


_concept_index = ConceptIndex()


def init_concept_index(con: duckdb.DuckDBPyConnection) -> None:
    """
    Call once at application startup.
    """
    _concept_index.load(con)


def get_concept_index() -> ConceptIndex:
    return _concept_index