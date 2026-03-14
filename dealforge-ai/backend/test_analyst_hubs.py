
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Setup path to import app module
sys.path.insert(0, str(Path(__file__).parent))

from app.agents.financial_analyst import FinancialAnalystAgent

async def test_financial_analyst_hubs():
    print("Testing FinancialAnalystAgent with HubSpot (HUBS) Data...")
    
    # 1. Load the HubSpot data
    data_path = Path("hubs_test_output.json")
    if not data_path.exists():
        print(f"Error: {data_path} not found. Please run the data retrieval test first.")
        return
        
    with open(data_path, "r") as f:
        hubs_data = json.load(f)
        
    # 2. Initialize Agent
    agent = FinancialAnalystAgent()
    
    # 3. Prepare Context
    context = {
        "deal_id": "test-hubs-deal-001",
        "ticker": "HUBS",
        "company_name": "HubSpot, Inc.",
        "financial_data": hubs_data
    }
    
    task = "Analyze HubSpot's financial performance and valuation based on the 2023-2025 SEC data."
    
    # 4. Run Analysis
    print("\nRunning agent.run()... (This may take a moment as it calls the LLM)")
    result = await agent.run(task, context)
    
    if result.success:
        print("\n=== Agent Analysis Results ===")
        print(f"Confidence Score: {result.confidence}")
        
        data = result.data
        
        print("\n--- Revenue Analysis ---")
        rev = data.get("revenue_analysis", {})
        print(f"Annual Revenue: ${rev.get('annual_revenue', 0):,}")
        print(f"Growth Rate: {rev.get('growth_rate', 0)}%")
        print(f"Quality: {rev.get('quality_assessment', 'N/A')}")
        
        print("\n--- Valuation ---")
        val = data.get("valuation", {})
        print(f"DCF Estimate: ${val.get('dcf_estimate', 0):,}")
        print(f"Multiple Estimate: ${val.get('multiple_estimate', 0):,}")
        
        print("\n--- Recommendation ---")
        print(f"Recommendation: {data.get('recommendation', 'N/A').upper()}")
        
        print("\n--- Reasoning ---")
        print(result.reasoning[:1000] + "..." if len(result.reasoning) > 1000 else result.reasoning)
        
        # Save analysis to file
        output_file = "hubs_financial_analysis.json"
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\nFull analysis saved to {output_file}")
        
    else:
        print(f"Error: {result.reasoning}")

if __name__ == "__main__":
    # We need to make sure settings are loaded and LLM is configured
    # This assumes the environment or settings.json is already set up for LM Studio or Gemini
    asyncio.run(test_financial_analyst_hubs())
