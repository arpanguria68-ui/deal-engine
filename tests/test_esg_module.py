import asyncio
from app.core.tools.esg_tools import (
    CarbonFootprintExtractorTool,
    SupplyChainRiskFlaggerTool,
    ESGScorerTool,
)
from app.agents.esg_agent import ESGAgent


def test_esg_tools():
    print("Testing Carbon Footprint Extractor...")
    extractor = CarbonFootprintExtractorTool()
    text = "We emitted 50,000 tons of Scope 1 CO2 last year. We also had scope 2 emissions of 1500."
    res1 = extractor.execute(sustainability_text=text)
    print("Extractor Result:", res1.data)
    assert res1.data.get("scope1_tco2e", 0) > 0, "Failed to extract scope 1"
    assert res1.data.get("total_tco2e", 0) > 0, "Total calculation failed"

    print("\nTesting Supply Chain Risk Flagger...")
    flagger = SupplyChainRiskFlaggerTool()
    supplier_text = "We use overseas manufacturers with no audited labor policies. There is some forced labor concern."
    res2 = flagger.execute(supplier_text=supplier_text)
    print("Flagger Result:", res2.data)
    assert (
        "Critical" in res2.data["supply_chain_risk_severity"]
    ), "Failed to flag critical severity"

    print("\nTesting ESG Scorer...")
    scorer = ESGScorerTool()
    res3 = scorer.execute(
        total_emissions=res1.data["total_tco2e"],
        supply_chain_severity=res2.data["supply_chain_risk_severity"],
    )
    print("Scorer Result:", res3.data)
    assert res3.data["composite_esg_score"] > 0, "Score calculation failed"
    print("Simulated MSCI Rating:", res3.data["simulated_msci_rating"])


def test_esg_agent_init():
    print("\nTesting ESG Agent Initialization...")
    agent = ESGAgent()
    print("Agent initialized successfully.")
    print("Agent Name:", agent.name)
    assert agent.name == "esg_agent", "Wrong agent name"


if __name__ == "__main__":
    test_esg_tools()
    test_esg_agent_init()
    print("\nAll internal sanity tests passed!")
