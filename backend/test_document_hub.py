
import requests
import time
import sys

BASE_URL = "http://localhost:8005/api/v1"

def test_document_hub(deal_id):
    print(f"--- Testing Document Hub for Deal: {deal_id} ---")

    # 1. List Documents (Initial)
    print("\n[1] Listing documents (expecting empty or existing)...")
    resp = requests.get(f"{BASE_URL}/deals/{deal_id}/documents")
    if resp.status_code != 200:
        print(f"Error listing documents: {resp.status_code} {resp.text}")
        return
    data = resp.json()
    print(f"Manifest: {len(data.get('documents', []))} docs found.")

    # 2. Generate Documents
    print("\n[2] Triggering document generation...")
    start_time = time.time()
    resp = requests.post(f"{BASE_URL}/deals/{deal_id}/documents/generate")
    if resp.status_code != 200:
        print(f"Error generating documents: {resp.status_code} {resp.text}")
        # If it fails, maybe the deal doesn't have activity. We need a live deal.
        return
    data = resp.json()
    duration = time.time() - start_time
    print(f"Generation took {duration:.2f}s. Formats: {data.get('formats_generated')}")

    # 3. List Documents (Post-generation)
    print("\n[3] Checking manifest post-generation...")
    resp = requests.get(f"{BASE_URL}/deals/{deal_id}/documents")
    data = resp.json()
    docs = data.get('documents', [])
    for d in docs:
        print(f" - {d['format'].upper()}: {d['size_human']} (Generated {d['generated_at']})")

    # 4. Binary Download (Instant)
    if docs:
        fmt = docs[0]['format']
        print(f"\n[4] Testing instant download for {fmt.upper()}...")
        start_time = time.time()
        resp = requests.get(f"{BASE_URL}/deals/{deal_id}/documents/{fmt}")
        duration = time.time() - start_time
        if resp.status_code == 200:
            print(f"Download successful! Size: {len(resp.content)} bytes. Time: {duration:.4f}s (Should be near-instant)")
        else:
            print(f"Download failed: {resp.status_code}")

    # 5. Bundle ZIP
    print("\n[5] Testing ZIP bundle...")
    resp = requests.get(f"{BASE_URL}/deals/{deal_id}/documents/bundle")
    if resp.status_code == 200:
        print(f"ZIP bundle successful! Size: {len(resp.content)} bytes.")
    else:
        print(f"ZIP bundle failed: {resp.status_code} {resp.text}")

if __name__ == "__main__":
    # Use a recent deal ID from the dashboard metrics if available, or a provided one
    deal_id = "test-deal" 
    if len(sys.argv) > 1:
        deal_id = sys.argv[1]
    
    test_document_hub(deal_id)
