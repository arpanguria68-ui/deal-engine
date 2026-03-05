import httpx
import json
import asyncio


async def test_search():
    url = "http://localhost:8000/api/v1/documents/query"
    queries = [
        "What is the role of Investment Banks in LBOs?",
        "purchase price disputes",
        "Valuation",
        "bulk ingestion",
        "test",
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for query in queries:
            payload = {"query": query, "deal_id": None}
            print(f"\n--- Testing Query: '{query}' ---")
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    if not results:
                        print("No results found.")
                    else:
                        print(f"Found {len(results)} results.")
                        for i, res in enumerate(results[:2]):
                            print(
                                f"  [{i+1}] Relevance: {res.get('relevance')} | Content snippet: {res.get('content', '')[:100]}..."
                            )
                else:
                    print(f"Error: {resp.status_code}")
            except Exception as e:
                print(f"Connection Error for '{query}': {e}")


if __name__ == "__main__":
    asyncio.run(test_search())
