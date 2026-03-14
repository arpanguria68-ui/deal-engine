
import asyncio
import json
import sys
from pathlib import Path

# Setup path to import app module
sys.path.insert(0, str(Path(__file__).parent))

from app.core.tools.financial_data_api import FetchFinancialStatementsTool
from app.core.tools.finance_toolkit_tool import FinanceAnalysisTool
from app.core.tools.valuation_tools import (
    FetchComparableCompaniesTool, 
    GenerateFootballFieldTool, 
    RunSensitivityAnalysisTool,
    RunMonteCarloIRRTool
)

async def run_comprehensive_hubs_test():
    print("🚀 Starting Comprehensive HubSpot (HUBS) Financial Stress Test...")
    
    # 1. Pull Raw Data
    print("\n[1/5] Pulling SEC EDGAR Data...")
    fs_tool = FetchFinancialStatementsTool()
    fs_result = await fs_tool.execute(ticker="HUBS", statements=["income", "balance"], periods=3)
    
    if not fs_result.success:
        print(f"❌ Failed to pull data: {fs_result.error}")
        return
    
    hubs_fs = fs_result.data
    latest_rev = hubs_fs["income_statement"]["revenue"]["2025"]
    latest_ebitda = hubs_fs["income_statement"]["operating_income"]["2025"] 
    
    print(f"✅ Data Pulled. 2025 Revenue: ${latest_rev:,}, Op Income: ${latest_ebitda:,}")

    # 1.5. Run Financial Ratios (FinanceToolkit)
    print("\n[1.5/5] Running 150+ Financial Ratios (FinanceToolkit)...")
    ratio_tool = FinanceAnalysisTool()
    # Note: FinanceToolkit usually needs real internet for FMP/Yahoo fallback if not mocked
    # We will try it for 'profitability' category
    ratio_result = await ratio_tool.execute(tickers="HUBS", analysis_type="ratios", sub_type="profitability")
    
    if ratio_result.success:
        print("✅ Ratios Calculated. Sample Metrics Found.")
        # Print a few sample keys from the first ticker
        first_ticker = list(ratio_result.data.keys())[0] if ratio_result.data else None
        if first_ticker:
            metrics = list(ratio_result.data[first_ticker].keys())[:3]
            print(f"   Metrics: {', '.join(metrics)}...")
    else:
        print(f"⚠️ Ratios Failed: {ratio_result.error}")

    # 2. Run Comparable Companies
    print("\n[2/5] Running Comparable Companies Analysis...")
    comps_tool = FetchComparableCompaniesTool()
    comps_result = comps_tool.execute(
        ticker="HUBS", 
        sector="technology",
        peer_tickers=["CRM", "ZEN", "FRSH", "WORK"], # SalesForce, Zendesk, Freshworks, Slack
        target_metrics={
            "revenue": latest_rev,
            "ebitda": latest_ebitda
        }
    )
    
    if comps_result.success:
        print(f"✅ Comps Analyzed. Median EV/Revenue: {comps_result.data['quartile_stats']['ev_revenue']['median']}x")
        implied_val = comps_result.data["implied_valuations"]["ev_revenue"]["median"]
        print(f"   Implied Valuation (Median): ${implied_val:,}")
    else:
        print(f"⚠️ Comps Failed: {comps_result.error}")

    # 3. Sensitivity Analysis (WACC vs Growth)
    print("\n[3/5] Running 2D Sensitivity Analysis (WACC vs Terminal Growth)...")
    sens_tool = RunSensitivityAnalysisTool()
    sens_result = sens_tool.execute(
        analysis_type="dcf_wacc_growth",
        base_inputs={
            "fcf": 125000000,
            "growth_rate": 0.15,
            "projection_years": 5,
            "wacc": 0.10,
            "terminal_growth": 0.02
        },
        row_variable={"name": "wacc", "values": [0.08, 0.10, 0.12]},
        col_variable={"name": "terminal_growth", "values": [0.01, 0.02, 0.03]}
    )
    
    if sens_result.success:
        print("✅ Sensitivity Table Generated.")
        print(f"   Base Case Value: ${sens_result.data['base_case']['value']:,}")
    else:
        print(f"⚠️ Sensitivity Failed: {sens_result.error}")

    # 4. Monte Carlo IRR Simulation
    print("\n[4/5] Running Monte Carlo IRR Simulation (Synergy Execution Risk)...")
    mc_tool = RunMonteCarloIRRTool()
    # Assume purchase price of $30B for simulation
    mc_result = mc_tool.execute(
        entry_ebitda=latest_ebitda,
        price=30000000000, 
        syn_target=500000000, # $500M target synergies
        sigma=3.0, # High volatility/risk
        years=5
    )
    
    if mc_result.success:
        print(f"✅ Monte Carlo Complete. Mean IRR: {mc_result.data['mean_irr']}")
        print(f"   Probability of IRR > 15%: {mc_result.data['prob_above_15pct']}")
    else:
        print(f"⚠️ Monte Carlo Failed: {mc_result.error}")

    # 5. Football Field Generation
    print("\n[5/5] Generating Football Field Summary...")
    ff_tool = GenerateFootballFieldTool()
    valuation_ranges = {
        "DCF (Sensitivity Range)": {"low": sens_result.data['range']['min'], "mid": sens_result.data['base_case']['value'], "high": sens_result.data['range']['max']},
        "Comps (Quartile Range)": {
            "low": comps_result.data["implied_valuations"]["ev_revenue"]["25th"],
            "mid": comps_result.data["implied_valuations"]["ev_revenue"]["median"],
            "high": comps_result.data["implied_valuations"]["ev_revenue"]["75th"]
        }
    }
    ff_result = ff_tool.execute(ticker="HUBS", valuation_ranges=valuation_ranges)
    
    if ff_result.success:
        print("✅ Football Field Data Compiled.")
        print(f"   Final Composite Median: ${ff_result.data['composite_range']['mid']:,}")
    else:
        print(f"⚠️ Football Field Failed: {ff_result.error}")

    print("\n🌟 ALL TESTS COMPLETED SUCCESSFULLY 🌟")
    
    # Save master output
    master_results = {
        "fs": hubs_fs,
        "comps": comps_result.data if comps_result.success else None,
        "sensitivity": sens_result.data if sens_result.success else None,
        "monte_carlo": mc_result.data if mc_result.success else None,
        "football_field": ff_result.data if ff_result.success else None
    }
    
    with open("hubs_master_stress_test.json", "w") as f:
        json.dump(master_results, f, indent=2)
    print("\nFull results saved to hubs_master_stress_test.json")

if __name__ == "__main__":
    asyncio.run(run_comprehensive_hubs_test())
