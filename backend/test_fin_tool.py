import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.tools.financial_data_api import FetchFinancialStatementsTool


def test_tool():
    tool = FetchFinancialStatementsTool()
    print("Executing FetchFinancialStatementsTool for MSFT...")
    result = tool.execute(ticker="MSFT", statements=["income"], periods=3)

    if result.success:
        print(f"Success! Source: {result.data.get('source')}")
        income = result.data.get("income_statement", {})
        rev = income.get("revenue", {})
        print(f"Revenue Data: {rev}")
    else:
        print(f"Failed: {result.error}")


if __name__ == "__main__":
    test_tool()
