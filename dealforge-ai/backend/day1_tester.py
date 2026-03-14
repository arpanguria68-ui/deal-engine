"""
Day 1 Testing Harness — DealForge AI
Executes real-world prompts, benchmarks LLM providers, and verifies tool integration.
"""

import asyncio
import json
import time
import os
from datetime import datetime
from typing import List, Dict, Any

import structlog
from app.core.llm.model_router import get_model_router
from app.agents.base import AgentOutput
from app.agents import (
    get_agent_registry,
    FinancialAnalystAgent,
    CommercialDueDiligenceAgent,
    ValuationAgent,
    MarketResearcherAgent,
)

logger = structlog.get_logger()


class Day1Tester:
    def __init__(self, prompt_file: str):
        self.prompt_file = prompt_file
        self.results = []
        self.registry = get_agent_registry()
        self._initialize_registry()

    def _initialize_registry(self):
        """Manually register agents for the test harness"""
        print("🔧 Initializing Agent Registry...")
        agents_to_register = [
            FinancialAnalystAgent(),
            CommercialDueDiligenceAgent(),
            ValuationAgent(),
            MarketResearcherAgent(),
        ]
        for agent in agents_to_register:
            self.registry.register(agent)
        print(f"✅ Registered {len(agents_to_register)} agents.")

    async def run_test(self, test_case: Dict[str, Any]):
        test_id = test_case["id"]
        agent_type = test_case["agent"]
        prompt = test_case["prompt"]

        print(f"\n🚀 Running Test: {test_case['name']} ({test_id})")
        print(f"   Agent: {agent_type}")
        print(f"   Prompt: {prompt[:100]}...")

        agent = self.registry.get(agent_type)
        if not agent:
            print(f"❌ Error: Agent {agent_type} not found in registry.")
            return

        start_time = time.time()
        try:
            # Execute agent
            result: AgentOutput = await agent.run(prompt, context={"test_mode": True})
            duration = time.time() - start_time

            status = "SUCCESS" if result.success else "FAILED"
            print(f"✅ Finished in {duration:.2f}s | Status: {status}")

            self.results.append(
                {
                    "test_item": test_case["name"],
                    "agent": agent_type,
                    "success": result.success,
                    "duration_s": round(duration, 2),
                    "confidence": result.confidence,
                    "reasoning": result.reasoning[:200] + "...",
                    "tool_calls": len(result.tool_calls) if result.tool_calls else 0,
                }
            )

        except Exception as e:
            duration = time.time() - start_time
            print(f"❌ Exception in {test_id}: {str(e)}")
            self.results.append(
                {
                    "test_item": test_case["name"],
                    "agent": agent_type,
                    "success": False,
                    "duration_s": round(duration, 2),
                    "error": str(e),
                }
            )

    async def run_all(self):
        with open(self.prompt_file, "r") as f:
            prompts = json.load(f)

        print(f"=== Starting Day 1 Testing ({len(prompts)} cases) ===")
        for i, p in enumerate(prompts):
            print(f"DEBUG: Processing case {i+1}: {p['id']}")
            try:
                await self.run_test(p)
            except Exception as e:
                print(f"DEBUG: Error in loop for {p['id']}: {e}")
            # Small delay between tests to avoid rapid hits
            await asyncio.sleep(2)

        self.save_results()

    def save_results(self):
        output_file = f"day1_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\n📊 Day 1 Results saved to {output_file}")

        # Print summary table
        print("\nSUMMARY:")
        print(f"{'Test Item':<30} | {'Status':<8} | {'Time':<6} | {'Conf':<5}")
        print("-" * 55)
        for r in self.results:
            status = "✅ OK" if r["success"] else "❌ FAIL"
            conf = r.get("confidence", 0.0)
            print(
                f"{r['test_item'][:30]:<30} | {status:<8} | {r['duration_s']:>5.1f}s | {conf:>4.2f}"
            )


if __name__ == "__main__":
    tester = Day1Tester(
        "f:/code project/Kimi_Agent_DealForge AI PRD/dealforge-ai/backend/tests/prompts_list.json"
    )
    asyncio.run(tester.run_all())
