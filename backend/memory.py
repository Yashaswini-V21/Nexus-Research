"""ChromaDB-based persistent memory for research sessions."""

import json
import os
from datetime import datetime, timezone

import chromadb


class ResearchMemory:
    """Vector database for semantic search across past research sessions."""
    def __init__(self):
        db_path = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(
            name="research_history",
            metadata={"hnsw:space": "cosine"},
        )

    def save(self, research_id: str, query: str, data: dict) -> None:
        try:
            self.collection.add(
                ids=[research_id],
                documents=[query],
                metadatas=[
                    {
                        "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                        "query": query,
                        "data": json.dumps(data),
                    }
                ],
            )
        except Exception as e:
            print(f"[Memory] Save error: {e}")

    def get_related(self, query: str, n_results: int = 3) -> list:
        try:
            count = self.collection.count()
            if count == 0:
                return []
            results = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, count),
            )
            return [f"Previously researched: {doc}" for doc in results["documents"][0]]
        except Exception:
            return []

    def get_all(self) -> list:
        try:
            results = self.collection.get()
            history = []
            for i, rid in enumerate(results["ids"]):
                meta = results["metadatas"][i]
                history.append(
                    {
                        "id": rid,
                        "query": meta.get("query", ""),
                        "timestamp": meta.get("timestamp", ""),
                    }
                )
            return sorted(history, key=lambda x: x["timestamp"], reverse=True)
        except Exception:
            return []

    def get_by_id(self, research_id: str) -> dict | None:
        try:
            results = self.collection.get(ids=[research_id])
            if not results["ids"]:
                return None
            return json.loads(results["metadatas"][0].get("data", "{}"))
        except Exception:
            return None

    def delete(self, research_id: str) -> None:
        try:
            self.collection.delete(ids=[research_id])
        except Exception as e:
            print(f"[Memory] Delete error: {e}")
