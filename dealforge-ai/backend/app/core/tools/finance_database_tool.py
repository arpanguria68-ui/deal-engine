"""
FinanceDatabase Tool — Offline Peer Discovery

MCP Tool: peer_discovery
- Uses JerBouma/FinanceDatabase (300K+ symbols)
- Offline, no API key required
- Filters by sector, industry, country, market cap
"""

from typing import Dict, Any, List, Optional
import structlog
from app.core.tools.tool_router import BaseTool, ToolResult


# Lazy import to avoid startup delays
def _try_import_fd():
    try:
        import financedatabase as fd

        return fd
    except ImportError:
        return None


class PeerDiscoveryTool(BaseTool):
    """Discover comparable companies using 300K+ offline symbol database."""

    def __init__(self):
        super().__init__(
            name="peer_discovery",
            description="Discover comparable companies and peer groups by filtering on sector, industry, country, and market capitalization using an offline database of 300,000+ symbols.",
        )
        self.logger = structlog.get_logger()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sector": {
                    "type": "string",
                    "description": "Sector to filter by (e.g., 'Technology', 'Healthcare')",
                },
                "industry": {
                    "type": "string",
                    "description": "Industry to filter by (e.g., 'Software - Application')",
                },
                "country": {
                    "type": "string",
                    "description": "Country to filter by (e.g., 'United States', 'India')",
                },
                "market_cap": {
                    "type": "string",
                    "description": "Market capitalization category (e.g., 'Large Cap', 'Mega Cap', 'Small Cap')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of peers to return (default: 20, max: 100)",
                    "default": 20,
                },
            },
            "required": [],
        }

    def execute(
        self,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        country: Optional[str] = None,
        market_cap: Optional[str] = None,
        limit: int = 20,
        **kwargs,
    ) -> ToolResult:
        fd = _try_import_fd()
        if not fd:
            return ToolResult(
                success=False,
                data=None,
                error="financedatabase library not installed. Run: pip install financedatabase",
            )

        try:
            equities = fd.Equities()

            # Start with all equities, then apply filters
            # The .select() method applies filters logically ANDed together
            peers = equities.select(
                sector=sector, industry=industry, country=country, market_cap=market_cap
            )

            if peers.empty:
                return ToolResult(
                    success=True,
                    data={
                        "peers": [],
                        "message": "No matching peers found for the given criteria.",
                    },
                )

            # Limit records for performance and context window constraints
            limit = min(limit, 100)

            # Reset index to get the symbol as a column, then convert to dict
            result_df = peers.reset_index().head(limit)
            records = result_df.to_dict(orient="records")

            # Clean up the output to include only the most relevant fields
            cleaned_records = []
            for r in records:
                cleaned_records.append(
                    {
                        "symbol": r.get("symbol", ""),
                        "name": r.get("name", ""),
                        "sector": r.get("sector", ""),
                        "industry": r.get("industry", ""),
                        "country": r.get("country", ""),
                        "exchange": r.get("exchange", ""),
                        "market_cap": r.get("market_cap", ""),
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "count_returned": len(cleaned_records),
                    "total_available": len(peers),
                    "peers": cleaned_records,
                },
            )

        except Exception as e:
            self.logger.error("peer_discovery_failed", error=str(e))
            return ToolResult(
                success=False,
                data=None,
                error=f"Internal error discovering peers: {str(e)}",
            )
