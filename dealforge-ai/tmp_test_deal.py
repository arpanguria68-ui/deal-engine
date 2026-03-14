import urllib.request
import json

URL = "http://localhost:8005/api/v1/deals"
payload = {
    "name": "KeyBank M&A Check",
    "target_company": "First Niagara",
    "description": "M&A Discussion \u2013 KeyBank\u2019s $4.1 Billion Acquisition of First Niagara",
    "industry": "finance",
    "context": {
        "user_prompt": "M&A Discussion \u2013 KeyBank\u2019s $4.1 Billion Acquisition of First Niagara"
    },
}

data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    URL, data=data, headers={"Content-Type": "application/json"}, method="POST"
)

try:
    print(f"Sending POST to {URL}...")
    with urllib.request.urlopen(req, timeout=10) as response:
        status = response.getcode()
        body = response.read().decode("utf-8")
        print(f"Status: {status}")
        print(f"Response: {json.dumps(json.loads(body), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
