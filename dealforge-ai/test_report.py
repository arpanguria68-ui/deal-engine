"""Quick test: create deal, run 1 agent, generate all 3 report formats"""

import requests, json, time, os

API = "http://localhost:8000"

print("=== REPORT & TOOL INTEGRATION TEST ===\n")

# 1. Health check
print("[1] Health check...")
r = requests.get(f"{API}/health", timeout=5)
print(f"  Status: {r.status_code}")

# 2. Create deal
print("\n[2] Creating Zapier deal...")
r = requests.post(
    f"{API}/api/v1/deals",
    json={
        "name": "Acquisition of Zapier",
        "target_company": "Zapier",
        "description": "Automation SaaS ~$50M ARR, 250 employees",
        "industry": "saas",
        "context": {},
    },
    timeout=10,
)
deal = r.json()
deal_id = deal["id"]
print(f"  Deal ID: {deal_id}")

# 3. Run 1 agent (financial)
print("\n[3] Running Financial Analyst...")
t0 = time.time()
r = requests.post(
    f"{API}/api/v1/agents/run",
    json={
        "agent_type": "financial_analyst",
        "task": "Financial analysis for Zapier, Automation SaaS ~$50M ARR",
        "context": {"deal_id": deal_id},
    },
    timeout=120,
)
elapsed = round(time.time() - t0, 1)

if r.status_code == 200:
    res = r.json()
    print(
        f"  SUCCESS ({elapsed}s) — confidence: {res.get('confidence')}, provider: {res.get('provider')}"
    )
    # Log activity with confidence
    requests.post(
        f"{API}/api/v1/agent-activity",
        json={
            "agent_type": "financial_analyst",
            "deal_id": deal_id,
            "summary": f"Completed ({elapsed}s)",
            "provider": res.get("provider", "gemini"),
            "confidence": res.get("confidence", 0.8),
            "reasoning": res.get("reasoning", "")[:300],
            "data": res.get("data", {}),
        },
        timeout=5,
    )
else:
    print(f"  FAILED: {r.status_code} {r.text[:200]}")

# 4. Generate reports
print("\n[4] Generating reports...")
for fmt in ["pdf", "pptx", "xlsx"]:
    r = requests.get(f"{API}/api/v1/deals/{deal_id}/report?format={fmt}", timeout=30)
    if r.status_code == 200:
        fname = f"test_report.{fmt}"
        with open(fname, "wb") as f:
            f.write(r.content)
        size_kb = round(len(r.content) / 1024, 1)
        print(f"  {fmt.upper()}: OK ({size_kb} KB) -> {fname}")
    else:
        print(f"  {fmt.upper()}: FAILED - {r.status_code} {r.text[:200]}")

# 5. Check dashboard metrics
print("\n[5] Dashboard metrics...")
r = requests.get(f"{API}/api/v1/dashboard/metrics", timeout=5)
m = r.json()
print(f"  Total deals: {m['total_deals']}")
print(f"  Agent activities: {len(m['agent_activity'])}")

# 6. Check tool routing for agents
print("\n[6] Checking tool schemas...")
r = requests.get(f"{API}/api/v1/models/routing", timeout=5)
routing = r.json()
print(f"  Strategy: {routing.get('strategy')}")

# Test listing of registered tools via a quick health check
print("\nDone! Check test_report.pdf, test_report.pptx, test_report.xlsx")
