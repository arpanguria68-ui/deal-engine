import requests
import time
import sys
import os
import json

# Target the Docker container's mapped port
HOST = "http://127.0.0.1:8005"


def run_real_transaction():
    print("=========================================")
    print("  DEALFORGE AI - REAL DEAL PIPELINE TEST ")
    print("=========================================")

    print("\n1. Creating Real Deal in Dockerized Backend...")
    deal_payload = {
        "name": "Project Sapphire - Real World Test",
        "target_company": "Palantir Technologies",
        "industry": "Enterprise Software / AI",
        "context": {
            "sector": "technology",
            "revenue": "$2.2B",
            "ebitda_margin": "18%",
            "employee_count": 3800,
            "tech_stack": "Gotham, Foundry, Apollo",
            "strategic_rationale": "Test fully autonomous AI/Enterprise SaaS valuation using live API ingestion and LangGraph refactor.",
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

    print("\n2. Triggering OFAS Pipeline (This may take several minutes)...")
    start_t = time.time()
    try:
        # Long timeout to allow native tool invocation and deep RL analysis
        res_run = requests.post(f"{HOST}/api/v1/deals/{deal_id}/run", timeout=900)
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

    print("\nStage History:")
    for stage in result.get("stage_history", []):
        print(f" - {stage}")

    print("\n3. Verifying Report Compilation Deliverables...")
    for fmt in ["pdf", "pptx"]:
        try:
            print(f"Requesting {fmt.upper()} report...")
            res_rep = requests.get(
                f"{HOST}/api/v1/deals/{deal_id}/report?format={fmt}", timeout=60
            )
            res_rep.raise_for_status()
            print(f"[OK] {fmt.upper()} report received from Docker.")

            # Save the report locally for user verification
            filename = f"Project_Sapphire_Report.{fmt}"
            with open(filename, "wb") as f:
                f.write(res_rep.content)
            print(f"   -> Saved to ./{filename}")

        except requests.exceptions.HTTPError as e:
            if res_rep.status_code == 404:
                print(
                    f"[WARNING] 404 Not Found: {fmt} report may not have been compiler generated."
                )
            else:
                print(f"[WARNING] Failed to fetch {fmt} report: {e}")
        except Exception as e:
            print(f"[WARNING] Failed to fetch {fmt} report: {e}")

    print("\n4. Executing Task Persistence Check...")
    try:
        res_tasks = requests.get(f"{HOST}/api/v1/deals/{deal_id}/tasks")
        res_tasks.raise_for_status()
        tasks = res_tasks.json().get("todo_lists", [])
        if tasks:
            print(f"[OK] Found {len(tasks)} persisted Scrum/Kanban task lists.")
            print(f"     Task List Examples:")
            for t in tasks[:2]:
                print(
                    f"      - {t.get('title', 'Unknown')} ({len(t.get('tasks', []))} tracking items)"
                )
        else:
            print(
                "[INFO] No task lists found. This is normal if the pipeline didn't loop back via Red Team."
            )
    except Exception as e:
        print(f"[WARNING] Task persistence check failed: {e}")

    print("\n[SUCCESS] Custom Real Deal Pipeline Test Concluded!")


if __name__ == "__main__":
    run_real_transaction()
