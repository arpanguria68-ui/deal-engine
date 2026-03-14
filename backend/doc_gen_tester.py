import asyncio
import os
import json
from pathlib import Path
from datetime import datetime
import structlog

from app.core.tools.reporting_tools import GenerateICMemoTool, GenerateDealDeckTool
from app.core.tools.excel_model_engine import ExcelModelPopulateTool

# Setup logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()

OUTPUT_DIR = Path("ofas_outputs")


async def test_pdf_generation():
    print("\n📄 Testing PDF Generation (IC Memo)...")
    tool = GenerateICMemoTool()
    result = tool.execute(
        ticker="MSFT",
        deal_name="Project Azure Sky",
        sections={
            "executive_summary": "Microsoft is considering a strategic acquisition of a specialized AI cloud provider to bolster its cognitive services at the edge.",
            "investment_thesis": "Vertical integration of edge AI hardware and software will provide a 30% margin improvement in the mid-market segment.",
            "risks": "Regulatory scrutiny on hyperscaler market share remains the primary hurdle.",
        },
        exhibits=[
            {"title": "Revenue Projections", "data": {"2025": "1.2B", "2026": "1.5B"}}
        ],
    )

    if result.success:
        print(f"✅ PDF Generated: {result.data['memo_path']}")
        return result.data["memo_path"]
    else:
        print(f"❌ PDF Failed: {result.error}")
        return None


async def test_pptx_generation():
    print("\n📊 Testing PPTX Generation (Deal Deck)...")
    tool = GenerateDealDeckTool()
    # Mock data structure expected by generate_pptx
    deal_data = {
        "name": "Project Azure Sky",
        "target_company": "EdgeAI Corp",
        "industry": "cloud_computing",
        "final_score": 0.85,
    }
    analyst_data = {
        "executive_summary": {
            "situation": "Market shifting to edge AI.",
            "complication": "Existing solutions are high latency.",
            "question": "Can Microsoft acquire EdgeAI to lead this shift?",
            "answer": "Yes, high synergy potential.",
        },
        "key_takeaways": [
            {
                "title": "Strategic Fit",
                "description": "Highly complementary tech stack.",
            }
        ],
    }

    result = tool.execute(
        ticker="MSFT",
        deal_name="Project Azure Sky",
        deal_data=deal_data,
        analyst_data=analyst_data,
    )

    if result.success:
        print(f"✅ PPTX Generated: {result.data['deck_path']}")
        return result.data["deck_path"]
    else:
        print(f"❌ PPTX Failed: {result.error}")
        return None


async def test_excel_generation():
    print("\n📉 Testing Excel Generation (Financial Model)...")
    tool = ExcelModelPopulateTool()
    # Use 'dcf' template as it's common
    result = tool.execute(
        template_id="dcf",
        ticker="MSFT",
        cell_mappings={
            "DCF": {
                "C5": 1500000000,  # Initial Revenue
                "C6": 0.25,  # Growth Rate
                "C7": 0.40,  # EBITDA Margin
            }
        },
    )

    if result.success:
        print(f"✅ Excel Generated: {result.data['model_path']}")
        return result.data["model_path"]
    else:
        print(f"❌ Excel Failed: {result.error}")
        # If openpyxl missing or template missing, report it
        return None


async def main():
    print("🚀 Starting Document Generation Verification...")

    pdf_path = await test_pdf_generation()
    pptx_path = await test_pptx_generation()
    excel_path = await test_excel_generation()

    print("\n🔍 Verification Summary:")
    print(f"  PDF: {'✅' if pdf_path else '❌'}")
    print(f"  PPTX: {'✅' if pptx_path else '❌'}")
    print(f"  Excel: {'✅' if excel_path else '❌'}")

    if all([pdf_path, pptx_path, excel_path]):
        print("\n🏆 ALL DOCUMENT GENERATION STAGES VERIFIED!")
    else:
        print("\n⚠️ SOME STAGES FAILED. Check logs for details.")


if __name__ == "__main__":
    asyncio.run(main())
