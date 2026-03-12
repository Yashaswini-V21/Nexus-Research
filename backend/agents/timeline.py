import os
import json
import asyncio
import logging
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("nexus.agent.timeline")


class TimelineAgent:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    async def run(self, query: str, search_results: list) -> dict:
        search_text = "\n".join(
            f"- {r['title']}: {r['content'][:300]}"
            for r in search_results[:6]
            if r.get("type") != "error"
        )

        prompt = f"""You are a historical research analyst. Build a comprehensive chronological timeline for: \"{query}\"

Evidence:
{search_text}

Return ONLY this exact JSON (no markdown):
{{
  "events": [
    {{
      "date": "specific year or date (e.g. '1969' or 'July 2023')",
      "event": "Clear, specific description of what happened",
      "significance": "Why this was important — impact and lasting implications",
      "type": "milestone|discovery|controversy|turning_point|founding|other"
    }}
  ],
  "era_summary": "One sentence summarizing the full historical arc",
  "future_outlook": "One sentence about the likely trajectory going forward"
}}

Rules:
- 8-12 events in strict chronological order
- Prioritize the most consequential events
- Types: milestone, discovery, controversy, turning_point, founding, other"""

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.chat.completions.create(
                model=self.model,
                max_tokens=1500,
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
                "events": [],
                "era_summary": "Timeline generation encountered an error.",
                "future_outlook": "Unable to determine.",
            }

