"""
OFAS Reporting Tools — IC Memo, Deck Assembly, Compliance QA

MCP Tools:
- generate_ic_memo: Assemble Investment Committee memo (DOCX/PDF) with citation system
- generate_deal_deck: Assemble pitch deck (PPTX) from agent analysis results
"""

import io
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
import structlog

from app.core.tools.tool_router import BaseTool, ToolResult

logger = structlog.get_logger()

OUTPUT_DIR = Path(
    r"F:\code project\Kimi_Agent_DealForge AI PRD\dealforge-ai\backend\ofas_outputs"
)


# ═══════════════════════════════════════════════
#  1. IC Memo Generator
# ═══════════════════════════════════════════════


class GenerateICMemoTool(BaseTool):
    """
    Generate an Investment Committee memo with structured sections
    and a citation/exhibit system linking back to RAG chunk IDs.

    Output: PDF file (via fpdf2) with appendix of source citations.
    """

    def __init__(self):
        super().__init__(
            name="generate_ic_memo",
            description=(
                "Generate an Investment Committee memo (PDF) with structured sections, "
                "financial exhibits, and a citation system linking to RAG sources."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Company ticker"},
                "deal_name": {"type": "string", "description": "Deal name"},
                "sections": {
                    "type": "object",
                    "description": (
                        "Memo sections: {'executive_summary': '...', "
                        "'investment_thesis': '...', 'financial_analysis': '...', "
                        "'valuation': '...', 'risks': '...', 'recommendation': '...'}"
                    ),
                },
                "exhibits": {
                    "type": "array",
                    "description": "Financial exhibits/tables to include",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "data": {"type": "object"},
                        },
                    },
                },
                "citations": {
                    "type": "array",
                    "description": (
                        "Source citations: [{'id': 'C1', 'source': 'CIM p.12', "
                        "'chunk_id': 'abc123', 'content': '...'}]"
                    ),
                    "items": {"type": "object"},
                },
                "agent_results": {
                    "type": "array",
                    "description": "Raw agent outputs to include in appendix",
                },
            },
            "required": ["ticker", "deal_name", "sections"],
        }

    def execute(
        self,
        ticker: str = "",
        deal_name: str = "",
        sections: Optional[Dict] = None,
        exhibits: Optional[List[Dict]] = None,
        citations: Optional[List[Dict]] = None,
        agent_results: Optional[List[Dict]] = None,
        **kwargs,
    ) -> ToolResult:
        sections = sections or {}
        exhibits = exhibits or []
        citations = citations or []
        agent_results = agent_results or []

        if not sections:
            return ToolResult(
                success=False, data=None, error="At least one memo section is required"
            )

        try:
            from fpdf import FPDF

            class ICMemo(FPDF):
                def __init__(self, deal_name, ticker):
                    super().__init__()
                    self.deal_name = deal_name
                    self.ticker = ticker

                def header(self):
                    self.set_font("Helvetica", "B", 8)
                    self.set_text_color(100, 100, 100)
                    self.cell(
                        0,
                        5,
                        f"CONFIDENTIAL - {self.deal_name} ({self.ticker})",
                        align="L",
                    )
                    self.ln(3)
                    self.set_draw_color(0, 51, 102)
                    self.line(10, 12, 200, 12)
                    self.ln(5)

                def footer(self):
                    self.set_y(-15)
                    self.set_font("Helvetica", "I", 7)
                    self.set_text_color(150, 150, 150)
                    self.cell(
                        0,
                        10,
                        f"Page {self.page_no()}/{{nb}} | OFAS IC Memo | {datetime.utcnow().strftime('%Y-%m-%d')}",
                        align="C",
                    )

                def section_title(self, title):
                    self.set_font("Helvetica", "B", 14)
                    self.set_text_color(0, 51, 102)
                    self.cell(0, 10, self._clean(title), new_x="LMARGIN", new_y="NEXT")
                    self.set_draw_color(0, 51, 102)
                    self.line(10, self.get_y(), 200, self.get_y())
                    self.ln(3)

                def body_text(self, text):
                    self.set_font("Helvetica", "", 10)
                    self.set_text_color(30, 30, 30)
                    self.multi_cell(0, 5, self._clean(text))
                    self.ln(3)

                def citation_ref(self, citation_id):
                    self.set_font("Helvetica", "", 8)
                    self.set_text_color(0, 100, 200)
                    self.write(4, f" [{citation_id}]")
                    self.set_text_color(30, 30, 30)

                def _clean(self, text):
                    if not text:
                        return ""
                    # Replace common unicode chars that break Helvetica
                    replacements = {
                        "\u2014": "--",  # em dash
                        "\u2013": "-",  # en dash
                        "\u2018": "'",  # left single quote
                        "\u2019": "'",  # right single quote
                        "\u201c": '"',  # left double quote
                        "\u201d": '"',  # right double quote
                        "\u2022": "*",  # bullet
                        "\u2026": "...",  # ellipsis
                        "\u00a0": " ",  # non-breaking space
                    }
                    for old, new in replacements.items():
                        text = text.replace(old, new)
                    return text.encode("latin-1", "replace").decode("latin-1")

            pdf = ICMemo(deal_name, ticker)
            pdf.alias_nb_pages()

            # Cover page
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 28)
            pdf.set_text_color(0, 51, 102)
            pdf.ln(40)
            pdf.cell(
                0, 15, pdf._clean(deal_name), align="C", new_x="LMARGIN", new_y="NEXT"
            )
            pdf.set_font("Helvetica", "", 16)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(
                0,
                10,
                "Investment Committee Memorandum",
                align="C",
                new_x="LMARGIN",
                new_y="NEXT",
            )
            pdf.ln(10)
            pdf.set_font("Helvetica", "", 12)
            pdf.cell(
                0, 8, f"Ticker: {ticker}", align="C", new_x="LMARGIN", new_y="NEXT"
            )
            pdf.cell(
                0,
                8,
                f"Date: {datetime.utcnow().strftime('%B %d, %Y')}",
                align="C",
                new_x="LMARGIN",
                new_y="NEXT",
            )
            pdf.cell(
                0,
                8,
                "Prepared by: OFAS Multi-Agent System",
                align="C",
                new_x="LMARGIN",
                new_y="NEXT",
            )

            # Standard section order
            section_order = [
                ("executive_summary", "1. EXECUTIVE SUMMARY"),
                ("investment_thesis", "2. INVESTMENT THESIS"),
                ("company_overview", "3. COMPANY OVERVIEW"),
                ("market_analysis", "4. MARKET ANALYSIS"),
                ("financial_analysis", "5. FINANCIAL ANALYSIS"),
                ("valuation", "6. VALUATION"),
                ("risks", "7. RISK ASSESSMENT"),
                ("recommendation", "8. RECOMMENDATION"),
            ]

            for key, title in section_order:
                content = sections.get(key)
                if content:
                    pdf.add_page()
                    pdf.section_title(title)
                    pdf.body_text(content)

            # Exhibits
            if exhibits:
                pdf.add_page()
                pdf.section_title("EXHIBITS")
                for i, exhibit in enumerate(exhibits):
                    pdf.set_font("Helvetica", "B", 11)
                    pdf.cell(
                        0,
                        8,
                        pdf._clean(f"Exhibit {i+1}: {exhibit.get('title', '')}"),
                        new_x="LMARGIN",
                        new_y="NEXT",
                    )
                    data = exhibit.get("data", {})
                    if isinstance(data, dict):
                        for k, v in data.items():
                            pdf.set_font("Helvetica", "", 9)
                            pdf.cell(
                                0,
                                5,
                                pdf._clean(f"  {k}: {v}"),
                                new_x="LMARGIN",
                                new_y="NEXT",
                            )
                    pdf.ln(5)

            # Citations appendix
            if citations:
                pdf.add_page()
                pdf.section_title("SOURCE CITATIONS")
                for cit in citations:
                    cit_id = cit.get("id", "?")
                    source = cit.get("source", "Unknown")
                    chunk_id = cit.get("chunk_id", "")
                    content_preview = cit.get("content", "")[:200]

                    pdf.set_font("Helvetica", "B", 9)
                    pdf.cell(
                        0,
                        5,
                        pdf._clean(f"[{cit_id}] {source}"),
                        new_x="LMARGIN",
                        new_y="NEXT",
                    )
                    if chunk_id:
                        pdf.set_font("Helvetica", "I", 8)
                        pdf.cell(
                            0,
                            4,
                            pdf._clean(f"  RAG chunk: {chunk_id}"),
                            new_x="LMARGIN",
                            new_y="NEXT",
                        )
                    if content_preview:
                        pdf.set_font("Helvetica", "", 8)
                        pdf.multi_cell(0, 4, pdf._clean(f'  "{content_preview}"'))
                    pdf.ln(2)

            # Save
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{ticker}_IC_Memo_{timestamp}.pdf"
            output_path = OUTPUT_DIR / filename
            pdf.output(str(output_path))

            return ToolResult(
                success=True,
                data={
                    "memo_path": str(output_path),
                    "file_size_kb": round(output_path.stat().st_size / 1024, 1),
                    "sections_included": [k for k, _ in section_order if k in sections],
                    "exhibit_count": len(exhibits),
                    "citation_count": len(citations),
                    "pages": pdf.page_no(),
                },
            )

        except ImportError:
            # Fallback: generate markdown memo
            return self._generate_markdown_memo(
                ticker, deal_name, sections, exhibits, citations
            )
        except Exception as e:
            logger.error("IC memo generation failed", error=str(e))
            return ToolResult(success=False, data=None, error=str(e))

    def _generate_markdown_memo(
        self, ticker, deal_name, sections, exhibits, citations
    ) -> ToolResult:
        """Fallback: generate markdown memo when fpdf2 is not installed"""
        lines = [
            f"# {deal_name} — Investment Committee Memorandum",
            f"**Ticker:** {ticker}",
            f"**Date:** {datetime.utcnow().strftime('%B %d, %Y')}",
            f"**Prepared by:** OFAS Multi-Agent System",
            "",
        ]

        section_order = [
            ("executive_summary", "Executive Summary"),
            ("investment_thesis", "Investment Thesis"),
            ("financial_analysis", "Financial Analysis"),
            ("valuation", "Valuation"),
            ("risks", "Risk Assessment"),
            ("recommendation", "Recommendation"),
        ]

        for key, title in section_order:
            content = sections.get(key)
            if content:
                lines.append(f"## {title}")
                lines.append(content)
                lines.append("")

        if citations:
            lines.append("## Source Citations")
            for cit in citations:
                lines.append(
                    f"- [{cit.get('id', '?')}] {cit.get('source', '')} (chunk: {cit.get('chunk_id', 'N/A')})"
                )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{ticker}_IC_Memo_{timestamp}.md"
        output_path = OUTPUT_DIR / filename

        with open(str(output_path), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return ToolResult(
            success=True,
            data={
                "memo_path": str(output_path),
                "format": "markdown",
                "note": "fpdf2 not installed — generated markdown instead. Install: pip install fpdf2",
            },
        )


# ═══════════════════════════════════════════════
#  2. Deal Deck Assembly (PPTX)
# ═══════════════════════════════════════════════


class GenerateDealDeckTool(BaseTool):
    """
    Assemble a deal pitch deck from agent analysis results.
    Leverages the existing report_generator.generate_pptx.
    """

    def __init__(self):
        super().__init__(
            name="generate_deal_deck",
            description=(
                "Assemble a deal pitch deck (PPTX) from agent analysis results. "
                "McKinsey-style formatting with executive summary, financials, "
                "valuation, and risk slides."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "deal_name": {"type": "string"},
                "deal_data": {
                    "type": "object",
                    "description": "Deal metadata (company_name, deal_type, etc.)",
                },
                "analyst_data": {
                    "type": "object",
                    "description": "Financial analysis data",
                },
                "agent_results": {
                    "type": "array",
                    "description": "List of agent outputs to include",
                },
            },
            "required": ["ticker", "deal_name"],
        }

    def execute(
        self,
        ticker: str = "",
        deal_name: str = "",
        deal_data: Optional[Dict] = None,
        analyst_data: Optional[Dict] = None,
        agent_results: Optional[List[Dict]] = None,
        **kwargs,
    ) -> ToolResult:
        deal_data = deal_data or {"company_name": deal_name, "deal_type": "acquisition"}
        analyst_data = analyst_data or {}
        agent_results = agent_results or []

        try:
            from app.core.reports.report_generator import generate_pptx

            pptx_bytes = generate_pptx(deal_data, analyst_data, agent_results)

            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{ticker}_Deal_Deck_{timestamp}.pptx"
            output_path = OUTPUT_DIR / filename

            with open(str(output_path), "wb") as f:
                f.write(
                    pptx_bytes.getvalue()
                    if hasattr(pptx_bytes, "getvalue")
                    else pptx_bytes
                )

            return ToolResult(
                success=True,
                data={
                    "deck_path": str(output_path),
                    "file_size_kb": round(output_path.stat().st_size / 1024, 1),
                    "format": "pptx",
                    "agent_sections": len(agent_results),
                },
            )

        except ImportError:
            return ToolResult(
                success=False,
                data=None,
                error="python-pptx not installed. Run: pip install python-pptx",
            )
        except Exception as e:
            logger.error("Deck generation failed", error=str(e))
            return ToolResult(success=False, data=None, error=str(e))
