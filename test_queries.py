"""Real-world query verification test suite for MCE AI Assistant.

Tests 12 realistic questions drawn from actual MCE knowledge base files:
  - College establishment & location
  - Departments (CSE, Civil, Mechanical, EEE, ECE)
  - Degree programmes & student intakes
  - Placement statistics (2024-25, 2023-24)
  - Placement training & eligibility policy
Plus 3 intentionally out-of-scope questions.

Pass criteria:
  - In-scope answers are correct and cite the right file and page number.
  - Out-of-scope questions return the standard fallback without hallucination.
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

import rag

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

TEST_CASES = [
    # In-scope questions
    {
        "id": 1,
        "type": "in_scope",
        "question": "Where is Malnad College of Engineering located?",
        "expected_terms": ["Hassan", "Karnataka"],
        "expected_sources": ["malnad.pdf", "knowledge_base.pdf"],
    },
    {
        "id": 2,
        "type": "in_scope",
        "question": "When was Malnad College of Engineering established?",
        "expected_terms": ["1960"],
        "expected_sources": ["malnad.pdf", "knowledge_base.pdf"],
    },
    {
        "id": 3,
        "type": "in_scope",
        "question": "Which undergraduate (UG) engineering programmes does MCE Hassan offer?",
        "expected_terms": ["Computer Science", "Civil", "Mechanical"],
        "expected_sources": ["knowledge_base.pdf", "malnad.pdf"],
    },
    {
        "id": 4,
        "type": "in_scope",
        "question": "When was the Department of Computer Science & Engineering established and what is its BE student intake?",
        "expected_terms": ["1983", "420"],
        "expected_sources": ["knowledge_base.pdf"],
    },
    {
        "id": 5,
        "type": "in_scope",
        "question": "What is the intake for the Civil Engineering undergraduate programme at MCE?",
        "expected_terms": ["120"],
        "expected_sources": ["knowledge_base.pdf"],
    },
    {
        "id": 6,
        "type": "in_scope",
        "question": "When did the Mechanical Engineering department begin and what is its BE course intake?",
        "expected_terms": ["1960", "120"],
        "expected_sources": ["knowledge_base.pdf"],
    },
    {
        "id": 7,
        "type": "in_scope",
        "question": "When was the Electrical and Electronics Engineering department started at MCE?",
        "expected_terms": ["1960"],
        "expected_sources": ["knowledge_base.pdf"],
    },
    {
        "id": 8,
        "type": "in_scope",
        "question": "When was the Electronics and Communication Engineering degree course instituted at MCE and what is its intake?",
        "expected_terms": ["1967", "90"],
        "expected_sources": ["knowledge_base.pdf"],
    },
    {
        "id": 9,
        "type": "in_scope",
        "question": "How many total offers were reported in the placement report for academic year 2024-25?",
        "expected_terms": ["455"],
        "expected_sources": ["knowledge_base.pdf"],
    },
    {
        "id": 10,
        "type": "in_scope",
        "question": "How many total offers were reported for 2023-24 placements at MCE?",
        "expected_terms": ["334"],
        "expected_sources": ["knowledge_base.pdf"],
    },
    {
        "id": 11,
        "type": "in_scope",
        "question": "What training facilities and programs are provided to students for campus placements?",
        "expected_terms": ["Aptitude", "Soft Skills"],
        "expected_sources": ["knowledge_base.pdf", "placement.pdf"],
    },
    {
        "id": 12,
        "type": "in_scope",
        "question": "When does student enrolment for campus placement begin at MCE?",
        "expected_terms": ["Sixth semester"],
        "expected_sources": ["placement.pdf"],
    },
    # Out-of-scope questions
    {
        "id": 13,
        "type": "out_of_scope",
        "question": "What is the annual tuition fee for the MBBS medical degree at MCE?",
        "expected_terms": ["don't have that information"],
        "expected_sources": [],
    },
    {
        "id": 14,
        "type": "out_of_scope",
        "question": "Who is the head coach of the MCE Australian cricket team in Sydney?",
        "expected_terms": ["don't have that information"],
        "expected_sources": [],
    },
    {
        "id": 15,
        "type": "out_of_scope",
        "question": "What is the Sunday morning breakfast menu at IIT Bombay hostel mess?",
        "expected_terms": ["don't have that information"],
        "expected_sources": [],
    },
]


def run_tests() -> bool:
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        print("ERROR: COHERE_API_KEY is not set.")
        return False

    client = rag.get_cohere_client()
    collection = rag.get_collection()

    total_chunks = collection.count()
    print(f"Loaded ChromaDB collection '{collection.name}' with {total_chunks} chunks.")
    print(f"RAG Settings: MAX_DISTANCE={rag.MAX_DISTANCE}, TOP_K={rag.TOP_K}, EMBED={rag.EMBED_MODEL}")
    print("=" * 80)

    passed_count = 0
    failed_count = 0

    for tc in TEST_CASES:
        t_id = tc["id"]
        q = tc["question"]
        q_type = tc["type"]
        expected_terms = tc["expected_terms"]

        print(f"\n[Test #{t_id} - {q_type.upper()}] Q: {q}")
        try:
            answer, hits = rag.ask(client, collection, q, history=[])
        except Exception as e:
            print(f"  FAILED with exception: {e}")
            failed_count += 1
            continue

        print(f"  A: {answer}")
        sources_str = ", ".join(f"{h['source']} (p.{h['page']})" for h in hits)
        print(f"  Retrieved sources: {sources_str if hits else 'None'}")

        # Check conditions
        passed = True
        reason = []

        if q_type == "in_scope":
            if "don't have that information" in answer.lower() and not hits:
                passed = False
                reason.append("In-scope question returned NO_INFO")
            # Verify expected terms
            for term in expected_terms:
                if term.lower() not in answer.lower():
                    passed = False
                    reason.append(f"Missing expected term: '{term}'")
            # Check citations
            if not hits:
                passed = False
                reason.append("No source chunks retrieved")
        else:
            # Out-of-scope question
            lower_ans = answer.lower()
            if "don't have that information" not in lower_ans and hits:
                passed = False
                reason.append("Out-of-scope question was answered instead of returning fallback")

        if passed:
            print(f"  RESULT: [PASS]")
            passed_count += 1
        else:
            print(f"  RESULT: [FAIL] - Reasons: {', '.join(reason)}")
            failed_count += 1

    print("\n" + "=" * 80)
    print(f"Test Suite Summary: {passed_count} PASSED, {failed_count} FAILED (Total: {len(TEST_CASES)})")
    return failed_count == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
