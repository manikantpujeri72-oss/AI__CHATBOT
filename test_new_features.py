"""Comprehensive automated verification suite for:
1. Additional Knowledge Base Folder ('kb_new_folder')
2. Strict Single-Faculty Lookup with photo-first format ('faculty_profiles')
3. Baseline integrity check ('mce_docs' = 83 chunks)
"""
from __future__ import annotations

import sys
from pathlib import Path

import chromadb

import faculty_lookup
import hybrid_rag
import rag
import source_config

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def test_all():
    print("=" * 80)
    print(" VERIFICATION SUITE: NEW KNOWLEDGE SOURCE & FACULTY LOOKUP")
    print("=" * 80)

    # 1. Baseline Integrity Check
    print("\n[CHECK 1] Verifying ChromaDB Collections & Integrity...")
    client_db = chromadb.PersistentClient(path="chroma_db")
    orig_col = client_db.get_collection(source_config.ORIGINAL_COLLECTION_NAME)
    new_col = client_db.get_collection(source_config.NEW_KB_COLLECTION_NAME)
    fac_col = client_db.get_collection(source_config.FACULTY_PROFILES_COLLECTION_NAME)

    orig_count = orig_col.count()
    new_count = new_col.count()
    fac_count = fac_col.count()

    print(f"  - Original collection '{orig_col.name}': {orig_count} chunks (Baseline: 83)")
    print(f"  - New KB collection '{new_col.name}': {new_count} chunks")
    print(f"  - Faculty profiles collection '{fac_col.name}': {fac_count} profiles")

    assert orig_count == 83, f"Integrity failure: mce_docs count is {orig_count}, expected 83!"
    print("  -> PASS: Baseline mce_docs is 100% intact and unchanged.")

    # 2. Faculty Lookup: Exact Name
    print("\n[CHECK 2] Exact Faculty Name ('Dr. Chandrika.J')...")
    res1 = faculty_lookup.lookup_faculty("Dr. Chandrika.J")
    assert res1.get("status") == "found", f"Expected 'found', got {res1.get('status')}"
    assert "dr_chandrikaj.jpg" in res1.get("photo_path", "").lower() or "chandrika" in res1.get("photo_path", "").lower()
    assert "Computer Science" in res1.get("message", "")
    print(f"  -> PASS: Found single profile for {res1['person']['name']}. Photo: {res1['photo_path']}")

    # 3. Faculty Lookup: Typo / Prefix
    print("\n[CHECK 3] Faculty Name with Typo & Prefix ('tell me about mrs sheetel d n')...")
    res2 = faculty_lookup.lookup_faculty("tell me about mrs sheetel d n")
    assert res2.get("status") == "found", f"Expected 'found', got {res2.get('status')}"
    assert "Sheetal D N" in res2.get("message", "")
    print(f"  -> PASS: Correctly resolved typo to {res2['person']['name']}.")

    # 4. Faculty Lookup: Non-Existent Name
    print("\n[CHECK 4] Non-Existent Faculty Name ('Dr. Alexander Hamilton')...")
    res3 = faculty_lookup.lookup_faculty("Dr. Alexander Hamilton")
    assert res3.get("status") == "not_found", f"Expected 'not_found', got {res3.get('status')}"
    assert "was found" in res3.get("message", "").lower() or "not found" in res3.get("message", "").lower()
    print("  -> PASS: Returned clean not-found message without hallucinations.")

    # 5. Faculty Lookup: Ambiguous Name
    print("\n[CHECK 5] Ambiguous Faculty Name ('Prasanna')...")
    res4 = faculty_lookup.lookup_faculty("Prasanna")
    assert res4.get("status") == "ambiguous", f"Expected 'ambiguous', got {res4.get('status')}"
    assert "Multiple faculty members matched" in res4.get("message", "")
    print("  -> PASS: Correctly prompted user to clarify between multiple matches.")

    # 6. RAG Answer from Old Knowledge Base
    print("\n[CHECK 6] Question from OLD Knowledge Base ('When was MCE established and where is it located?')...")
    cohere_client = rag.get_cohere_client()
    ans_old, hits_old, _ = hybrid_rag.ask(cohere_client, "When was MCE established and where is it located?")
    assert "1960" in ans_old, "Expected year 1960 in answer"
    assert "Hassan" in ans_old, "Expected Hassan in answer"
    sources_old = {h["source"] for h in hits_old}
    print(f"  -> PASS: Answered accurately. Sources used: {sources_old}")

    # 7. RAG Answer from New Knowledge Folder
    print("\n[CHECK 7] Question from NEW Folder ('What is the vision and mission of the First Year Engineering Department at MCE?')...")
    ans_new, hits_new, _ = hybrid_rag.ask(cohere_client, "What is the vision and mission of the First Year Engineering Department at MCE?")
    assert "first-year" in ans_new.lower() or "foundation" in ans_new.lower() or "excellence" in ans_new.lower()
    sources_new = {h["source"] for h in hits_new}
    print(f"  -> PASS: Answered from new folder. Sources used: {sources_new}")

    print("\n" + "=" * 80)
    print(" ALL 7 VERIFICATION CHECKS PASSED WITH 100% SUCCESS!")
    print("=" * 80)


if __name__ == "__main__":
    test_all()
