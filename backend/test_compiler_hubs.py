
import asyncio
import json
import sys
import base64
from pathlib import Path
from datetime import datetime

# Setup path to import app module
sys.path.insert(0, str(Path(__file__).parent))

from app.agents.compiler_agent import ReportCompilerAgent
from app.core.settings_service import SettingsService

# Initialize and apply settings from settings.json
svc = SettingsService.get_instance()
svc._apply_to_system()

async def test_compiler_hubs_package():
    print("🎬 Starting HubSpot (HUBS) Final Report Synthesis...")
    
    # 1. Load the pre-verified stress test data
    master_path = Path("hubs_master_stress_test.json")
    analyst_path = Path("hubs_financial_analysis.json")
    
    if not master_path.exists() or not analyst_path.exists():
        print("❌ Error: Required HubSpot data files not found. Run the stress test first.")
        return
        
    with open(master_path, "r") as f:
        master_data = json.load(f)
    with open(analyst_path, "r") as f:
        analyst_data = json.load(f)
        
    # 2. Mock full Deal State & Agent Results for the Compiler
    # This simulates what happens at the end of a real multi-agent pipeline
    deal_state = {
        "deal_id": "hubs-strat-2026",
        "deal_name": "Project HubSpot: Strategic SaaS Pivot",
        "target_company": "HubSpot, Inc.",
        "ticker": "HUBS",
        "industry": "Software / CRM",
        "final_score": 0.78,
        "agents_run": ["financial_analyst", "data_curator", "valuation_expert"],
        "consistency_warnings": [
            {"severity": "warning", "message": "High OpEx relative to peer median", "field": "Profitability"}
        ]
    }
    
    # We pass the master stress test data as part of the agent results
    agent_results = [
        {
            "agent_name": "financial_analyst",
            "success": True,
            "data": analyst_data,
            "reasoning": analyst_data.get("reasoning", "")
        },
        {
            "agent_name": "valuation_expert",
            "success": True,
            "data": master_data.get("football_field", {}),
            "reasoning": "Consolidated valuation across DCF, Comps, and Monte Carlo modules."
        },
        {
            "agent_name": "risk_assessor",
            "success": True,
            "data": master_data.get("monte_carlo", {}),
            "reasoning": "Monte Carlo simulations show 0% probability of 15% IRR at 30B entry."
        }
    ]
    
    # 3. Initialize Agent & Run
    compiler = ReportCompilerAgent()
    print("\n📦 Calling ReportCompilerAgent.run()... (This triggers LLM synthesis + Graphics Engines)")
    
    # Requesting all three major formats
    context = {
        "deal_state": deal_state,
        "agent_results": agent_results,
        "formats": ["pptx", "pdf", "excel"]
    }
    
    result = await compiler.run(
        task="Synthesize all HubSpot financial data and risk simulations into a final Investment Committee package including PPTX, PDF, and Excel model.",
        context=context
    )
    
    if result.success:
        print("\n✅ SUCCESS: Reports Compiled!")
        print(f"   Reasoning: {result.reasoning}")
        print(f"   Generated Formats: {result.data['generated_formats']}")
        
        # Log any tool errors if formats are missing
        if not result.data['generated_formats']:
            print("   ⚠️  Warning: No formats generated. Raw Data Trace:")
            print(json.dumps(result.data, indent=2))
        
        # 4. Save the generated files from base64
        files = result.data.get("files_base64", {})
        for ext, b64_data in files.items():
            filename = f"hubs_final_package.{ext}"
            with open(filename, "wb") as f:
                f.write(base64.b64decode(b64_data))
            print(f"   💾 Saved: {filename}")
    else:
        print(f"\n❌ FAILED: {result.reasoning}")

if __name__ == "__main__":
    asyncio.run(test_compiler_hubs_package())
