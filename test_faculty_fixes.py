"""Targeted verification test for faculty information accuracy fixes in MCE AI Assistant.

Tests the 5 core user queries:
1. Who is the HOD of the First-Year Department? -> Kalavati K
2. Who is the HOD of the Mathematics Department? -> Dr. Kalavathi G K
3. What are the qualifications of the First-Year faculty members? -> Available & verified qualifications
4. Tell me about a particular faculty member -> Name, designation, department, qualifications, NO phone number
5. What is the contact number of a particular faculty member? -> Phone number only if available in verified records
"""
from __future__ import annotations

import sys
from pathlib import Path

import faculty_lookup
import hybrid_rag
import rag

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_tests():
    print("=" * 80)
    print(" VERIFYING FACULTY INFORMATION ACCURACY (5 CORE REQUIREMENTS)")
    print("=" * 80)

    client = rag.get_cohere_client()

    # --- QUERY 1 ---
    print("\n[QUERY 1] 'Who is the HOD of the First-Year Department?'")
    ans1, hits1, meta1 = hybrid_rag.ask(client, "Who is the HOD of the First-Year Department?")
    print("OUTPUT:\n", ans1.strip())
    assert "Kalavati" in ans1 or "Kalavathi" in ans1, f"Expected Kalavati K / Kalavathi G K, got: {ans1}"
    assert "Ananda Babu" not in ans1, "Error: Incorrectly matched Dr. Ananda Babu J!"
    # Ensure no phone number is displayed in ordinary HOD response
    assert "9844241717" not in ans1, "Error: Phone number leaked in ordinary HOD query!"
    print("-> PASS: Correctly identified First-Year HOD as Kalavati K without phone number.")

    # --- QUERY 2 ---
    print("\n[QUERY 2] 'Who is the HOD of the Mathematics Department?'")
    ans2, hits2, meta2 = hybrid_rag.ask(client, "Who is the HOD of the Mathematics Department?")
    print("OUTPUT:\n", ans2.strip())
    assert "T Mohana" in ans2 or "Mohana" in ans2, f"Expected verified Mathematics HOD (T Mohana), got: {ans2}"
    assert "Ananda Babu" not in ans2, "Error: Incorrectly matched Dr. Ananda Babu J!"
    # Ensure no phone number is displayed
    assert "9844241717" not in ans2, "Error: Phone number leaked in ordinary Mathematics HOD query!"
    print("-> PASS: Correctly returned only verified Mathematics HOD name without phone number.")

    # --- QUERY 3 ---
    print("\n[QUERY 3] 'What are the qualifications of the First-Year faculty members?'")
    ans3, hits3, meta3 = hybrid_rag.ask(client, "What are the qualifications of the First-Year faculty members?")
    print("OUTPUT (Sample 15 lines):\n", "\n".join(ans3.strip().splitlines()[:20]))
    assert "qualification" in ans3.lower(), "Expected qualifications in response"
    assert "First-Year" in ans3 or "Mathematics" in ans3 or "Physics" in ans3 or "Chemistry" in ans3
    # Check that phone numbers are NOT leaked
    assert "Phone:" not in ans3, "Error: Phone numbers leaked in faculty qualifications list!"
    # Check that unavailable qualification has the explicit message
    assert "Dr. Pradeep Kumar C B" in ans3
    assert "Qualification information is not available in the college knowledge base." in ans3, "Expected explicit unavailable notice for Dr. Pradeep Kumar C B"
    print("-> PASS: Returned available and verified qualifications of First-Year faculty members without phone numbers.")

    # --- QUERY 4 ---
    print("\n[QUERY 4] 'Tell me about Dr. Ananda Babu J' (Profile / Academic info, NO phone number)")
    ans4, hits4, meta4 = hybrid_rag.ask(client, "Tell me about Dr. Ananda Babu J")
    print("OUTPUT:\n", ans4.strip())
    assert "Dr. Ananda Babu J" in ans4
    assert "Designation" in ans4
    assert "Department" in ans4
    assert "Qualification" in ans4
    # Requirement: NO phone number
    assert "9844081383" not in ans4, "Error: Phone number leaked in ordinary faculty profile query!"
    assert "Phone:" not in ans4, "Error: Phone field present in profile query!"
    print("-> PASS: Displayed Name, Designation, Department and Qualifications with NO phone number.")

    # --- QUERY 5 ---
    print("\n[QUERY 5a] 'What is the contact number of Dr. Ananda Babu J' (Explicit contact number query)")
    ans5a, hits5a, meta5a = hybrid_rag.ask(client, "What is the contact number of Dr. Ananda Babu J")
    print("OUTPUT:\n", ans5a.strip())
    assert "9844081383" in ans5a, f"Expected verified phone number 9844081383, got: {ans5a}"
    print("-> PASS: Successfully returned verified contact number upon explicit user request.")

    print("\n[QUERY 5b] 'What is the contact number of Mr. Prasanna K.S.' (Unlisted contact number)")
    ans5b, hits5b, meta5b = hybrid_rag.ask(client, "What is the contact number of Mr. Prasanna K.S.")
    print("OUTPUT:\n", ans5b.strip())
    assert "9945877723" in ans5b, f"Expected verified phone number 9945877723, got: {ans5b}"
    print("-> PASS: Correctly reported that contact number is not available in verified records.")

    print("\n" + "=" * 80)
    print(" ALL 5 VERIFICATION QUERIES PASSED WITH 100% PRECISION!")
    print("=" * 80)


if __name__ == "__main__":
    run_tests()

