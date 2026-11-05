"""Comprehensive validation script executing all 15 tests required in PART 4."""
from __future__ import annotations

import json
from pathlib import Path
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import chromadb

import faculty_lookup
import hod_manager
import hybrid_rag
import rag
import source_config

PASS_COUNT = 0
FAIL_COUNT = 0


def report(test_name: str, passed: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if passed:
        PASS_COUNT += 1
        print(f"[PASS] {test_name}: {detail}")
    else:
        FAIL_COUNT += 1
        print(f"[FAIL] {test_name}: {detail}")


def run_all_tests():
    global PASS_COUNT, FAIL_COUNT
    print("=" * 80)
    print(" EXECUTING PART 4 ACCEPTANCE TESTS (1 to 15)")
    print("=" * 80)

    # TEST 1: ISE HOD queries
    print("\n--- TEST 1: ISE HOD Queries ---")
    for q in ["hod of ise", "ise hod", "who is the head of information science"]:
        res = faculty_lookup.lookup_faculty(q)
        name = res.get("person", {}).get("name", "")
        passed = (name == "Dr. Ananda Babu J" and res.get("status") == "found")
        report(q, passed, f"Returned {name} (Card Heading: {res.get('title')})")

    # TEST 2: EEE HOD queries
    print("\n--- TEST 2: EEE HOD Queries ---")
    for q in ["eee hod", "hod of electrical and electronics"]:
        res = faculty_lookup.lookup_faculty(q)
        name = res.get("person", {}).get("name", "")
        passed = ("rajanna" in name.lower() and res.get("status") == "found")
        report(q, passed, f"Returned {name} (Card Heading: {res.get('title')})")

    # TEST 3: Civil HOD queries
    print("\n--- TEST 3: Civil HOD Queries ---")
    for q in ["civil hod", "hod of civil engineering"]:
        res = faculty_lookup.lookup_faculty(q)
        name = res.get("person", {}).get("name", "")
        passed = ("sumana" in name.lower() and res.get("status") == "found")
        report(q, passed, f"Returned {name} (Card Heading: {res.get('title')})")

    # TEST 4: E&I HOD queries
    print("\n--- TEST 4: E&I HOD Queries ---")
    for q in ["E&I hod", "hod of electronics and instrumentation", "EIE hod"]:
        res = faculty_lookup.lookup_faculty(q)
        name = res.get("person", {}).get("name", "")
        passed = ("naveen" in name.lower() and res.get("status") == "found")
        report(q, passed, f"Returned {name} (Card Heading: {res.get('title')})")

    # TEST 5: First-Year HOD queries
    print("\n--- TEST 5: First-Year HOD Queries ---")
    for q in ["hod of first year", "first year hod", "who is hod of 1st year"]:
        res = faculty_lookup.lookup_faculty(q)
        name = res.get("person", {}).get("name", "")
        passed = ("kalavathi" in name.lower() and res.get("status") == "found")
        report(q, passed, f"Returned {name} (Card Heading: {res.get('title')})")

    # TEST 6: Mathematics HOD queries
    print("\n--- TEST 6: Mathematics HOD Queries ---")
    for q in ["mathematics hod", "maths hod", "hod of mathematics department"]:
        res = faculty_lookup.lookup_faculty(q)
        name = res.get("person", {}).get("name", "")
        passed = ("mohana" in name.lower() and res.get("status") == "found")
        report(q, passed, f"Returned {name} (Card Heading: {res.get('title')})")

    # TEST 7: MCA HOD query
    print("\n--- TEST 7: MCA HOD Query ---")
    res7 = faculty_lookup.lookup_faculty("mca hod")
    name7 = res7.get("person", {}).get("name", "")
    p_ok7 = Path(res7.get("person", {}).get("photo_path", "")).exists()
    report("mca hod", name7 == "Mrs. Margaret R.E." and p_ok7, f"Returned {name7}, Photo exists: {p_ok7}")

    # TEST 8: MCA faculty queries
    print("\n--- TEST 8: MCA Faculty Queries ---")
    for q in ["mca faculty", "faculty of mca"]:
        res = faculty_lookup.lookup_faculty(q)
        fac = res.get("faculty_list", [])
        passed = (len(fac) == 5 and res.get("status") == "found")
        report(q, passed, f"Found {len(fac)} cards (expected 5)")

    # TEST 9: PG Programs queries
    print("\n--- TEST 9: PG Program Faculty Queries ---")
    pg_queries = [
        ("faculty of cads", 7, "CADS"),
        ("decs faculty", 7, "DECS"),
        ("power and energy systems faculty", 2, "PES"),
        ("ai and ds faculty", 2, "AIDS"),
        ("mtech faculty", 18, "All M.Tech"),
    ]
    for q, count, prog in pg_queries:
        res = faculty_lookup.lookup_faculty(q)
        fac = res.get("faculty_list", [])
        passed = (len(fac) == count and res.get("status") == "found")
        report(q, passed, f"Program {prog}: {len(fac)} faculty cards (expected {count})")

    # TEST 10: ISE faculty query (Must be exactly 14)
    print("\n--- TEST 10: ISE Faculty Query ---")
    res10 = faculty_lookup.lookup_faculty("faculty of ise")
    fac10 = res10.get("faculty_list", [])
    report("faculty of ise", len(fac10) == 14, f"Found {len(fac10)} faculty cards (strictly expected 14)")

    # TEST 11: Chemistry & Physics HOD queries
    print("\n--- TEST 11: Chemistry & Physics HOD Queries ---")
    res_chem = faculty_lookup.lookup_faculty("hod of chemistry")
    name_chem = res_chem.get("person", {}).get("name", "")
    passed_chem = ("krishnakumar" in name_chem.lower() or "pradeep" in name_chem.lower())
    report("hod of chemistry", passed_chem, f"Returned {name_chem}")

    res_phy = faculty_lookup.lookup_faculty("hod of physics")
    name_phy = res_phy.get("person", {}).get("name", "")
    passed_phy = ("prasanna" in name_phy.lower())
    report("hod of physics", passed_phy, f"Returned {name_phy}")

    # TEST 12: HOD of EVERY department in hod_verified.json
    print("\n--- TEST 12: Loop over all departments in hod_verified.json ---")
    v_map = hod_manager.load_hod_verified()
    all_hods_matched = True
    for code, v_entry in v_map.items():
        if v_entry.get("status") == "not_offered":
            continue
        res_h = faculty_lookup.get_department_hod(code)
        ret_name = res_h.get("person", {}).get("name", "")
        exp_name = v_entry["hod_name"]
        match = (ret_name == exp_name or exp_name.lower() in ret_name.lower())
        if not match:
            all_hods_matched = False
            report(f"HOD Check {code}", False, f"Expected {exp_name}, got {ret_name}")
    report("All Departments HOD Match", all_hods_matched, f"Verified all {len(v_map)} department heads")

    # TEST 13: Non-existent person or department
    print("\n--- TEST 13: Non-existent person or department ---")
    res_non_p = faculty_lookup.lookup_faculty("details about Dr. NonExistent PersonXYZ")
    report("Non-existent person", res_non_p.get("status") == "not_found", res_non_p.get("message", "")[:80])
    res_non_d = faculty_lookup.lookup_faculty("faculty of aeronautical engineering")
    passed_non_d = (not res_non_d.get("handled") or res_non_d.get("status") in ["not_found", "not_listed", "not_offered"])
    report("Non-existent department", passed_non_d, "Properly handled as unlisted/unhandled department")

    # TEST 14: General RAG questions (Placements & About MCE)
    print("\n--- TEST 14: General RAG Questions ---")
    cohere_client = rag.get_cohere_client()
    ans14a, hits14a, meta14a = hybrid_rag.ask(cohere_client, "plcmt stats of cse")
    report("General RAG: plcmt stats of cse", len(ans14a) > 50 and "cse" in ans14a.lower(), f"Answer length {len(ans14a)} chars")

    ans14b, hits14b, meta14b = hybrid_rag.ask(cohere_client, "what is MCE")
    report("General RAG: what is MCE", "malnad" in ans14b.lower() or "1960" in ans14b, f"Answer length {len(ans14b)} chars")

    # TEST 15: Database Safety Check (mce_docs == 83)
    print("\n--- TEST 15: Collection Safety Check ---")
    client_db = chromadb.PersistentClient(path="chroma_db")
    col_orig = client_db.get_collection("mce_docs")
    count_orig = col_orig.count()
    report("mce_docs unchanged at 83 chunks", count_orig == 83, f"Current count = {count_orig}")

    print("\n" + "=" * 80)
    print(f" TOTAL TESTS COMPLETED: PASS = {PASS_COUNT}, FAIL = {FAIL_COUNT}")
    print("=" * 80)


if __name__ == "__main__":
    run_all_tests()

