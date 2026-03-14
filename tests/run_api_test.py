import requests
import time
import sys

HOST = "http://127.0.0.1:8000"


def run_test():
    print("=========================================")
    print("  DEALFORGE AI - END-TO-END DEMO TEST    ")
    print("=========================================")

    print("\n1. Pinging API Health...")
    try:
        health = requests.get(f"{HOST}/health")
        print(f"Status: {health.json()['status']}")
    except Exception as e:
        print(f"Cannot reach backend: {e}")
        sys.exit(1)

    print("\n2. Triggering OFAS Supervisor Pipeline via Agent Endpoint...")
    print("This will spin up LangGraph and dispatch parallel agents.")
    print("Please wait (could take 30-90s depending on the mock responses/LLMs)...")

    start_t = time.time()
    payload = {
        "agent_type": "ofas_supervisor",
        "task": "Perform a full M&A diligence pipeline check on Project Nebula.",
        "context": {"target_company": "Nebula AI Corp", "industry": "technology"},
    }

    res_run = requests.post(f"{HOST}/api/v1/agents/run", json=payload, timeout=120)

    if res_run.status_code != 200:
        print(f"[ERROR] Pipeline execution failed: {res_run.text}")
        sys.exit(1)

    result = res_run.json()
    elapsed = time.time() - start_t

    print("\n=========================================")
    print(f"  PIPELINE COMPLETION [{elapsed:.1f}s]")
    print("=========================================")
    print(f"Success: {result.get('success', False)}")
    print(f"Reasoning: {result.get('reasoning', '')}")
    if isinstance(result.get("data"), dict):
        print(f"Final Output State Keys: {list(result['data'].keys())}")

    print("\n[OK] End-to-End Test Passed!")


if __name__ == "__main__":
    run_test()
