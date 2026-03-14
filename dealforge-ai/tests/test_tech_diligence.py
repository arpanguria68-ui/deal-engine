import asyncio
from app.core.tools.ai_tech_tools import (
    AIStackScannerTool,
    ModelDefensibilityScorerTool,
    AIValueQuantifierTool,
)
from app.agents.ai_tech_diligence_agent import AITechDiligenceAgent


def test_tech_tools():
    print("Testing AI Stack Scanner...")
    scanner = AIStackScannerTool()
    text = (
        "We use Llama 3 for RAG, pulling data from a Postgres database running on AWS."
    )
    res1 = scanner.execute(tech_summary_text=text)
    print("Scanner Result:", res1.data)
    assert "Llama" in res1.data["models_and_frameworks"], "Failed to detect Llama"
    assert "AWS" in res1.data["infrastructure"], "Failed to detect AWS"

    print("\nTesting Model Defensibility Scorer...")
    scorer = ModelDefensibilityScorerTool()
    res2 = scorer.execute(stack_metadata=res1.data)
    print("Scorer Result:", res2.data)
    assert res2.data["defensibility_score"] > 0, "Score should be calculated"

    print("\nTesting AI Value Quantifier...")
    quantifier = AIValueQuantifierTool()
    res3 = quantifier.execute(
        current_revenue=10000000, defensibility_score=res2.data["defensibility_score"]
    )
    print("Quantifier Result:", res3.data)
    assert res3.data["base_value_uplift"] > 0, "Uplift should be > 0"


def test_agent_init():
    print("\nTesting Agent Initialization...")
    agent = AITechDiligenceAgent()
    print("Agent initialized successfully.")
    print("Agent Name:", agent.name)
    assert agent.name == "ai_tech_diligence_agent", "Wrong name"


if __name__ == "__main__":
    test_tech_tools()
    test_agent_init()
    print("\nAll internal sanity tests passed!")
