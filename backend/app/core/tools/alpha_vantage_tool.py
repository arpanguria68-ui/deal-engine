"""
Alpha Vantage Tool

MCP Tool Equivalent
Requires ALPHA_VANTAGE_API_KEY
- Prices, technical indicators (RSI, MACD, SMA), Forex
"""

import os
from typing import Dict, Any, Optional
import structlog
from app.core.tools.tool_router import BaseTool, ToolResult
from app.config import get_settings
import httpx


class AlphaVantageTool(BaseTool):
    """Retrieve technical indicators and market data using Alpha Vantage."""

    def __init__(self):
        super().__init__(
            name="alpha_vantage",
            description="Fetch stock time series data and technical indicators (RSI, MACD, SMA, EMA) using the Alpha Vantage API.",
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
                "function": {
                    "type": "string",
                    "enum": ["TIME_SERIES_DAILY", "SMA", "EMA", "MACD", "RSI"],
                    "description": "Alpha Vantage API function to call",
                    "default": "TIME_SERIES_DAILY",
                },
                "interval": {
                    "type": "string",
                    "enum": [
                        "daily",
                        "weekly",
                        "monthly",
                        "1min",
                        "5min",
                        "15min",
                        "30min",
                        "60min",
                    ],
                    "description": "Time interval (for technical indicators)",
                    "default": "daily",
                },
                "time_period": {
                    "type": "integer",
                    "description": "Number of data points used to calculate each indicator value",
                    "default": 14,
                },
            },
            "required": ["symbol"],
        }

    async def execute(
        self,
        symbol: str,
        function: str = "TIME_SERIES_DAILY",
        interval: str = "daily",
        time_period: int = 14,
        **kwargs,
    ) -> ToolResult:
        settings = get_settings()
        api_key = settings.ALPHA_VANTAGE_API_KEY

        if not api_key:
            return ToolResult(
                success=False,
                data=None,
                error="Alpha Vantage API key is not configured. Please set it in Settings.",
            )

        base_url = "https://www.alphavantage.co/query"
        params = {
            "function": function,
            "symbol": symbol,
            "apikey": api_key,
        }

        if function in ["SMA", "EMA", "MACD", "RSI"]:
            params["interval"] = interval
            params["time_period"] = time_period
            params["series_type"] = "close"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(base_url, params=params)
                response.raise_for_status()
                data = response.json()

                if "Error Message" in data:
                    return ToolResult(
                        success=False, data=None, error=data["Error Message"]
                    )
                if (
                    "Information" in data
                    and "rate limit" in data["Information"].lower()
                ):
                    return ToolResult(
                        success=False, data=None, error=data["Information"]
                    )

                # Limit data size to avoid context overflow
                meta = data.get("Meta Data", {})
                time_series_key = next(
                    (
                        k
                        for k in data.keys()
                        if "Time Series" in k or "Technical Analysis" in k
                    ),
                    None,
                )

                if time_series_key:
                    ts_data = data[time_series_key]
                    # Get the 5 most recent dates
                    recent_dates = sorted(ts_data.keys(), reverse=True)[:5]
                    recent_data = {date: ts_data[date] for date in recent_dates}

                    return ToolResult(
                        success=True,
                        data={
                            "meta": meta,
                            "recent_data": recent_data,
                            "note": f"Showing latest 5 data points for {function}",
                        },
                    )

                return ToolResult(success=True, data=data)

        except Exception as e:
            self.logger.error("alpha_vantage_failed", error=str(e), symbol=symbol)
            return ToolResult(
                success=False,
                data=None,
                error=f"Alpha Vantage request failed: {str(e)}",
            )
