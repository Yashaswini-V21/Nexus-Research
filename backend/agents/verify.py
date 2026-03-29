"""Fact verification agent — validates claims with confidence scoring."""

import os
import json
import asyncio
import logging
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("nexus.agent.verify")


class VerifyAgent:
    """Generates 6-8 fact-checked claims with per-claim confidence and overall trust score."""
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    async def run(self, query: str, search_results: list) -> dict:
        search_text = "\n".join(
            f"- {r['title']}: {r['content'][:300]}"
            for r in search_results[:6]
            if r.get("type") != "error"
        )

        prompt = f"""You are a rigorous fact-checking analyst. Verify the key claims about: \"{query}\"

Search Evidence:
{search_text}

Return ONLY this exact JSON (no markdown):
{{
  "claims": [
    {{
      "claim": "specific factual claim extracted or derived from the evidence",
      "status": "verified|disputed|unverified|misleading",
      "evidence": "brief quote or paraphrase from evidence supporting or refuting this claim",
      "confidence_score": 0.95
    }}
  ],
  "overall_confidence": 0.82,
  "key_uncertainties": ["uncertainty 1", "uncertainty 2"],
  "recommendation": "One sentence on information quality and what to research further"
}}

Rules:
- 6-8 distinct, specific claims (not vague statements)
- Status definitions:
  - verified: Multiple independent sources confirm this
  - disputed: Sources conflict or credible counter-evidence exists
  - unverified: Cannot confirm from available evidence
  - misleading: Technically true but missing critical context
- overall_confidence: 0.0-1.0 based on aggregate evidence quality
- confidence_score per claim: 0.0-1.0"""

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
                "claims": [],
                "overall_confidence": 0.0,
                "key_uncertainties": ["Verification parsing failed"],
                "recommendation": "Manual verification recommended.",
            }

