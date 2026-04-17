from typing import List, Dict, Any


class VectorStore:
    """Simple keyword-based store simulating vector search."""

    def __init__(self):
        self.data: List[Dict[str, Any]] = []

    def add(self, item: Dict[str, Any]) -> None:
        self.data.append(item)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self.data:
            return []
        query_terms = query.lower().split()
        scored = []
        for item in self.data:
            item_str = str(item).lower()
            score = sum(1 for term in query_terms if term in item_str)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def clear(self) -> None:
        self.data = []