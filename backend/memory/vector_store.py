import time
from typing import List, Dict, Any

STOP_WORDS = {"find", "give", "show", "get", "list", "with", "that", "their",
              "from", "into", "this", "have", "will", "they", "what", "which",
              "companies", "company", "startups", "startup", "and", "for", "the"}


class VectorStore:
    """
    Keyword-based vector store simulating semantic search.
    Stores past query → enriched results pairs.
    Used to:
      - Surface relevant past results for similar queries
      - Avoid redundant retrieval on similar searches
      - Improve future responses with accumulated context
    """

    def __init__(self):
        # Each entry: { query, results, signals, ts }
        self.entries: List[Dict[str, Any]] = []

    def add(self, query: str, results: List[Dict[str, Any]], signals: List[str]) -> None:
        """Store a query and its enriched results."""
        self.entries.append({
            "query":   query,
            "results": results,
            "signals": signals,
            "ts":      time.time(),
        })

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Find past results relevant to the current query.
        Returns a flat list of enriched company records scored by relevance.
        """
        if not self.entries:
            return []

        terms = self._extract_terms(query)
        if not terms:
            return []

        scored: List[tuple] = []
        for entry in self.entries:
            entry_text = (entry["query"] + " " + str(entry["signals"])).lower()
            score = sum(1 for t in terms if t in entry_text)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Flatten top matching entries into a deduplicated company list
        seen = set()
        results = []
        for _, entry in scored[:top_k]:
            for record in entry["results"]:
                name = record.get("company", "")
                if name not in seen:
                    seen.add(name)
                    results.append(record)

        return results

    def get_similar_signals(self, query: str) -> List[str]:
        """Return signals from past similar queries — used to boost enrichment."""
        past = self.search(query, top_k=2)
        signals = []
        for r in past:
            signals.extend(r.get("signals", []))
        return list(set(signals))

    def size(self) -> int:
        return len(self.entries)

    def clear(self) -> None:
        self.entries = []

    def _extract_terms(self, query: str) -> List[str]:
        return [
            w for w in query.lower().split()
            if len(w) > 3 and w not in STOP_WORDS
        ]