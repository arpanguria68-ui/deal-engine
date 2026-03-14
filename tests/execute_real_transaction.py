import requests
import time
import sys
import os

HOST = "http://127.0.0.1:8000"


def run_transaction():
    print("=========================================")
    print("  DEALFORGE AI - REAL TRANSACTION EXECUTION ")
    print("=========================================")

    print("\n1. Creating high-profile M&A Deal...")
    deal_payload = {
        "name": "Project CyberShield - SentinelOne Acquisition",
        "target_company": "SentinelOne",
        "industry": "technology",
        "context": {
            "sector": "technology",
            "revenue_run_rate": "$600M",
            "ebitda_margin": "-10%",
            "employee_count": 2000,
            "tech_stack": "AWS, Python, Go, Kubernetes, ML models for threat detection",
            "regulatory_concerns": "GDPR data storage in EU, high HHI in endpoint security market",
            "esg_notes": "Scope 1 emissions low, Scope 3 supply chain includes Taiwanese hardware manufacturing",
            "strategic_rationale": "Expand endpoint security capabilities and acquire AI-driven threat hunting models.",
        },
    }

    try:
        res = requests.post(f"{HOST}/api/v1/deals", json=deal_payload)
        res.raise_for_status()
    except Exception as e:
        print(f"Failed to create deal: {e}")
        if "res" in locals():
            print(res.text)
        sys.exit(1)

    deal_data = res.json()
    deal_id = deal_data["id"]
    print(f"[OK] Deal created: {deal_data['name']} (ID: {deal_id})")

    print("\n2. Triggering Full OFAS Pipeline (LangGraph)...")
    print(
        "Dispatching parallel agents (Financial, Legal, Risk, Market, Tech, ESG, etc)..."
    )
    print("This will take a few minutes as local LLMs process the context.")

    start_t = time.time()
    try:
        # Increase timeout drastically for local LLMs
        res_run = requests.post(f"{HOST}/api/v1/deals/{deal_id}/run", timeout=600)
        res_run.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Pipeline execution failed: {e}")
        if "res_run" in locals():
            print(res_run.text)
        sys.exit(1)

    result = res_run.json()
    elapsed = time.time() - start_t

    print("\n=========================================")
    print(f"  PIPELINE COMPLETION [{elapsed:.1f}s]")
    print("=========================================")
    print(f"Status: {result.get('status', 'unknown').upper()}")
    print(f"Final Score: {result.get('final_score')}")
    print(f"Final Recommendation: {result.get('final_recommendation')}")
    print("Stage History:")
    for stage in result.get("stage_history", []):
        print(f" - {stage}")

    print("\n3. Generating Final McKinsey-Style Report...")
    artifacts_dir = os.path.join(
        os.path.expanduser("~"),
        ".gemini",
        "antigravity",
        "brain",
        os.environ.get("CONVERSATION_ID", ""),
    )
    if not os.path.exists(artifacts_dir):
        # Fallback if executing outside the standard runner
        artifacts_dir = "."

    for fmt in ["pdf", "pptx"]:
        try:
            print(f"Requesting {fmt.upper()} report...")
            res_rep = requests.get(
                f"{HOST}/api/v1/deals/{deal_id}/report?format={fmt}", timeout=60
            )
            res_rep.raise_for_status()

            output_path = os.path.join(
                artifacts_dir, f"Project_CyberShield_Report.{fmt}"
            )
            with open(output_path, "wb") as f:
                f.write(res_rep.content)
            print(f"[OK] Saved {fmt.upper()} report to {output_path}")
        except Exception as e:
            print(f"[WARNING] Failed to generate {fmt} report: {e}")

    print("\n[OK] Transaction Executed Successfully!")


if __name__ == "__main__":
    run_transaction()
