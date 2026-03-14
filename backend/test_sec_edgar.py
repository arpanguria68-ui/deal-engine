import requests
import json

SEC_HEADERS = {
    "User-Agent": "DealForge-OFAS/1.0 (contact@dealforge.ai)",
    "Accept": "application/json",
}


def test_sec_urls():
    urls = [
        "https://www.sec.gov/files/company_tickers.json",
        "https://data.sec.gov/submissions/company_tickers.json",
        "https://data.sec.gov/files/company_tickers.json",
    ]

    for url in urls:
        print(f"Testing {url}...")
        try:
            resp = requests.get(url, headers=SEC_HEADERS, timeout=10)
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                # Print first entry
                first_key = list(data.keys())[0]
                print(f"  Success! First entry: {data[first_key]}")
                return url, data
        except Exception as e:
            print(f"  Error: {e}")
    return None, None


def test_msft_facts(cik):
    facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"
    print(f"\nFetching facts for MSFT (CIK {cik}) from {facts_url}...")
    try:
        resp = requests.get(facts_url, headers=SEC_HEADERS, timeout=30)
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            facts = resp.json()
            print(f"  Success! Entity: {facts.get('entityName')}")
            # Check for us-gaap facts
            us_gaap = facts.get("facts", {}).get("us-gaap", {})
            print(f"  Found {len(us_gaap)} us-gaap fields.")

            # Look for Revenues
            rev_field = us_gaap.get("Revenues")
            if rev_field:
                units = rev_field.get("units", {}).get("USD", [])
                if units:
                    latest = units[-1]
                    print(
                        f"  Latest Revenue: {latest['val']} (End: {latest['end']}, Form: {latest['form']})"
                    )
                else:
                    print("  No USD units for Revenues.")
            else:
                # Try another common revenue field
                rev_field = us_gaap.get(
                    "RevenueFromContractWithCustomerExcludingAssessedTax"
                )
                if rev_field:
                    units = rev_field.get("units", {}).get("USD", [])
                    if units:
                        latest = units[-1]
                        print(
                            f"  Latest Revenue (Contract): {latest['val']} (End: {latest['end']}, Form: {latest['form']})"
                        )

            return facts
    except Exception as e:
        print(f"  Error: {e}")
    return None


if __name__ == "__main__":
    current_url, tickers = test_sec_urls()
    if tickers:
        msft_cik = None
        for _, entry in tickers.items():
            if entry.get("ticker") == "MSFT":
                msft_cik = str(entry["cik_str"])
                break

        if msft_cik:
            test_msft_facts(msft_cik)
        else:
            print("MSFT not found in ticker list.")
