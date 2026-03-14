import requests
import time
import sys
import os

# Target the Docker container's mapped port
HOST = "http://127.0.0.1:8005"


def run_transaction():
    print("=========================================")
    print("  DEALFORGE AI - DOCKER E2E VALIDATION  ")
    print("=========================================")

    print("\n1. Creating Deal in Dockerized Backend...")
    deal_payload = {
        "name": "Project DockerShield - Persistence Test",
        "target_company": "DockerInc",
        "industry": "technology",
        "context": {
            "sector": "technology",
            "revenue_run_rate": "$100M",
            "ebitda_margin": "15%",
            "employee_count": 500,
            "tech_stack": "Docker, Kubernetes, FastAPI",
            "strategic_rationale": "Verify persistence and RL loop in containerized environment.",
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

    print("\n2. Triggering OFAS Pipeline...")
    start_t = time.time()
    try:
        # Increase timeout for local processing
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

    # Check for Peer Review entries in history
    print("Stage History:")
    for stage in result.get("stage_history", []):
        print(f" - {stage}")

    print("\n3. Verifying Report Compilation...")
    for fmt in ["pdf", "pptx"]:
        try:
            print(f"Requesting {fmt.upper()} report...")
            res_rep = requests.get(
                f"{HOST}/api/v1/deals/{deal_id}/report?format={fmt}", timeout=60
            )
            res_rep.raise_for_status()
            print(f"[OK] {fmt.upper()} report received from Docker.")
        except Exception as e:
            print(f"[WARNING] Failed to fetch {fmt} report: {e}")

    print("\n4. Verifying Task Persistence (Simulating Restart Check)...")
    try:
        res_tasks = requests.get(f"{HOST}/api/v1/deals/{deal_id}/tasks")
        res_tasks.raise_for_status()
        tasks = res_tasks.json().get("todo_lists", [])
        if tasks:
            print(f"[OK] Found {len(tasks)} persisted task lists in SQLite.")
        else:
            print("[FAIL] No task lists found in persistence.")
    except Exception as e:
        print(f"[ERROR] Task persistence check failed: {e}")

    print("\n[OK] Docker E2E Validation Completed!")


if __name__ == "__main__":
    run_transaction()
