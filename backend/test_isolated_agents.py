import sys
import asyncio
from pathlib import Path

# Setup path so it can import the app module correctly
sys.path.insert(0, str(Path(__file__).parent))

from app.core.settings_service import SettingsService
from app.agents.data_curator_agent import DataCuratorAgent
from app.agents.financial_analyst import FinancialAnalystAgent
from app.agents.compiler_agent import ReportCompilerAgent
from app.core.tools.tool_router import ToolRouter, ReportGenerationTool

async def main():
    print("Initializing Isolated Agent Test...")
    
    # 1. Force override settings for local LM Studio testing
    # This ensures it doesn't use the web configuration or OpenAI accidentally
    print("Configuring LM Studio (qwen/qwen3.5-35b-a3b @ 127.0.0.1:1234)...")
    settings_service = SettingsService.get_instance()
    
    # We override all agent routing to use 'lmstudio' provider
    settings_service._settings["DEFAULT_LLM_PROVIDER"] = "lmstudio"
    
    agent_routing = settings_service._settings.get("agent_routing", {})
    # Set known agents explicitly and also loop through existing
    agent_routing["compiler_agent"] = "lmstudio"
    agent_routing["report_architect"] = "lmstudio"
    for agent_key in agent_routing.keys():
        agent_routing[agent_key] = "lmstudio"
    settings_service._settings["agent_routing"] = agent_routing
    
    # Explicitly set the local endpoint and model
    settings_service._settings["lmstudio_base_url"] = "http://127.0.0.1:1234/v1"
    settings_service._settings["lmstudio_model"] = "qwen/qwen3.5-35b-a3b"
    
    # 2. Test Data Curator (Uses general Web Search / MCP)
    # print("\n" + "="*60)
    # print("🕵️  Testing: Data Curator Agent (Web Search Capabilities)")
    # print("="*60)
    # ...
    
    # 3. Test Financial Analyst (Uses DuckDB / SEC EDGAR / Specific Financial Tools)
    # print("\n" + "="*60)
    # print("📈 Testing: Financial Analyst Agent (Financial/SEC Capabilities)")
    # print("="*60)
    # ...

    # 4. Test Report Compiler (Uses ReportGenerationTool / pptx / openpyxl / reportlab)
    print("\n" + "="*60)
    print("Testing: Report Compiler Agent (Final Deliverables)")
    print("="*60)
    
    try:
        compiler = ReportCompilerAgent()
        
        # Mock deal state and analyst data as it would be in a real pipeline
        mock_deal_state = {
            "deal_name": "Project Skyfall",
            "target_company": "Microsoft",
            "industry": "technology",
            "final_score": 0.85,
            "agents_run": ["financial_analyst", "market_researcher", "legal_advisor"],
            "ticker": "MSFT"
        }
        
        mock_analyst_data = {
            "executive_summary": {
                "situation": "Microsoft is considering a strategic acquisition.",
                "complication": "Market competition is increasing in the cloud sector.",
                "question": "Should Microsoft proceed with the acquisition of Target Co?",
                "answer": "Yes, the acquisition provides significant synergies."
            },
            "financial_synthesis": {
                "narrative": "The financial profile shows strong cash flow and margin expansion.",
                "key_metrics": {
                    "Revenue ($M)": 211000,
                    "EBITDA ($M)": 88000
                }
            },
            "key_takeaways": [
                {"title": "Strategic Fit", "description": "Perfect alignment with cloud strategy."},
                {"title": "Financial Upside", "description": "Highly accretive transaction."}
            ],
            "action_items": ["Proceed to LOI", "Finalize technical DD"],
            "reasoning": "Standard compilation of project skyfall."
        }
        
        # Mock context that replicates the full system state
        test_context = {
            "deal_id": "test-deal-123",
            "deal_state": mock_deal_state,
            "analyst_data": mock_analyst_data,
            "formats": ["pptx", "pdf", "excel"],
            "agent_results": [
                {"agent_type": "financial_analyst", "reasoning": "Financials are strong.", "confidence": 0.9},
                {"agent_type": "market_researcher", "reasoning": "Market position is dominant.", "confidence": 0.85},
            ]
        }
        
        print("-> Running Report Compiler to generate PPTX, PDF, and Excel...")
        result = await compiler.run(
            task="Compile the final investment memorandum and presentation deck for Project Skyfall in PPTX, PDF, and Excel formats.",
            context=test_context
        )
        
        print("\nResult Success:", result.success)
        if result.data:
            print("Generated Formats:", result.data.get("generated_formats"))
            if result.data.get("files_base64"):
                print("Reports generated successfully (Base64 data present)")
        
        # Check tool execution
        if result.tool_calls:
            print("\nTools Used:", [tc.get('name') for tc in result.tool_calls])
        else:
            print("No tools were called by the agent.")
            
    except Exception as e:
        print(f"Error testing ReportCompilerAgent: {e}")
        import traceback
        traceback.print_exc()

    # 5. Direct Tool Verification (Bypassing LLM)
    print("\n" + "="*60)
    print("Direct Tool Verification: ReportGenerationTool")
    print("="*60)
    
    try:
        tool = ReportGenerationTool()
        mock_deal_context = {"name": "Test Deal", "target_company": "Test Target"}
        mock_analyst_data = {
            "executive_summary": {"situation": "Direct test.", "answer": "Proceed."},
            "key_takeaways": [{"title": "Success", "description": "Tool works."}]
        }
        mock_agent_results = [{"agent_type": "tester", "reasoning": "Direct verification.", "confidence": 1.0}]
        
        for fmt in ["pptx", "pdf", "excel"]:
            print(f"-> Generating {fmt.upper()} directly...")
            res = await tool.execute(
                format=fmt,
                deal_context=mock_deal_context,
                analyst_data=mock_analyst_data,
                agent_results=mock_agent_results
            )
            print(f"   Success: {res.success}")
            if not res.success:
                print(f"   Error: {res.error}")
                
    except Exception as e:
        print(f"Error during direct tool verification: {e}")
        
    print("\nIsolated testing complete.")

if __name__ == "__main__":
    asyncio.run(main())
