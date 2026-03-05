"""
OFAS Financial Data API — Fetch Financial Statements from Public Sources

MCP Tool: fetch_financial_statements
- SEC EDGAR XBRL API (primary, free, no API key)
- Yahoo Finance fallback (via yfinance, free, no API key)

Both sources are free and require NO API keys.
"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog

from app.core.tools.tool_router import BaseTool, ToolResult

logger = structlog.get_logger()

# SEC EDGAR API base URL (free, no API key needed)
SEC_EDGAR_BASE = "https://data.sec.gov"
SEC_WWW_BASE = "https://www.sec.gov"
SEC_COMPANY_TICKERS = f"{SEC_WWW_BASE}/files/company_tickers.json"
SEC_COMPANY_FACTS = f"{SEC_EDGAR_BASE}/api/xbrl/companyfacts"

# Required headers for SEC EDGAR (must identify the software and provide a contact email)
SEC_HEADERS = {
    "User-Agent": "DealForge-OFAS/1.0 (contact@dealforge.ai)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}

# XBRL taxonomy mappings (Prioritized order: most common/modern first)
XBRL_INCOME_STATEMENT = {
    # Modern Revenue fields (ASC 606)
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "RevenueFromContractWithCustomerIncludingAssessedTax": "revenue",
    # Legacy/General Revenue fields
    "Revenues": "revenue",
    "SalesRevenueNet": "revenue",
    "TotalRevenues": "revenue",
    "CostOfRevenue": "cost_of_revenue",
    "CostOfGoodsAndServicesSold": "cost_of_revenue",
    "GrossProfit": "gross_profit",
    "OperatingExpenses": "operating_expenses",
    "OperatingIncomeLoss": "operating_income",
    "InterestExpense": "interest_expense",
    "IncomeTaxExpenseBenefit": "income_tax",
    "NetIncomeLoss": "net_income",
    "EarningsPerShareBasic": "eps_basic",
    "EarningsPerShareDiluted": "eps_diluted",
    "WeightedAverageNumberOfSharesOutstandingBasic": "shares_basic",
    "WeightedAverageNumberOfDilutedSharesOutstanding": "shares_diluted",
}

XBRL_BALANCE_SHEET = {
    "Assets": "total_assets",
    "AssetsCurrent": "current_assets",
    "CashAndCashEquivalentsAtCarryingValue": "cash",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": "cash",
    "Liabilities": "total_liabilities",
    "LiabilitiesCurrent": "current_liabilities",
    "LongTermDebt": "long_term_debt",
    "LongTermDebtNoncurrent": "long_term_debt",
    "StockholdersEquity": "shareholders_equity",
    "CommonStockSharesOutstanding": "shares_outstanding",
}

XBRL_CASH_FLOW = {
    "NetCashProvidedByUsedInOperatingActivities": "cfo",
    "NetCashProvidedByUsedInInvestingActivities": "cfi",
    "NetCashProvidedByUsedInFinancingActivities": "cff",
    "DepreciationDepletionAndAmortization": "dna",
    "PaymentsToAcquirePropertyPlantAndEquipment": "capex",
    "PaymentOfDividends": "dividends",
    "PaymentsForRepurchaseOfCommonStock": "buybacks",
}


def _try_import_requests():
    """Lazy import requests to avoid startup dependency"""
    try:
        import requests

        return requests
    except ImportError:
        return None


def _try_import_yfinance():
    """Lazy import yfinance for Yahoo Finance fallback"""
    try:
        import yfinance as yf

        return yf
    except ImportError:
        return None


class FetchFinancialStatementsTool(BaseTool):
    """
    Fetch historical financial statements from SEC EDGAR (XBRL API).

    Falls back to Yahoo Finance if EDGAR data is unavailable.
    Both sources are FREE and require NO API keys.
    """

    def __init__(self):
        super().__init__(
            name="fetch_financial_statements",
            description=(
                "Retrieve historical financial statements (income statement, "
                "balance sheet, cash flow) from SEC EDGAR XBRL API. "
                "Free, no API key required. Falls back to Yahoo Finance."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., 'MSFT', 'AAPL')",
                },
                "statements": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["income", "balance", "cashflow"],
                    },
                    "description": "Which statements to fetch",
                },
                "periods": {
                    "type": "integer",
                    "description": "Number of annual periods to fetch (default: 5)",
                    "default": 5,
                },
                "frequency": {
                    "type": "string",
                    "enum": ["annual", "quarterly"],
                    "description": "Annual or quarterly data",
                    "default": "annual",
                },
            },
            "required": ["ticker"],
        }

    def execute(
        self,
        ticker: str = "",
        statements: Optional[List[str]] = None,
        periods: int = 5,
        frequency: str = "annual",
        **kwargs,
    ) -> ToolResult:
        """Fetch financial statements — try SEC EDGAR first, then Yahoo Finance"""

        statements = statements or ["income", "balance", "cashflow"]
        ticker = ticker.upper().strip()

        if not ticker:
            return ToolResult(
                success=False,
                data=None,
                error="Ticker symbol is required",
            )

        # Try SEC EDGAR first
        result = self._fetch_from_edgar(ticker, statements, periods, frequency)
        if result and result.get("has_data"):
            return ToolResult(
                success=True,
                data={
                    "source": "sec_edgar",
                    "ticker": ticker,
                    "currency": "USD",
                    **result,
                },
            )

        # Fallback to Yahoo Finance
        logger.info("SEC EDGAR unavailable, trying Yahoo Finance", ticker=ticker)
        result = self._fetch_from_yfinance(ticker, statements, periods, frequency)
        if result and result.get("has_data"):
            return ToolResult(
                success=True,
                data={
                    "source": "yahoo_finance",
                    "ticker": ticker,
                    "currency": "USD",
                    **result,
                },
            )

        return ToolResult(
            success=False,
            data=None,
            error=(
                f"Could not fetch financial data for {ticker}. "
                f"Install 'requests' for SEC EDGAR or 'yfinance' for Yahoo Finance."
            ),
        )

    def _fetch_from_edgar(
        self,
        ticker: str,
        statements: List[str],
        periods: int,
        frequency: str,
    ) -> Optional[Dict]:
        """Fetch from SEC EDGAR XBRL API"""
        requests = _try_import_requests()
        if not requests:
            return None

        try:
            # Step 1: Get CIK from ticker
            tickers_url = SEC_COMPANY_TICKERS
            # Note: For tickers_url, we need different headers (Host: www.sec.gov)
            headers = SEC_HEADERS.copy()
            headers["Host"] = "www.sec.gov"
            resp = requests.get(tickers_url, headers=headers, timeout=10)
            resp.raise_for_status()
            tickers_data = resp.json()

            cik = None
            for _, entry in tickers_data.items():
                if entry.get("ticker", "").upper() == ticker:
                    cik = str(entry["cik_str"]).zfill(10)
                    break

            if not cik:
                logger.warning("Ticker not found in SEC EDGAR", ticker=ticker)
                return None

            # Step 2: Fetch company facts (XBRL data)
            facts_url = f"{SEC_COMPANY_FACTS}/CIK{cik}.json"
            headers = SEC_HEADERS.copy()
            headers["Host"] = "data.sec.gov"
            resp = requests.get(facts_url, headers=headers, timeout=30)
            resp.raise_for_status()
            facts = resp.json()

            us_gaap = facts.get("facts", {}).get("us-gaap", {})
            if not us_gaap:
                return None

            result = {
                "has_data": True,
                "cik": cik,
                "entity_name": facts.get("entityName", ticker),
            }

            # Step 3: Extract requested statements
            if "income" in statements:
                result["income_statement"] = self._extract_xbrl_items(
                    us_gaap, XBRL_INCOME_STATEMENT, periods, frequency
                )

            if "balance" in statements:
                result["balance_sheet"] = self._extract_xbrl_items(
                    us_gaap, XBRL_BALANCE_SHEET, periods, frequency
                )

            if "cashflow" in statements:
                result["cash_flow"] = self._extract_xbrl_items(
                    us_gaap, XBRL_CASH_FLOW, periods, frequency
                )

            # Extract fiscal years covered
            fiscal_years = set()
            for stmt in ["income_statement", "balance_sheet", "cash_flow"]:
                if stmt in result:
                    for item_data in result[stmt].values():
                        if isinstance(item_data, dict):
                            fiscal_years.update(item_data.keys())
            result["fiscal_years"] = sorted(fiscal_years)[-periods:]

            return result

        except Exception as e:
            logger.warning("SEC EDGAR fetch failed", ticker=ticker, error=str(e))
            return None

    def _extract_xbrl_items(
        self,
        us_gaap: Dict,
        field_map: Dict[str, str],
        periods: int,
        frequency: str,
    ) -> Dict[str, Any]:
        """Extract standardized financial items from XBRL data"""
        result = {}
        # Metadata to track which field provided which year's data
        sources = {}
        unit_filter = "10-K" if frequency == "annual" else "10-Q"

        for xbrl_field, std_name in field_map.items():
            if xbrl_field not in us_gaap:
                continue

            field_data = us_gaap[xbrl_field]
            units = field_data.get("units", {})

            # Try USD first, then 'shares', then 'USD/shares'
            values = (
                units.get("USD", [])
                or units.get("shares", [])
                or units.get("USD/shares", [])
            )

            if not values:
                continue

            if std_name not in result:
                result[std_name] = {}
                sources[std_name] = {}

            # Filter by form type and extract yearly values
            for entry in values:
                form = entry.get("form", "")
                if unit_filter not in form:
                    continue

                end_date = entry.get("end", "")
                if not end_date:
                    continue

                year = end_date[:4]
                val = entry.get("val")

                # Data prioritized by end_date (newest first)
                # If we already have data for this year, only overwrite if this field is 'better'
                # or if the date is actually more recent for the same fiscal year
                current_entry = result[std_name].get(year)
                if current_entry is None or end_date > sources[std_name].get(year, ""):
                    result[std_name][year] = val
                    sources[std_name][year] = end_date

        # Post-process: limit to requested periods and sort years
        processed_result = {}
        for std_name, years_data in result.items():
            sorted_years = sorted(years_data.keys(), reverse=True)[:periods]
            time_series = {y: years_data[y] for y in sorted(sorted_years)}
            if time_series:
                processed_result[std_name] = time_series

        return processed_result

    def _fetch_from_yfinance(
        self,
        ticker: str,
        statements: List[str],
        periods: int,
        frequency: str,
    ) -> Optional[Dict]:
        """Fallback: fetch from Yahoo Finance via yfinance"""
        yf = _try_import_yfinance()
        if not yf:
            return None

        try:
            stock = yf.Ticker(ticker)
            result = {"has_data": False}

            if "income" in statements:
                if frequency == "annual":
                    df = stock.income_stmt
                else:
                    df = stock.quarterly_income_stmt

                if df is not None and not df.empty:
                    result["income_statement"] = self._df_to_dict(df, periods)
                    result["has_data"] = True

            if "balance" in statements:
                if frequency == "annual":
                    df = stock.balance_sheet
                else:
                    df = stock.quarterly_balance_sheet

                if df is not None and not df.empty:
                    result["balance_sheet"] = self._df_to_dict(df, periods)
                    result["has_data"] = True

            if "cashflow" in statements:
                if frequency == "annual":
                    df = stock.cashflow
                else:
                    df = stock.quarterly_cashflow

                if df is not None and not df.empty:
                    result["cash_flow"] = self._df_to_dict(df, periods)
                    result["has_data"] = True

            if result["has_data"]:
                # Extract fiscal years
                fiscal_years = set()
                for key in ["income_statement", "balance_sheet", "cash_flow"]:
                    if key in result:
                        for item_data in result[key].values():
                            if isinstance(item_data, dict):
                                fiscal_years.update(item_data.keys())
                result["fiscal_years"] = sorted(fiscal_years)[-periods:]

            return result

        except Exception as e:
            logger.warning("Yahoo Finance fetch failed", ticker=ticker, error=str(e))
            return None

    def _df_to_dict(self, df, periods: int) -> Dict[str, Dict[str, Any]]:
        """Convert a pandas DataFrame (from yfinance) to standardized dict"""
        result = {}
        # Columns are dates, rows are line items
        cols = list(df.columns)[:periods]

        for idx, row in df.iterrows():
            item_name = str(idx).replace(" ", "_").lower()
            time_series = {}
            for col in cols:
                year = str(col.year) if hasattr(col, "year") else str(col)[:4]
                val = row[col]
                if val is not None and str(val) != "nan":
                    try:
                        time_series[year] = float(val)
                    except (ValueError, TypeError):
                        time_series[year] = val

            if time_series:
                result[item_name] = time_series

        return result
