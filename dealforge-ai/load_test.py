import urllib.request
import urllib.error
import concurrent.futures
import time
import json
from collections import Counter

# Configuration
CONCURRENT_USERS = 30
TOTAL_REQUESTS = 150
TARGET_URL = "http://localhost:8000/api/v1/models/available"


def make_request(request_id):
    start_time = time.time()
    result = {"id": request_id, "status": None, "latency": 0.0, "error": None}

    try:
        # Increase timeout because this endpoint fans out to 5 LLM providers
        req = urllib.request.Request(TARGET_URL, method="GET")
        with urllib.request.urlopen(req, timeout=15) as response:
            result["status"] = response.getcode()
            response.read()  # drain
    except urllib.error.HTTPError as e:
        result["status"] = e.code
        result["error"] = str(e)
    except urllib.error.URLError as e:
        result["status"] = 0
        result["error"] = str(e.reason)
    except Exception as e:
        result["status"] = -1
        result["error"] = str(e)

    result["latency"] = time.time() - start_time
    return result


def main():
    print(f"Starting Load Test on Dynamic Discovery Endpoint...")
    print(f"Target URL: {TARGET_URL}")
    print(f"This endpoint spawns 5 concurrent outbound HTTP requests per hit.")
    print(f"Concurrent Users (Threads): {CONCURRENT_USERS}")
    print(f"Total Requests: {TOTAL_REQUESTS}")
    print("-" * 40)

    start_total = time.time()
    results = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=CONCURRENT_USERS
    ) as executor:
        futures = [executor.submit(make_request, i) for i in range(TOTAL_REQUESTS)]

        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            results.append(res)
            if len(results) % (TOTAL_REQUESTS // 10) == 0:
                print(f"Completed {len(results)}/{TOTAL_REQUESTS} requests...")

    total_time = time.time() - start_total

    latencies = [r["latency"] for r in results if r["status"] == 200]
    status_codes = Counter([r["status"] for r in results])
    errors = Counter([r["error"] for r in results if r["error"] is not None])

    print("-" * 40)
    print("LOAD TEST RESULTS")
    print("-" * 40)
    print(f"Total Time Taken: {total_time:.2f} seconds")
    print(f"Requests per Second: {(TOTAL_REQUESTS / total_time):.2f} RPS")
    print("\nStatus Codes:")
    for code, count in status_codes.items():
        print(f"  HTTP {code}: {count}")

    if latencies:
        print("\nLatency Metrics (for successful requests):")
        print(f"  Min: {min(latencies):.3f}s")
        print(f"  Max: {max(latencies):.3f}s")
        print(f"  Avg: {(sum(latencies)/len(latencies)):.3f}s")
        latencies.sort()
        print(f"  p95: {latencies[int(len(latencies) * 0.95)]:.3f}s")

    if errors:
        print("\nErrors Encountered:")
        for err, count in errors.items():
            print(f"  {err}: {count} times")


if __name__ == "__main__":
    main()
