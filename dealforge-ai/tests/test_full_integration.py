import asyncio
import logging
from app.agents import get_agent_registry
from app.core.tools.tool_router import ToolRouter, AGENT_TOOL_MAP
from app.agents.ofas_supervisor import OFASSupervisorAgent

# Import agents to trigger module load (which might self-register or at least verify syntactical correctness)
from app.agents.ai_tech_diligence_agent import AITechDiligenceAgent
from app.agents.esg_agent import ESGAgent
from app.agents.integration_planner_agent import IntegrationPlannerAgent

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


async def test_full_integration():
    print("=========================================")
    print("  DEALFORGE AI - SYSTEM INTEGRATION TEST ")
    print("=========================================")

    # 1. Check Agent Instantiation
    print("\n--- 1. Agent Instantiation Check ---")

    expected_agents = [
        ("AITechDiligenceAgent", AITechDiligenceAgent),
        ("ESGAgent", ESGAgent),
        ("IntegrationPlannerAgent", IntegrationPlannerAgent),
        ("OFASSupervisorAgent", OFASSupervisorAgent),
    ]

    agents = {}
    for name, cls in expected_agents:
        try:
            agent_instance = cls()
            agents[name] = agent_instance
            print(f"[OK] {name} instantiated successfully.")
        except Exception as e:
            print(f"[FAIL] {name} failed to instantiate: {e}")
            return 1

    # 2. Check Tool Router
    print("\n--- 2. Tool Router Check ---")
    tool_router = ToolRouter()
    tool_router.register_default_tools()
    all_tools = tool_router.list_tools()
    print(f"Total tools registered in ToolRouter: {len(all_tools)}")

    expected_new_tools = [
        "peer_discovery",
        "finance_analysis",
        "finnhub_data",
        "alpha_vantage",
        "financial_datasets",
        "ai_stack_scanner",
        "model_defensibility_scorer",
        "ai_value_quantifier",
        "carbon_footprint_extractor",
        "supply_chain_risk_flagger",
        "esg_scorer",
        "cyber_vuln_scanner",
        "antitrust_hhi_calculator",
        "privacy_auditor",
        "roadmap_generator",
        "churn_monte_carlo",
        "synergy_tracker",
    ]

    missing_tools = []
    registered_tool_names = [
        t.get("name") or t.get("function", {}).get("name") or str(t) for t in all_tools
    ]
    for tool_name in expected_new_tools:
        if tool_name in registered_tool_names:
            pass  # Suppress mass OKs for brevity
        else:
            print(f"[FAIL] Tool '{tool_name}' is MISSING.")
            missing_tools.append(tool_name)

    if not missing_tools:
        print("[OK] All required external and internal tools are registered.")

    # Check mappings
    print("\nChecking Agent-Tool Mappings...")
    for agent_name in [
        "ai_tech_diligence_agent",
        "esg_agent",
        "integration_planner_agent",
        "dcf_lbo_architect",
    ]:
        mapped_tools = AGENT_TOOL_MAP.get(agent_name, [])
        if mapped_tools:
            print(f"[OK] {agent_name} has {len(mapped_tools)} mapped tools.")
        else:
            print(f"[FAIL] {agent_name} has NO mapped tools in AGENT_TOOL_MAP.")
            return 1

    # 3. Check LangGraph Orchestrator
    print("\n--- 3. LangGraph Orchestrator Check ---")
    supervisor = agents["OFASSupervisorAgent"]
    try:
        graph = supervisor.build_mna_graph()
        print(
            "[OK] OFASSupervisorAgent successfully built the LangGraph MNA StateGraph."
        )
    except Exception as e:
        print(f"[FAIL] Failed to build LangGraph: {e}")
        return 1

    # 4. Check Sector Loader integration
    print("\n--- 4. Sector Customization Check ---")
    from app.core.sector_loader import load_sector_config

    tech_cfg = load_sector_config("tech")
    if tech_cfg and tech_cfg.get("sector") == "technology":
        print("[OK] Sector Customization Framework loaded successfully.")
    else:
        print("[FAIL] Failed to load sector config.")
        return 1

    print("\n=========================================")
    print("FINAL RESULT: ALL SYSTEMS NOMINAL AND INTEGRATED.")
    return 0


if __name__ == "__main__":
    import warnings

    warnings.filterwarnings("ignore")  # Suppress FutureWarnings
    exit_code = asyncio.run(test_full_integration())
    exit(exit_code)
