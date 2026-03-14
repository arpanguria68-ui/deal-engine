import os
import asyncio
import logging

# Set environment variables for testing OR set them before imports
os.environ["NVIDIA_API_KEY"] = os.environ.get("NVIDIA_API_KEY", "your_nvidia_api_key_here")
os.environ["NVIDIA_MODEL"] = os.environ.get("NVIDIA_MODEL", "z-ai/glm5")
os.environ["DEFAULT_LLM_PROVIDER"] = os.environ.get("DEFAULT_LLM_PROVIDER", "nvidia")

from app.agents import get_agent_registry
# from app.core.tools.tool_router import tool_router  # Removed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_live_agent_tests():
    print("=========================================")
    print("  DEALFORGE AI - LIVE LLM AGENT TESTS    ")
    print("=========================================")

    registry = get_agent_registry()

    # We will test 3 distinct new agents to verify their tool routing and LLM reasoning
    test_cases = [
        {
            "agent": "ai_tech_diligence_agent",
            "task": "Extract the AI stack and defensibility for an AI company that uses OpenAI GPT-4, Pinecone vector DB, and LangChain on AWS. Assume they have $5M in revenue.",
        },
        {
            "agent": "esg_agent",
            "task": "Extract carbon footprint for a target that has 500 tons Scope 1, 1200 tons Scope 2, and 4500 tons Scope 3. Also check for supply chain flags if they manufacture in Xinjiang.",
        },
        {
            "agent": "dcf_lbo_architect",
            "task": "What is the valuation impact if we add an Ornstein-Uhlenbeck synergy fade target of $10M with kappa=0.5?",
        },
    ]

    for case in test_cases:
        agent_name = case["agent"]
        task_prompt = case["task"]

        agent = registry.get(agent_name)
        if not agent:
            print(f"\n[ERROR] Agent {agent_name} not found in registry. Skipping.")
            continue

        print(f"\n>> Testing Agent: {agent_name.upper()}")
        print(f"Task: {task_prompt}")
        print("Executing (this may take 10-30 seconds depending on local LLM)...")

        try:
            # We use a mocked out tool_router just for testing or rely on the agent's internal router
            result = await agent.run(task_prompt, context={"test_mode": True})

            print(f"Success: {result.success}")
            print(f"Reasoning: {result.reasoning}")
            print(f"Confidence: {result.confidence}")
            print(
                f"Output Data: {result.data.keys() if isinstance(result.data, dict) else result.data}"
            )

        except Exception as e:
            print(f"[ERROR] Failed during execution: {e}")


if __name__ == "__main__":
    asyncio.run(run_live_agent_tests())
