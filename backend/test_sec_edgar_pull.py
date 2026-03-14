
import asyncio
import json
import sys
from pathlib import Path

# Setup path to import app module
sys.path.insert(0, str(Path(__file__).parent))

from app.core.tools.financial_data_api import FetchFinancialStatementsTool

async def test_edgar_pull():
    print("Testing SEC EDGAR Data Retrieval for AAPL...")
    tool = FetchFinancialStatementsTool()
    
    # We want to see what EDGAR pulls specifically
    result = await tool.execute(ticker="AAPL", statements=["income", "balance"], periods=3)
    
    if result.success:
        print(f"\nSource: {result.data.get('source')}")
        print(f"Company: {result.data.get('entity_name')}")
        
        # Print a snippet of the Income Statement
        income = result.data.get("income_statement", {})
        print("\n--- Income Statement (Snippet) ---")
        for metric, years in list(income.items())[:5]:
            print(f"{metric}: {years}")
            
        # Print a snippet of the Balance Sheet
        balance = result.data.get("balance_sheet", {})
        print("\n--- Balance Sheet (Snippet) ---")
        for metric, years in list(balance.items())[:5]:
            print(f"{metric}: {years}")
            
        # Save full output for inspection if needed
        with open("edgar_test_output.json", "w") as f:
            json.dump(result.data, f, indent=2)
        print("\nFull data saved to edgar_test_output.json")
    else:
        print(f"Error: {result.error}")

if __name__ == "__main__":
    asyncio.run(test_edgar_pull())
