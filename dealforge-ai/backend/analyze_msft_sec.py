import requests
import json

SEC_HEADERS = {
    "User-Agent": "DealForge-OFAS/1.0 (contact@dealforge.ai)",
    "Accept": "application/json",
}


def analyze_msft_recent_facts(cik):
    facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
    print(f"Fetching facts for MSFT (CIK {cik})...")
    try:
        resp = requests.get(facts_url, headers=SEC_HEADERS, timeout=30)
        if resp.status_code == 200:
            facts = resp.json()
            us_gaap = facts.get("facts", {}).get("us-gaap", {})

            # Common revenue fields to check
            revenue_fields = [
                "Revenues",
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "SalesRevenueNet",
            ]

            for field in revenue_fields:
                data = us_gaap.get(field)
                if data:
                    print(f"\nAnalyzing field: {field}")
                    units = data.get("units", {}).get("USD", [])
                    # Filter for 10-K and sort by end date
                    ten_ks = [e for e in units if e.get("form") == "10-K"]
                    ten_ks.sort(key=lambda x: x.get("end"), reverse=True)

                    print(f"  Found {len(ten_ks)} 10-K entries.")
                    for e in ten_ks[:3]:
                        print(
                            f"    Year end: {e['end']}, Value: ${e['val']/1e9:.2f}B, filed: {e.get('filed')}"
                        )
    except Exception as e:
        print(f"  Error: {e}")


if __name__ == "__main__":
    analyze_msft_recent_facts("789019")
