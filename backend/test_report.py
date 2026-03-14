import asyncio
import json
import httpx
from fpdf import FPDF
import io


async def test_report():
    print("Testing report generation")
    # We will trigger the backend download endpoint to see if it generates successfully
    # Wait, we need an actual deal_id. Let's find one by calling the API...

    async with httpx.AsyncClient() as client:
        # Get deals
        resp = await client.get("http://127.0.0.1:8000/api/v1/deals")
        deals = resp.json().get("deals", [])
        if not deals:
            print("No deals found!")
            return

        deal_id = deals[0]["id"]
        print(f"Testing with deal: {deal_id}")

        # Test PPTX
        url = f"http://127.0.0.1:8000/api/v1/deals/{deal_id}/report?format=pptx"
        resp = await client.get(url, timeout=60.0)
        print(f"PPTX Status: {resp.status_code}")
        if resp.status_code == 200:
            with open("test.pptx", "wb") as f:
                f.write(resp.content)
            print("Successfully wrote test.pptx")
        else:
            print("PPTX Error:", resp.text)

        # Test Excel
        url = f"http://127.0.0.1:8000/api/v1/deals/{deal_id}/report?format=xlsx"
        resp = await client.get(url, timeout=60.0)
        print(f"XLSX Status: {resp.status_code}")
        if resp.status_code == 200:
            with open("test.xlsx", "wb") as f:
                f.write(resp.content)
            print("Successfully wrote test.xlsx")
        else:
            print("XLSX Error:", resp.text)


if __name__ == "__main__":
    asyncio.run(test_report())
