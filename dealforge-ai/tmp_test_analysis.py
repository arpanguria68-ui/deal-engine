import urllib.request
import json

DEAL_ID = "5908d44b-062f-4f73-b49e-da470fda0a39"
PROMPT = (
    "M&A Discussion \u2013 KeyBank\u2019s $4.1 Billion Acquisition of First Niagara"
)


def trigger_step(url_suffix, payload):
    url = f"http://localhost:8005/api/v1/chat/{url_suffix}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    print(f"--- Triggering {url_suffix} ---")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = response.read().decode("utf-8")
            print(f"Status: {response.getcode()}")
            return json.loads(body)
    except Exception as e:
        print(f"Error in {url_suffix}: {e}")
        return None


# 1. Clarify
clarify_payload = {
    "prompt": PROMPT,
    "deal_id": DEAL_ID,
    "company_name": "First Niagara",
    "clarification_round": 0,
}
clarify_data = trigger_step("clarify", clarify_payload)
print(json.dumps(clarify_data, indent=2))

# 2. Plan
plan_payload = {
    "prompt": PROMPT,
    "deal_id": DEAL_ID,
    "company_name": "First Niagara",
    "user_answers": [],
    "focus_mode": "balanced",
    "sources": ["financial", "docs"],
}
plan_data = trigger_step("plan", plan_payload)
print(json.dumps(plan_data, indent=2))
