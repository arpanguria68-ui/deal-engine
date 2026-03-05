import requests
import json
import sys

base_url = "http://localhost:8000/api/v1"

print("--- 1. Routing check ---")
try:
    r = requests.get(f"{base_url}/models/routing")
    print("Status:", r.status_code)
    print(json.dumps(r.json(), indent=2))
except Exception as e:
    print("Routing error:", e)

print("\n--- 2. Agent run (legal_advisor = Mistral) ---")
try:
    data = {
        "agent_type": "legal_advisor",
        "task": "Review TechFlow Corp acquisition for red flags",
        "context": {"deal_id": "test_deal_123"},
    }
    r = requests.post(f"{base_url}/agents/run", json=data)
    print("Status:", r.status_code)
    if r.status_code == 200:
        print(json.dumps(r.json(), indent=2))
    else:
        print(r.text)
except Exception as e:
    print("Agent run error:", e)

print("\n--- 3. Agent run (financial_analyst = Gemini) ---")
try:
    data = {
        "agent_type": "financial_analyst",
        "task": "Analyze financials for TechFlow Corp",
        "context": {"deal_id": "test_deal_123"},
    }
    r = requests.post(f"{base_url}/agents/run", json=data)
    print("Status:", r.status_code)
    if r.status_code == 200:
        print(json.dumps(r.json(), indent=2))
    else:
        print(r.text)
except Exception as e:
    print("Agent run error:", e)
