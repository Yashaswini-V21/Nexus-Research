"""Nexus Research API — FastAPI backend with async multi-agent orchestration.

Provides REST and WebSocket endpoints for 4D research:
  - Debate analysis (mainstream vs contrarian)
  - Historical timeline extraction
  - Knowledge graph construction
  - Fact verification with confidence scoring
"""

import os
import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("nexus")

from backend.search import TavilySearch
from backend.memory import ResearchMemory
from backend.pdf_export import ResearchPDFExporter
from backend.agents.debate import DebateAgent
from backend.agents.mindmap import MindmapAgent
from backend.agents.timeline import TimelineAgent
from backend.agents.verify import VerifyAgent

# ── API Key Validation ───────────────────────────────────────────────
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
TAVILY_KEY = os.getenv("TAVILY_API_KEY", "")

if not GROQ_KEY:
    logger.error("GROQ_API_KEY is not set in .env — agents will fail.")
if not TAVILY_KEY:
    logger.error("TAVILY_API_KEY is not set in .env — search will fail.")

app = FastAPI(title="Nexus Research API", version="2.0.0")


def _parse_cors_origins() -> list[str]:
    """Parse comma-separated origins from env, with safe local defaults."""
    configured = os.getenv("CORS_ORIGINS", "").strip()
    if configured:
        return [o.strip() for o in configured.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]


cors_origins = _parse_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ── Rate Limiting (in-memory, per-IP) ────────────────────────────────
RATE_LIMIT = int(os.getenv("RATE_LIMIT_RPM", "15"))  # requests per minute
_rate_store: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/research"):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = _rate_store[client_ip]
        # Remove entries older than 60s
        _rate_store[client_ip] = [t for t in window if now - t < 60]
        if len(_rate_store[client_ip]) >= RATE_LIMIT:
            logger.warning(f"Rate limit hit for {client_ip}")
            return HTMLResponse(
                content=json.dumps({"detail": "Rate limit exceeded. Try again in a minute."}),
                status_code=429,
                media_type="application/json",
            )
        _rate_store[client_ip].append(now)
    response = await call_next(request)
    return response


searcher = TavilySearch()
memory = ResearchMemory()
pdf_exporter = ResearchPDFExporter()
debate_agent = DebateAgent()
mindmap_agent = MindmapAgent()
timeline_agent = TimelineAgent()
verify_agent = VerifyAgent()


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    depth: Literal["basic", "deep"] = "deep"


@app.get("/")
async def root():
    return {
        "message": "Nexus Research API",
        "version": "2.0.0",
        "status": "operational",
        "dimensions": ["debate", "timeline", "knowledge_graph", "fact_check"],
        "keys_configured": {
            "groq": bool(GROQ_KEY),
            "tavily": bool(TAVILY_KEY),
        },
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rate_limit_rpm": RATE_LIMIT,
        "cors_origins": cors_origins,
        "keys_configured": {
            "groq": bool(GROQ_KEY),
            "tavily": bool(TAVILY_KEY),
        },
    }


# ── Helper: safe agent run ──────────────────────────────────────────
async def _safe_run(name: str, coro):
    """Run an agent coroutine; return fallback dict on failure instead of crashing."""
    try:
        return await coro
    except Exception as exc:
        logger.exception(f"Agent '{name}' failed: {exc}")
        return {"error": f"{name} agent failed: {str(exc)}"}


@app.post("/api/research")
async def run_research(request: ResearchRequest):
    if not GROQ_KEY or not TAVILY_KEY:
        raise HTTPException(
            status_code=503,
            detail="API keys not configured. Set GROQ_API_KEY and TAVILY_API_KEY in .env",
        )

    research_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"[{research_id}] Research started: {request.query!r} (depth={request.depth})")

    # Parallel: web search + related memory context
    search_results = await searcher.search(request.query, depth=request.depth)
    related = memory.get_related(request.query, n_results=3)

    # Run all 4 intelligence agents in parallel — each is individually fault-tolerant
    debate, mindmap, timeline, verify = await asyncio.gather(
        _safe_run("debate", debate_agent.run(request.query, search_results, related)),
        _safe_run("mindmap", mindmap_agent.run(request.query, search_results, related)),
        _safe_run("timeline", timeline_agent.run(request.query, search_results)),
        _safe_run("verify", verify_agent.run(request.query, search_results)),
    )

    result = {
        "id": research_id,
        "query": request.query,
        "timestamp": timestamp,
        "search_summary": search_results[:5],
        "debate": debate,
        "mindmap": mindmap,
        "timeline": timeline,
        "verify": verify,
    }

    memory.save(research_id, request.query, result)
    logger.info(f"[{research_id}] Research complete — saved to ChromaDB")
    return result


# ── WebSocket Streaming ─────────────────────────────────────────────
@app.websocket("/ws/research")
async def ws_research(ws: WebSocket):
    await ws.accept()
    try:
        data = await ws.receive_json()
        query = data.get("query", "").strip()
        ws_depth = data.get("depth", "deep")
        if not query:
            await ws.send_json({"type": "error", "message": "Empty query"})
            await ws.close()
            return
        if not GROQ_KEY or not TAVILY_KEY:
            await ws.send_json({"type": "error", "message": "API keys not configured"})
            await ws.close()
            return

        research_id = uuid.uuid4().hex[:12]
        timestamp = datetime.now(timezone.utc).isoformat()
        logger.info(f"[WS:{research_id}] Streaming research: {query!r}")

        # Stage 1: Search
        await ws.send_json({"type": "stage", "stage": "search", "status": "running"})
        search_results = await searcher.search(query, depth=ws_depth)
        related = memory.get_related(query, n_results=3)
        await ws.send_json({"type": "stage", "stage": "search", "status": "done", "count": len(search_results)})

        # Stage 2-5: Run all agents in parallel and stream completion per stage
        async def _run_named_agent(name: str, coro):
            return name, await _safe_run(name, coro)

        agent_tasks = [
            asyncio.create_task(_run_named_agent("debate", debate_agent.run(query, search_results, related))),
            asyncio.create_task(_run_named_agent("timeline", timeline_agent.run(query, search_results))),
            asyncio.create_task(_run_named_agent("graph", mindmap_agent.run(query, search_results, related))),
            asyncio.create_task(_run_named_agent("verify", verify_agent.run(query, search_results))),
        ]
        for stage in ["debate", "timeline", "graph", "verify"]:
            await ws.send_json({"type": "stage", "stage": stage, "status": "running"})

        agent_results = {}
        for done_task in asyncio.as_completed(agent_tasks):
            name, result = await done_task
            agent_results[name] = result
            await ws.send_json({"type": "stage", "stage": name, "status": "done"})

        full_result = {
            "id": research_id,
            "query": query,
            "timestamp": timestamp,
            "search_summary": search_results[:5],
            "debate": agent_results["debate"],
            "mindmap": agent_results["graph"],
            "timeline": agent_results["timeline"],
            "verify": agent_results["verify"],
        }
        memory.save(research_id, query, full_result)
        await ws.send_json({"type": "result", "data": full_result})
        logger.info(f"[WS:{research_id}] Streaming complete")
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.exception(f"WebSocket error: {exc}")
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


@app.get("/api/history")
async def get_history():
    return memory.get_all()


@app.get("/api/history/{research_id}")
async def get_research(research_id: str):
    result = memory.get_by_id(research_id)
    if not result:
        raise HTTPException(status_code=404, detail="Research not found")
    return result


@app.delete("/api/history/{research_id}")
async def delete_research(research_id: str):
    memory.delete(research_id)
    return {"message": "Deleted"}


@app.post("/api/export/pdf/{research_id}")
async def export_pdf(research_id: str):
    result = memory.get_by_id(research_id)
    if not result:
        raise HTTPException(status_code=404, detail="Research not found")
    pdf_path = pdf_exporter.export(result)
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"nexus-research-{research_id}.pdf",
    )


# ── Markdown Export ──────────────────────────────────────────────────
@app.get("/api/export/markdown/{research_id}")
async def export_markdown(research_id: str):
    result = memory.get_by_id(research_id)
    if not result:
        raise HTTPException(status_code=404, detail="Research not found")

    md = _build_markdown(result)
    return HTMLResponse(content=md, media_type="text/markdown", headers={
        "Content-Disposition": f'attachment; filename="nexus-{research_id}.md"'
    })


@app.get("/api/export/html/{research_id}")
async def export_html(research_id: str):
    result = memory.get_by_id(research_id)
    if not result:
        raise HTTPException(status_code=404, detail="Research not found")

    md = _build_markdown(result)
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Nexus Research — {_esc_html(result.get('query',''))}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:800px;margin:40px auto;padding:0 20px;line-height:1.7;color:#222}}
h1{{color:#00aa66}}h2{{color:#0077cc;border-bottom:1px solid #eee;padding-bottom:4px}}
h3{{color:#555}}code{{background:#f4f4f4;padding:2px 6px;border-radius:3px}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#f0f0f0}}blockquote{{border-left:3px solid #00aa66;margin:0;padding:4px 16px;color:#555}}</style></head>
<body>{"".join(f"<p>{line}</p>" if not line.startswith("#") and not line.startswith("|") and not line.startswith(">") and not line.startswith("-") and line.strip() else _md_line_to_html(line) for line in md.split(chr(10)))}</body></html>"""
    return HTMLResponse(content=html, headers={
        "Content-Disposition": f'attachment; filename="nexus-{research_id}.html"'
    })


def _esc_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_line_to_html(line: str) -> str:
    s = _esc_html(line)
    if s.startswith("### "):
        return f"<h3>{s[4:]}</h3>"
    if s.startswith("## "):
        return f"<h2>{s[3:]}</h2>"
    if s.startswith("# "):
        return f"<h1>{s[2:]}</h1>"
    if s.startswith("&gt; "):
        return f"<blockquote>{s[5:]}</blockquote>"
    if s.startswith("- "):
        return f"<li>{s[2:]}</li>"
    if s.startswith("|"):
        return f"<p><code>{s}</code></p>"
    if not s.strip():
        return "<br>"
    return f"<p>{s}</p>"


def _build_markdown(data: dict) -> str:
    lines = [
        f"# Nexus Research Report",
        f"**Query:** {data.get('query', '')}",
        f"**ID:** {data.get('id', '')} | **Generated:** {data.get('timestamp', '')}",
        "",
        "---",
        "",
    ]

    # Debate
    debate = data.get("debate", {})
    if debate and not debate.get("error"):
        lines.append("## 1. Debate Analysis")
        ms = debate.get("mainstream_view", {})
        ct = debate.get("contrarian_view", {})
        lines.append(f"### Mainstream: {ms.get('title', '')}")
        lines.append(ms.get("summary", ""))
        for pt in ms.get("key_points", []):
            lines.append(f"- {pt}")
        lines.append("")
        lines.append(f"### Contrarian: {ct.get('title', '')}")
        lines.append(ct.get("summary", ""))
        for pt in ct.get("key_points", []):
            lines.append(f"- {pt}")
        lines.append("")
        lines.append(f"### Synthesis")
        lines.append(f"> {debate.get('synthesis', '')}")
        lines.append(f"**Verdict:** {debate.get('verdict', 'nuanced')}")
        lines.append("")

    # Timeline
    timeline = data.get("timeline", {})
    if timeline and not timeline.get("error") and timeline.get("events"):
        lines.append("## 2. Historical Timeline")
        if timeline.get("era_summary"):
            lines.append(f"*{timeline['era_summary']}*")
            lines.append("")
        for ev in timeline["events"]:
            lines.append(f"- **{ev.get('date', '')}** — {ev.get('event', '')}")
            if ev.get("significance"):
                lines.append(f"  *{ev['significance']}*")
        if timeline.get("future_outlook"):
            lines.append(f"\n**Outlook:** {timeline['future_outlook']}")
        lines.append("")

    # Fact Verification
    verify = data.get("verify", {})
    if verify and not verify.get("error") and verify.get("claims"):
        lines.append("## 3. Fact Verification")
        pct = int((verify.get("overall_confidence", 0)) * 100)
        lines.append(f"**Overall Confidence:** {pct}%")
        lines.append(f"{verify.get('recommendation', '')}")
        lines.append("")
        for c in verify["claims"]:
            status = (c.get("status", "unverified")).upper()
            conf = int(c.get("confidence_score", 0) * 100)
            lines.append(f"- [{status} {conf}%] {c.get('claim', '')}")
        if verify.get("key_uncertainties"):
            lines.append("\n**Key Uncertainties:**")
            for u in verify["key_uncertainties"]:
                lines.append(f"- {u}")
        lines.append("")

    # Knowledge Graph
    mindmap = data.get("mindmap", {})
    if mindmap and not mindmap.get("error") and mindmap.get("nodes"):
        lines.append("## 4. Knowledge Graph")
        if mindmap.get("central_insight"):
            lines.append(f"> {mindmap['central_insight']}")
            lines.append("")
        for n in mindmap["nodes"]:
            lines.append(f"- **{n.get('label', '')}** [{n.get('type', '')}]: {n.get('description', '')}")
        lines.append("")

    # Sources
    sources = data.get("search_summary", [])
    if sources:
        lines.append("## Sources")
        for s in sources:
            if s.get("url"):
                lines.append(f"- [{s.get('title', 'Source')}]({s['url']})")
            else:
                lines.append(f"- {s.get('title', 'Source')}")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by Nexus Research*")
    return "\n".join(lines)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

