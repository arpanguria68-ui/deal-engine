import httpx
import json
import asyncio


async def check_live_routing():
    url = "http://localhost:8000/api/v1/models/routing"
    print(f"Fetching routing from: {url}")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                print("\n--- Live Routing Table ---")
                print(json.dumps(data.get("routing_table", {}), indent=2))

                print("\n--- Live Health Status ---")
                print(json.dumps(data.get("health", {}), indent=2))

                pageindex_health = data.get("health", {}).get("pageindex", {})
                print(f"\nPageIndex Status Summary:")
                print(f"- Assigned: {data.get('routing_table', {}).get('pageindex')}")
                print(f"- Healthy: {pageindex_health.get('is_healthy')}")
                print(f"- Fallback used: {pageindex_health.get('fallback')}")
            else:
                print(f"Error: HTTP {resp.status_code}")
    except Exception as e:
        print(f"Connection Error: {e}")


if __name__ == "__main__":
    asyncio.run(check_live_routing())
