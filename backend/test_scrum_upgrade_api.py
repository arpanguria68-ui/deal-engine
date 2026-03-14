import requests
import json
import time

BASE_URL = "http://localhost:8005/api/v1"


def test_clarification_tier1():
    print("\n--- Testing Tier 1: Hard Limit & Questions ---")
    payload = {
        "prompt": "I want to acquire a software company in Berlin with 50M revenue.",
        "deal_id": "test_deal_123",
        "company_name": "Berlin Soft",
        "clarification_round": 0,
    }
    r = requests.post(f"{BASE_URL}/chat/clarify", json=payload)
    if r.status_code == 200:
        data = r.json()
        questions = data.get("clarifying_questions", [])
        print(f"Success! Got {len(questions)} questions.")
        for i, q in enumerate(questions, 1):
            print(f"Q{i}: {q['question']}")

        # Verify Hard Limit (<= 3)
        if len(questions) > 3:
            print("❌ FAILURE: More than 3 questions returned!")
        else:
            print("✅ PASS: Correct question limit (<= 3).")

        # Verify Reasoning is present
        if all(q.get("reasoning") for q in questions):
            print("✅ PASS: All questions have reasoning.")
        else:
            print("❌ FAILURE: Missing reasoning for some questions.")
    else:
        print(f"❌ FAILURE: Status {r.status_code}")
        print(r.text)


def test_clarification_tier1_round_guardrail():
    print("\n--- Testing Tier 1: Round Guardrail ---")
    payload = {
        "prompt": "I want to acquire a software company in Berlin with 50M revenue.",
        "deal_id": "test_deal_123",
        "company_name": "Berlin Soft",
        "clarification_round": 1,  # Round 1 should be the last
    }
    r = requests.post(f"{BASE_URL}/chat/clarify", json=payload)
    if r.status_code == 200:
        data = r.json()
        questions = data.get("clarifying_questions", [])
        print(f"Success! Got {len(questions)} questions.")
        if len(questions) == 0:
            print("✅ PASS: Guardrail prevented more questions in Round 1+.")
            print(f"Skip Reason: {data.get('skip_reason')}")
        else:
            print("❌ FAILURE: Questions still returned in Round 1+!")
    else:
        print(f"❌ FAILURE: Status {r.status_code}")


def test_feedback_tier2_3():
    print("\n--- Testing Tier 2 & 3: Feedback Loop ---")
    payload = {
        "deal_type": "saas_acquisition",
        "questions": [
            {"question": "What is the churn rate?", "type": "financial_metric"},
            {"question": "Who are the competitors?", "type": "market_analysis"},
        ],
        "user_answer": "Churn is 5%. Competitors: Company X, Y.",
        "task_score": 0.85,
        "user_rating": "positive",
    }
    r = requests.post(f"{BASE_URL}/chat/clarify/feedback", json=payload)
    if r.status_code == 200:
        print("✅ PASS: Feedback stored successfully.")
        print(r.json())
    else:
        print(f"❌ FAILURE: Status {r.status_code}")


if __name__ == "__main__":
    try:
        test_clarification_tier1()
        test_clarification_tier1_round_guardrail()
        test_feedback_tier2_3()
    except Exception as e:
        print(f"Execution failed: {e}")
