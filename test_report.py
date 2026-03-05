import asyncio
import sys
import uuid
import re

# Add backend to path
sys.path.append("f:/code project/Kimi_Agent_DealForge AI PRD/dealforge-ai/backend")

from app.main import generate_deal_report, _deal_store


async def main():
    deal_id = "80fb01f5-cb56-47b9-a84b-9e00854921e5"
    _deal_store[deal_id] = {
        "id": deal_id,
        "name": "Test Deal",
        "target_company": "Test Company",
        "status": "completed",
    }
    try:
        response = await generate_deal_report(deal_id, "pdf")
        print("Status code:", response.status_code)
        print("Headers:", dict(response.headers))
    except Exception as e:
        print("Error:", e)


if __name__ == "__main__":
    asyncio.run(main())
