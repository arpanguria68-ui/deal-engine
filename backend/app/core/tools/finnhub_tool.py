"""
Finnhub Tool

MCP Tool Equivalent
Requires FINNHUB_API_KEY
- Real-time stock prices, company news, and standard financial data
"""

import os
from typing import Dict, Any, Optional
import structlog
import httpx
from app.core.tools.tool_router import BaseTool, ToolResult
from app.config import get_settings


class FinnhubTool(BaseTool):
    """Retrieve fast, real-time quotes and company news using Finnhub API."""

    def __init__(self):
        super().__init__(
            name="finnhub_data",
            description="Fetch real-time stock quotes, basic financials, and live company news using the Finnhub API.",
        )
        self.logger = structlog.get_logger()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., AAPL)",
                },
                "endpoint": {
                    "type": "string",
                    "enum": ["quote", "company-news", "profile2", "metric"],
                    "description": "Finnhub API endpoint (quote for live prices, company-news for news)",
                    "default": "quote",
                },
                "from_date": {
                    "type": "string",
                    "description": "Start date for news (YYYY-MM-DD), required if endpoint is company-news",
                },
                "to_date": {
                    "type": "string",
                    "description": "End date for news (YYYY-MM-DD), required if endpoint is company-news",
                },
            },
            "required": ["symbol"],
        }

    async def execute(
        self,
        symbol: str,
        endpoint: str = "quote",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        settings = get_settings()
        api_key = settings.FINNHUB_API_KEY

        if not api_key:
            return ToolResult(
                success=False,
                data=None,
                error="Finnhub API key is not configured. Please set it in Settings.",
            )

        base_url = f"https://finnhub.io/api/v1/{endpoint}"
        params = {"symbol": symbol, "token": api_key}

        if endpoint == "company-news":
            if not from_date or not to_date:
                return ToolResult(
                    success=False,
                    data=None,
                    error="from_date and to_date are required for company-news endpoint (format YYYY-MM-DD).",
                )
            params["from"] = from_date
            params["to"] = to_date

        if endpoint == "metric":
            params["metric"] = "all"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(base_url, params=params)
                response.raise_for_status()
                data = response.json()

                # Truncate news to top 10 articles to avoid overwhelming LLM context
                if endpoint == "company-news" and isinstance(data, list):
                    data = data[:10]

                return ToolResult(success=True, data=data)

        except Exception as e:
            self.logger.error(
                "finnhub_failed", error=str(e), symbol=symbol, endpoint=endpoint
            )
            return ToolResult(
                success=False, data=None, error=f"Finnhub request failed: {str(e)}"
            )
