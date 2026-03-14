import sys
import os
import json
from datetime import datetime

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "dealforge-ai/backend"))
)

from app.core.reports.report_generator import (
    generate_pdf,
    generate_html,
    generate_excel,
)


def run_tests():
    print("Running E2E Report Generation Tests...")

    deal = {
        "id": "test-deal-001",
        "name": "Project Sapphire",
        "target_company": "Acme Tech",
        "industry": "Software",
        "status": "completed",
        "created_at": datetime.utcnow().isoformat(),
        "final_score": 0.85,
        "final_recommendation": "Strong Buy",
    }

    analyst_data = {
        "executive_summary": {
            "situation": "Acme Tech is a leading SaaS provider.",
            "complication": "Facing increased competition.",
            "question": "Should we acquire them?",
            "answer": "Yes, to expand market share.",
        }
    }

    agent_results = [
        {
            "agent_type": "RiskAssessor",
            "confidence": 0.9,
            "reasoning": "# Risks\\n- Market Competition\\n- Regulatory changes",
            "provider": "openai",
        }
    ]

    print("Testing Excel generation...")
    try:
        excel_bytes = generate_excel(deal, analyst_data, agent_results)
        with open("test_output.xlsx", "wb") as f:
            f.write(excel_bytes)
        print("Excel saved to test_output.xlsx")
    except Exception as e:
        print(f"Error generating Excel: {e}")

    print("Testing PDF output using Reportlab...")
    try:
        pdf_bytes = generate_pdf(deal, analyst_data, agent_results)
        with open("test_output.pdf", "wb") as f:
            f.write(pdf_bytes)
        print("PDF saved to test_output.pdf")
    except Exception as e:
        print(f"Error generating PDF: {e}")

    print("Testing HTML output...")
    try:
        html_bytes = generate_html(deal, analyst_data, agent_results)
        with open("test_output.html", "wb") as f:
            f.write(html_bytes)
        print("HTML saved to test_output.html")
    except Exception as e:
        print(f"Error generating HTML: {e}")

    print("Tests completed.")


if __name__ == "__main__":
    run_tests()
