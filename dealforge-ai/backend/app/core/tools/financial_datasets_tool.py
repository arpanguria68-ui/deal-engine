"""
Financial Datasets Tool

MCP Tool Equivalent
Requires FINANCIAL_DATASETS_API_KEY
- Comprehensive financial statements (Income, Balance Sheet, Cash Flow), actuals and estimates.
"""

import os
from typing import Dict, Any, Optional
import structlog
import httpx
from app.core.tools.tool_router import BaseTool, ToolResult
from app.config import get_settings


class FinancialDatasetsTool(BaseTool):
    """Retrieve detailed financial statements using Financial Datasets AI API."""

    def __init__(self):
        super().__init__(
            name="financial_datasets",
            description="Fetch comprehensive financial statements (Income Statement, Balance Sheet, Cash Flow) and prices from Financial Datasets.",
        )
        self.logger = structlog.get_logger()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., AAPL)",
                },
                "statement_type": {
                    "type": "string",
                    "enum": [
                        "income-statements",
                        "balance-sheets",
                        "cash-flow-statements",
                    ],
                    "description": "Type of financial statement to retrieve",
                    "default": "income-statements",
                },
                "period": {
                    "type": "string",
                    "enum": ["annual", "quarterly", "ttm"],
                    "description": "Reporting period frequency",
                    "default": "annual",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of periods to return",
                    "default": 3,
                },
            },
            "required": ["ticker"],
        }

    async def execute(
        self,
        ticker: str,
        statement_type: str = "income-statements",
        period: str = "annual",
        limit: int = 3,
        **kwargs,
    ) -> ToolResult:
        settings = get_settings()
        api_key = settings.FINANCIAL_DATASETS_API_KEY

        if not api_key:
            return ToolResult(
                success=False,
                data=None,
                error="Financial Datasets API key is not configured. Please set it in Settings.",
            )

        base_url = f"https://api.financialdatasets.ai/financials/{statement_type}"
        params = {
            "ticker": ticker,
            "period": period,
            "limit": limit,
        }
        headers = {"X-API-KEY": api_key}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(base_url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

                return ToolResult(success=True, data=data)

        except Exception as e:
            self.logger.error("financial_datasets_failed", error=str(e), ticker=ticker)
            return ToolResult(
                success=False,
                data=None,
                error=f"Financial Datasets request failed: {str(e)}",
            )
