
import asyncio
import json
import sys
from pathlib import Path

# Setup path to import app module
sys.path.insert(0, str(Path(__file__).parent))

from app.core.reports.report_generator import generate_pptx, generate_excel

async def test_hubs_reports():
    print("Testing Report Generation for HubSpot (HUBS)...")
    
    # 1. Load the data
    analysis_path = Path("hubs_financial_analysis.json")
    raw_data_path = Path("hubs_test_output.json")
    
    if not analysis_path.exists() or not raw_data_path.exists():
        print("Error: Required data files not found.")
        return
        
    with open(analysis_path, "r") as f:
        analyst_data = json.load(f)
    
    with open(raw_data_path, "r") as f:
        raw_data = json.load(f)
        
    # Mock deal object
    deal = {
        "id": "test-hubs-deal-001",
        "name": "HubSpot Strategic Analysis",
        "ticker": "HUBS",
        "sector": "SaaS / CRM",
        "deal_type": "Strategic Assessment",
        "stage": "deep_dive"
    }
    
    # Mock agent results (usually a list of AgentOutput dicts)
    agent_results = [
        {
            "agent_name": "financial_analyst",
            "success": True,
            "data": analyst_data,
            "reasoning": analyst_data.get("reasoning", "")
        }
    ]
    
    # 2. Generate PPTX
    print("Generating PPTX...")
    pptx_bytes = generate_pptx(
        deal=deal,
        analyst_data=analyst_data,
        agent_results=agent_results,
        deal_stage="deep_dive"
    )
    
    with open("hubs_strategic_report.pptx", "wb") as f:
        f.write(pptx_bytes)
    print("PPTX saved to hubs_strategic_report.pptx")
    
    # 3. Generate Excel
    print("Generating Excel...")
    excel_bytes = generate_excel(
        deal=deal,
        analyst_data=analyst_data,
        agent_results=agent_results,
        deal_stage="deep_dive"
    )
    
    with open("hubs_financial_model.xlsx", "wb") as f:
        f.write(excel_bytes)
    print("Excel saved to hubs_financial_model.xlsx")
    
    print("\nReport generation successful!")

if __name__ == "__main__":
    asyncio.run(test_hubs_reports())
