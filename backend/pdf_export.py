"""PDF report generation using ReportLab with styled sections for all 4D research dimensions."""

import tempfile

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class ResearchPDFExporter:
    def export(self, data: dict) -> str:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf_path = tmp.name
        tmp.close()

        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            topMargin=0.6 * inch,
            bottomMargin=0.6 * inch,
            leftMargin=0.7 * inch,
            rightMargin=0.7 * inch,
        )

        styles = getSampleStyleSheet()

        def style(name, **kwargs):
            return ParagraphStyle(name, parent=styles["Normal"], **kwargs)

        title_s = style(
            "NTitle",
            fontSize=24,
            textColor=HexColor("#00ff88"),
            fontName="Helvetica-Bold",
            spaceAfter=4,
            alignment=TA_LEFT,
        )
        sub_s = style(
            "NSub",
            fontSize=11,
            textColor=HexColor("#666688"),
            spaceAfter=2,
        )
        h2_s = style(
            "NH2",
            fontSize=14,
            textColor=HexColor("#00cc66"),
            fontName="Helvetica-Bold",
            spaceBefore=18,
            spaceAfter=6,
        )
        h3_s = style(
            "NH3",
            fontSize=11,
            textColor=HexColor("#3b82f6"),
            fontName="Helvetica-Bold",
            spaceBefore=10,
            spaceAfter=4,
        )
        body_s = style(
            "NBody",
            fontSize=10,
            textColor=HexColor("#222222"),
            leading=15,
            spaceAfter=6,
        )
        small_s = style(
            "NSmall",
            fontSize=9,
            textColor=HexColor("#555555"),
            leading=13,
            spaceAfter=4,
        )
        green_s = style(
            "NGreen",
            fontSize=10,
            textColor=HexColor("#006633"),
            leading=14,
            spaceAfter=4,
        )

        story = []

        # ── Header ──────────────────────────────────────────────────────────
        story.append(Paragraph("NEXUS RESEARCH", title_s))
        story.append(Paragraph(f"Query: <b>{data.get('query', '')}</b>", body_s))
        story.append(Paragraph(f"Report ID: {data.get('id', '')}  ·  Generated: {data.get('timestamp', '')}", sub_s))
        story.append(HRFlowable(width="100%", thickness=2, color=HexColor("#00ff88"), spaceAfter=8))
        story.append(Spacer(1, 6))

        # ── Debate ──────────────────────────────────────────────────────────
        debate = data.get("debate", {})
        if debate and "mainstream_view" in debate:
            story.append(Paragraph("01 — DEBATE ANALYSIS", h2_s))
            ms = debate.get("mainstream_view", {})
            ct = debate.get("contrarian_view", {})

            story.append(Paragraph(f"Mainstream View: {ms.get('title', '')}", h3_s))
            story.append(Paragraph(ms.get("summary", ""), body_s))
            for pt in ms.get("key_points", []):
                story.append(Paragraph(f"→  {pt}", small_s))

            story.append(Paragraph(f"Contrarian View: {ct.get('title', '')}", h3_s))
            story.append(Paragraph(ct.get("summary", ""), body_s))
            for pt in ct.get("key_points", []):
                story.append(Paragraph(f"→  {pt}", small_s))

            story.append(Paragraph("Synthesis", h3_s))
            story.append(Paragraph(debate.get("synthesis", ""), green_s))

        # ── Timeline ────────────────────────────────────────────────────────
        timeline = data.get("timeline", {})
        if timeline and "events" in timeline:
            story.append(Paragraph("02 — HISTORICAL TIMELINE", h2_s))
            story.append(Paragraph(timeline.get("era_summary", ""), small_s))
            for ev in timeline["events"][:12]:
                story.append(
                    Paragraph(
                        f"<b>{ev.get('date', '')}:</b>  {ev.get('event', '')}",
                        body_s,
                    )
                )
                story.append(Paragraph(ev.get("significance", ""), small_s))
            if timeline.get("future_outlook"):
                story.append(Paragraph(f"Outlook: {timeline['future_outlook']}", green_s))

        # ── Fact Verification ───────────────────────────────────────────────
        verify = data.get("verify", {})
        if verify and "claims" in verify:
            story.append(Paragraph("03 — FACT VERIFICATION", h2_s))
            pct = int((verify.get("overall_confidence", 0)) * 100)
            story.append(Paragraph(f"Overall Confidence Score: <b>{pct}%</b>", body_s))
            story.append(Paragraph(verify.get("recommendation", ""), small_s))

            table_data = [["Claim", "Status", "Confidence"]]
            for claim in verify.get("claims", [])[:8]:
                table_data.append(
                    [
                        Paragraph(claim.get("claim", ""), small_s),
                        claim.get("status", "").upper(),
                        f"{int(claim.get('confidence_score', 0) * 100)}%",
                    ]
                )
            tbl = Table(table_data, colWidths=[4.2 * inch, 1.1 * inch, 0.9 * inch])
            tbl.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#003322")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#00ff88")),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#f9f9f9"), HexColor("#ffffff")]),
                        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dddddd")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.append(tbl)

        # ── Knowledge Graph Nodes ───────────────────────────────────────────
        mindmap = data.get("mindmap", {})
        if mindmap and "nodes" in mindmap:
            story.append(Paragraph("04 — KNOWLEDGE GRAPH", h2_s))
            story.append(Paragraph(mindmap.get("central_insight", ""), green_s))
            for node in mindmap["nodes"][:12]:
                story.append(
                    Paragraph(
                        f"<b>{node.get('label', '')}</b> [{node.get('type', '')}]:  {node.get('description', '')}",
                        small_s,
                    )
                )

        doc.build(story)
        return pdf_path
