"""Knowledge graph agent — constructs semantic node and edge structure."""

import os
import json
import asyncio
import logging
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("nexus.agent.mindmap")


class MindmapAgent:
    """Builds 10-14 typed nodes with 12-18 weighted edges for knowledge visualization."""
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    async def run(self, query: str, search_results: list, related_context: list = []) -> dict:
        search_text = "\n".join(
            f"- {r['title']}: {r['content'][:250]}"
            for r in search_results[:6]
            if r.get("type") != "error"
        )

        prompt = f"""You are a knowledge graph architect. Build a rich, interconnected knowledge graph for: \"{query}\"

Evidence:
{search_text}

Return ONLY this exact JSON (no markdown):
{{
  "nodes": [
    {{"id": "1", "label": "Main Topic Label", "type": "central", "description": "core concept description", "weight": 10}},
    {{"id": "2", "label": "Node Label", "type": "concept", "description": "brief description", "weight": 7}}
  ],
  "edges": [
    {{"from": "1", "to": "2", "label": "relationship verb", "strength": 0.9}}
  ],
  "central_insight": "One sentence core insight about this knowledge domain"
}}

Rules:
- 10-14 nodes total; first node is always "central" type for the main topic
- 12-18 edges; all from/to values must reference valid node ids
- Node types: central, concept, person, event, technology, location, organization
- Weight 1-10 (10 = most important)
- Strength 0.0-1.0 (1.0 = strongest relationship)"""

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.chat.completions.create(
                model=self.model,
                max_tokens=1800,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
            ),
        )

        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1][4:] if parts[1].startswith("json") else parts[1]

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "nodes": [{"id": "1", "label": query, "type": "central", "description": "Main topic", "weight": 10}],
                "edges": [],
                "central_insight": "Knowledge graph generation encountered an error.",
            }

