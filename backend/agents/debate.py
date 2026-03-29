"""Debate agent — analyzes topics through mainstream and contrarian perspectives."""

import os
import json
import asyncio
import logging
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("nexus.agent.debate")


class DebateAgent:
    """Generates structured debate synthesis with consensus vs alternative views."""
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    async def run(self, query: str, search_results: list, related_context: list = []) -> dict:
        search_text = "\n".join(
            f"- {r['title']}: {r['content'][:300]}"
            for r in search_results[:6]
            if r.get("type") != "error"
        )
        context_text = "\n".join(related_context) if related_context else "No prior research context."

        prompt = f"""You are a multi-perspective research analyst. Analyze this topic with deep intellectual rigor.

Topic: \"{query}\"

Search Evidence:
{search_text}

Prior Research Context:
{context_text}

Return ONLY this exact JSON (no markdown, no extra text):
{{
  "mainstream_view": {{
    "title": "short title for consensus view",
    "summary": "2-3 sentence mainstream/consensus perspective grounded in evidence",
    "key_points": ["point 1", "point 2", "point 3"],
    "confidence": "high"
  }},
  "contrarian_view": {{
    "title": "short title for alternative/underexplored view",
    "summary": "2-3 sentence genuine devil's advocate or alternative perspective that challenges assumptions",
    "key_points": ["point 1", "point 2", "point 3"],
    "confidence": "medium"
  }},
  "synthesis": "2-3 sentence nuanced synthesis acknowledging complexity and integrating both views",
  "verdict": "nuanced|mainstream_wins|contrarian_wins"
}}"""

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.chat.completions.create(
                model=self.model,
                max_tokens=1200,
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
                "mainstream_view": {"title": "Analysis", "summary": text[:400], "key_points": [], "confidence": "low"},
                "contrarian_view": {"title": "Alternative View", "summary": "Could not generate contrarian analysis.", "key_points": [], "confidence": "low"},
                "synthesis": "Analysis requires review.",
                "verdict": "nuanced",
            }

