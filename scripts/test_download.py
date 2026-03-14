import requests
import json

base_url = "http://localhost:8000"

print("Fetching deals...")
try:
    res = requests.get(f"{base_url}/api/v1/deals")
    if res.status_code == 200:
        response_data = res.json()
        print("Response data keys/type:", type(response_data))

        deals = response_data
        if isinstance(response_data, dict) and "deals" in response_data:
            deals = response_data["deals"]

        print(f"Found {len(deals)} deals.")
        for d in deals:
            print(f"- {d.get('id')} : {d.get('target_company')}")

            if d.get("status") == "completed":
                print(f"  Attempting to download PDF for this deal...")
                report_url = f"{base_url}/api/v1/deals/{d.get('id')}/report?format=pdf"
                r = requests.get(report_url)
                print(f"  Status code: {r.status_code}")
                print(f"  Headers: {r.headers}")
                print(f"  Content length: {len(r.content)} bytes")
                if r.status_code != 200:
                    print(f"  Error body: {r.text[:500]}")
                else:
                    print(f"  Success content start: {r.content[:50]}")
                break
    else:
        print("Failed to fetch deals:", res.status_code, res.text)
except Exception as e:
    print("Error:", e)
