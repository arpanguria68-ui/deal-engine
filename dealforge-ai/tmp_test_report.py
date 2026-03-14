import urllib.request
import json
import time

DEAL_ID = "5908d44b-062f-4f73-b49e-da470fda0a39"
TASK_ID = "0f9edf1a"  # Comparable Companies Analysis


def trigger_post(url_suffix, payload):
    url = f"http://localhost:8005/api/v1/{url_suffix}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    print(f"--- Triggering {url_suffix} ---")
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            body = response.read().decode("utf-8")
            print(f"Status: {response.getcode()}")
            return json.loads(body)
    except Exception as e:
        print(f"Error in {url_suffix}: {e}")
        return None


# 1. Execute Task
execute_payload = {
    "agent_type": "valuation_agent",
    "task": "Identify peer companies for First Niagara and calculate trading multiples.",
    "deal_id": DEAL_ID,
    "task_id": TASK_ID,
    "title": "Comparable Companies Analysis",
    "sources": ["financial"],
}
task_result = trigger_post("chat/execute-task", execute_payload)
print(json.dumps(task_result, indent=2))

# 2. Generate Report
# Report generation is a GET that triggers a byte stream
print("--- Triggering Report Generation (PDF) ---")
report_url = f"http://localhost:8005/api/v1/deals/{DEAL_ID}/report?format=pdf"
try:
    with urllib.request.urlopen(report_url, timeout=120) as response:
        print(f"Status: {response.getcode()}")
        content_type = response.headers.get("Content-Type")
        content_length = response.headers.get("Content-Length")
        print(f"Content-Type: {content_type}")
        print(f"Content-Length: {content_length}")
        # Read a bit to verify it works
        data = response.read()
        print(f"Successfully received {len(data)} bytes of PDF data.")
except Exception as e:
    print(f"Error in report generation: {e}")
