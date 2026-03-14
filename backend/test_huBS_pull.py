
import asyncio
import json
import sys
from pathlib import Path

# Setup path to import app module
sys.path.insert(0, str(Path(__file__).parent))

from app.core.tools.financial_data_api import FetchFinancialStatementsTool

async def test_huBS_pull():
    print("Testing SEC EDGAR Data Retrieval for HUBS (HubSpot)...")
    tool = FetchFinancialStatementsTool()
    
    # We want to see what EDGAR pulls specifically for HUBS
    result = await tool.execute(ticker="HUBS", statements=["income", "balance"], periods=3)
    
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
            
        # Save full output for inspection
        with open("hubs_test_output.json", "w") as f:
            json.dump(result.data, f, indent=2)
        print("\nFull data saved to hubs_test_output.json")
    else:
        print(f"Error: {result.error}")

if __name__ == "__main__":
    asyncio.run(test_huBS_pull())
