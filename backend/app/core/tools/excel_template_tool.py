"""
Excel Template Tool — Read and query financial model templates from the Knowledge Base.

Lets agents discover available templates and read their structure/data.
"""

import os
from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog

from app.core.tools.tool_router import BaseTool, ToolResult

logger = structlog.get_logger()

# Knowledge base directories with Excel templates
TEMPLATE_DIRS = [
    r"F:\code project\Kimi_Agent_DealForge AI PRD\Knowledge managerment\Excel knowledge",
]

# Template categories for agent discovery
TEMPLATE_CATEGORIES = {
    "3_statement": {
        "patterns": [
            "three_statement",
            "three-statement",
            "3_statement",
            "income_statement",
            "balance_sheet",
        ],
        "description": "Three-Statement Financial Model (IS, BS, CF)",
    },
    "dcf": {
        "patterns": ["dcf", "discounted_cash_flow"],
        "description": "Discounted Cash Flow Valuation Model",
    },
    "lbo": {
        "patterns": ["lbo", "leveraged_buyout", "cap_table", "waterfall"],
        "description": "Leveraged Buyout / Cap Table / Returns Waterfall",
    },
    "debt": {
        "patterns": ["debt_schedule", "debt"],
        "description": "Debt Schedule and Amortization Model",
    },
    "sensitivity": {
        "patterns": ["sensitivity", "scenario"],
        "description": "Sensitivity / Scenario Analysis Model",
    },
    "accretion_dilution": {
        "patterns": ["accretion", "dilution", "m&a", "merger"],
        "description": "M&A Accretion / Dilution Model",
    },
    "saas": {
        "patterns": ["saas", "subscription", "recurring"],
        "description": "SaaS / Subscription Business Model",
    },
    "ecommerce": {
        "patterns": ["ecommerce", "commerce", "retail"],
        "description": "E-commerce / Retail Business Model",
    },
    "fcfe": {
        "patterns": ["fcfe", "free_cash_flow_equity"],
        "description": "Free Cash Flow to Equity Model",
    },
    "general": {
        "patterns": ["financial", "planning", "forecast"],
        "description": "General Financial Planning Templates",
    },
}


class ExcelTemplateTool(BaseTool):
    """Tool that lets agents discover and read Excel financial model templates."""

    def __init__(self):
        super().__init__(
            name="excel_template",
            description="Search and read Excel financial model templates. "
            "Supports: 3-Statement, DCF, LBO, Debt Schedule, Sensitivity, M&A, SaaS models.",
        )
        self._template_index: Optional[List[Dict]] = None

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "search", "read"],
                    "description": "Action: 'list' all templates, 'search' by category/keyword, 'read' a specific template",
                },
                "category": {
                    "type": "string",
                    "description": "Template category (for 'search'): 3_statement, dcf, lbo, debt, sensitivity, etc.",
                },
                "query": {
                    "type": "string",
                    "description": "Search keyword (for 'search')",
                },
                "file_name": {
                    "type": "string",
                    "description": "Exact file name to read (for 'read')",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str = "list",
        category: str = "",
        query: str = "",
        file_name: str = "",
    ) -> ToolResult:
        """Execute the template tool action."""
        try:
            if action == "list":
                return self._list_templates()
            elif action == "search":
                return self._search_templates(category, query)
            elif action == "read":
                return self._read_template(file_name)
            else:
                return ToolResult(
                    success=False, data=None, error=f"Unknown action: {action}"
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

    def _build_index(self) -> List[Dict]:
        """Scan template directories and build an index."""
        if self._template_index is not None:
            return self._template_index

        index = []
        for directory in TEMPLATE_DIRS:
            base = Path(directory)
            if not base.exists():
                continue
            for fpath in base.rglob("*.xlsx"):
                fname_lower = fpath.stem.lower().replace("-", "_").replace(" ", "_")
                cats = []
                for cat_name, cat_info in TEMPLATE_CATEGORIES.items():
                    if any(p in fname_lower for p in cat_info["patterns"]):
                        cats.append(cat_name)
                if not cats:
                    cats = ["general"]

                index.append(
                    {
                        "name": fpath.name,
                        "path": str(fpath),
                        "size_kb": round(fpath.stat().st_size / 1024, 1),
                        "categories": cats,
                        "directory": fpath.parent.name,
                    }
                )

        self._template_index = index
        return index

    def _list_templates(self) -> ToolResult:
        index = self._build_index()
        # Group by category
        by_cat = {}
        for t in index:
            for cat in t["categories"]:
                by_cat.setdefault(cat, []).append(t["name"])

        return ToolResult(
            success=True,
            data={
                "total_templates": len(index),
                "by_category": {
                    k: {"count": len(v), "files": v[:5]} for k, v in by_cat.items()
                },
                "categories": {
                    k: v["description"] for k, v in TEMPLATE_CATEGORIES.items()
                },
            },
        )

    def _search_templates(self, category: str, query: str) -> ToolResult:
        index = self._build_index()
        results = []
        for t in index:
            match = False
            if category and category in t["categories"]:
                match = True
            if query and query.lower() in t["name"].lower():
                match = True
            if match:
                results.append(t)

        return ToolResult(
            success=True,
            data={
                "query": query or category,
                "results": results[:20],
                "total_matches": len(results),
            },
        )

    def _read_template(self, file_name: str) -> ToolResult:
        """Read the structure and sample data from an Excel template."""
        index = self._build_index()
        match = next((t for t in index if t["name"] == file_name), None)
        if not match:
            return ToolResult(
                success=False, data=None, error=f"Template '{file_name}' not found"
            )

        from app.core.tasks.knowledge_ingestion import KnowledgeIngestionService

        content = KnowledgeIngestionService.parse_excel(match["path"])

        return ToolResult(
            success=True,
            data={
                "file": match["name"],
                "categories": match["categories"],
                "size_kb": match["size_kb"],
                "content": content[:5000],  # First 5K chars
            },
        )
