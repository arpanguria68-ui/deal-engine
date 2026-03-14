import asyncio
import json
from app.core.tools.integration_tools import (
    RoadmapGeneratorTool,
    ChurnMonteCarloTool,
    SynergyTrackerTool,
)
from app.agents.integration_planner_agent import IntegrationPlannerAgent


def test_integration_tools():
    print("Testing Roadmap Generator Tool...")
    roadmap_tool = RoadmapGeneratorTool()
    res1 = roadmap_tool.execute(company_name="Acme Corp", complexity_level="High")
    print("Roadmap Result:", json.dumps(res1.data, indent=2))
    assert res1.data["target_company"] == "Acme Corp", "Failed company name mapping"
    assert (
        len(res1.data["milestone_roadmap"]) > 6
    ), "Failed to inject high complexity steps"

    print("\nTesting Churn Monte Carlo Tool...")
    churn_tool = ChurnMonteCarloTool()
    res2 = churn_tool.execute(base_count=1000, cultural_fit_score=30, iterations=1000)
    print("Churn Monte Carlo Result:", json.dumps(res2.data, indent=2))
    assert (
        res2.data["expected_annual_churn_rate"] > 0.20
    ), "Churn rate should be high for poor cultural fit"
    assert (
        res2.data["retained_count"] < 1000
    ), "Retained count should be less than base count"

    print("\nTesting Synergy Tracker Tool...")
    synergy_tool = SynergyTrackerTool()
    res3 = synergy_tool.execute(total_synergy_value=10_000_000, realization_months=12)
    print(
        "Synergy Tracker Result (Month 12):",
        json.dumps(res3.data["schedule"][-1], indent=2),
    )
    assert len(res3.data["schedule"]) == 12, "Should have 12 months"
    assert (
        res3.data["schedule"][-1]["cumulative_synergy"] == 10_000_000
    ), "Should hit cumulative target at month 12"


def test_agent_init():
    print("\nTesting Integration Planner Agent Initialization...")
    agent = IntegrationPlannerAgent()
    print("Agent initialized successfully.")
    print("Agent Name:", agent.name)
    assert agent.name == "integration_planner_agent", "Wrong name"


if __name__ == "__main__":
    test_integration_tools()
    test_agent_init()
    print("\nAll internal sanity tests passed!")
