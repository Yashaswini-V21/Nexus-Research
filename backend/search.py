"""Tavily Search API wrapper for real-time web retrieval."""

import os
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("nexus.search")


class TavilySearch:
    """Encapsulates Tavily search client with connection pooling and error handling."""
    def __init__(self):
        self._api_key = os.getenv("TAVILY_API_KEY", "")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from tavily import TavilyClient
            self._client = TavilyClient(api_key=self._api_key)
        return self._client

    async def search(self, query: str, depth: str = "deep") -> list:
        if not self._api_key:
            logger.error("TAVILY_API_KEY not set")
            return [{"type": "error", "title": "Missing API Key", "content": "TAVILY_API_KEY not set.", "url": ""}]

        client = self._get_client()
        search_depth = "advanced" if depth == "deep" else "basic"
        logger.info(f"Searching: {query!r} (depth={search_depth})")

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: client.search(
                    query=query,
                    search_depth=search_depth,
                    max_results=5,
                    include_raw_content=False,
                    include_answer=True,
                ),
            )

            results = []
            if response.get("answer"):
                results.append(
                    {"type": "answer", "title": "Direct Answer", "content": response["answer"], "url": ""}
                )
            for r in response.get("results", []):
                results.append(
                    {
                        "type": "web",
                        "title": r.get("title", ""),
                        "content": r.get("content", ""),
                        "url": r.get("url", ""),
                        "score": r.get("score", 0),
                    }
                )
            logger.info(f"Search returned {len(results)} results")
            return results
        except Exception as e:
            logger.exception(f"Search error: {e}")
            return [{"type": "error", "title": "Search Error", "content": str(e), "url": ""}]

