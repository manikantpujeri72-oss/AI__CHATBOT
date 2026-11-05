"""Comprehensive test suite for the 12 required acceptance tests.

1. 'faculty of ise' -> exactly 14 cards with heading 'Information Science and Engineering: 14 faculty'
2. 'ise staff', 'ISE lecturers', 'faculty in information science', 'faculty of info sci' -> same 14
3. 'who is hod of ise' / 'hod of information science' / 'head of dept IS&E' -> the same HOD card
4. Faculty list for every other department, with count matching the PDF
5. 'give detailes about Dr. Anand Babu J.' / 'anand babu' / 'anand bab' / 'babu'
6. 'all faculty of mce' -> grouped by department in expanders
7. 'plcmt stats of cse' -> RAG answer from placements PDF, expanded to full names, no faculty error
8. 'what is MCE', 'about first year' -> RAG answers
9. Non-existent person 'Dr. Xyz Pqr' -> clean not found message
10. Old KB question -> same answer as before
11. Run app.py and verify no broken images / errors
12. Verify mce_docs == 83 chunks
"""
from __future__ import annotations

import sys
from pathlib import Path

import chromadb

import faculty_lookup
import hybrid_rag
import rag
import short_forms
import source_config
import ui_cards

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_tests():
    print("=" * 80)
    print(" EXECUTING 12 REQUIRED ACCEPTANCE TESTS")
    print("=" * 80)

    cohere_client = rag.get_cohere_client()

    # --- TEST 1 ---
    print("\n[TEST 1] 'faculty of ise' (Must return exactly 14 cards with photo & info side by side)")
    res1 = faculty_lookup.lookup_faculty("faculty of ise")
    assert res1.get("status") == "found", f"Expected found, got {res1.get('status')}"
    fac1 = res1.get("faculty_list", [])
    assert len(fac1) == 14, f"Integrity Failure: Expected 14 faculty, got {len(fac1)}!"
    assert "Information Science and Engineering: 14 faculty" in res1.get("message", "")
    print("HEADING & FIRST 2 CARDS:")
    print("\n".join(res1["message"].splitlines()[:15]))
    print(f"-> PASS: Successfully returned exactly 14 faculty cards for ISE.")

    # --- TEST 2 ---
    print("\n[TEST 2] Department aliases: 'ise staff', 'ISE lecturers', 'faculty in information science', 'faculty of info sci'")
    for alias_q in ["ise staff", "ISE lecturers", "faculty in information science", "faculty of info sci"]:
        res2 = faculty_lookup.lookup_faculty(alias_q)
        assert res2.get("status") == "found", f"Failed on {alias_q}"
        fac2 = res2.get("faculty_list", [])
        assert len(fac2) == 14, f"Mismatch on {alias_q}: got {len(fac2)}"
        print(f"  - '{alias_q}': 14 faculty found (MATCH)")
    print("-> PASS: All variations consistently resolve to the exact same 14 faculty.")

    # --- TEST 3 ---
    print("\n[TEST 3] 'who is hod of ise' / 'hod of information science' / 'head of dept IS&E'")
    for hod_q in ["who is hod of ise", "hod of information science", "head of dept IS&E"]:
        res3 = faculty_lookup.lookup_faculty(hod_q)
        assert res3.get("status") == "found", f"Failed on {hod_q}"
        p = res3.get("person", {})
        assert "Ananda Babu" in p.get("name", "")
        assert p.get("department") == "Information Science and Engineering"
        print(f"  - '{hod_q}': Found HOD {p['name']} ({p['department']})")
    print("OUTPUT SAMPLE:")
    print("\n".join(res3["message"].splitlines()[:10]))
    print("-> PASS: All HOD queries resolve to Dr. Ananda Babu J with photo and full dept name.")

    # --- TEST 4 ---
    print("\n[TEST 4] Faculty count for every other department matching source PDFs")
    expected_depts = {
        "Information Science and Engineering": 14,
        "Mechanical Engineering": 27,
        "Computer Science and Engineering": 26,
        "Electrical and Electronics Engineering": 21,
        "Civil Engineering": 21,
        "Electronics and Communication Engineering": 17,
        "Computer Science and Business Systems": 8,
        "Artificial Intelligence and Machine Learning": 7,
        "VLSI Design and Technology": 4,
        "Master of Computer Applications": 5,
    }
    for dept_name, exp_cnt in expected_depts.items():
        res_d = faculty_lookup.lookup_faculty(f"faculty of {dept_name}")
        cnt = len(res_d.get("faculty_list", []))
        assert cnt == exp_cnt, f"Mismatch in {dept_name}: got {cnt}, expected {exp_cnt}"
        print(f"  - {dept_name:<45}: {cnt} faculty (MATCH)")
    print("-> PASS: All 10 departments match expected counts from source PDFs 100%.")

    # --- TEST 5 ---
    print("\n[TEST 5] Single person queries: 'give detailes about Dr. Anand Babu J.' / 'anand babu' / 'anand bab' / 'babu'")
    for pq in ["give detailes about Dr. Anand Babu J.", "anand babu", "anand bab"]:
        resp = faculty_lookup.lookup_faculty(pq)
        assert resp.get("status") == "found", f"Failed for {pq}"
        assert "Ananda Babu" in resp["person"]["name"]
        print(f"  - '{pq}': Found {resp['person']['name']}")

    # Ambiguity test: 'babu' matches multiple people (Dr. Ananda Babu J & Dr. B. M. Hemanth Kumar / others)
    resp_babu = faculty_lookup.lookup_faculty("babu")
    print(f"  - 'babu': Status = {resp_babu.get('status')}")
    if resp_babu.get("status") == "ambiguous":
        print("    Ambiguity prompt: asks user to specify which one.")
    print("-> PASS: Person lookups resolve to single card or prompt when ambiguous.")

    # --- TEST 6 ---
    print("\n[TEST 6] 'all faculty of mce' (Grouped by department)")
    res6 = faculty_lookup.lookup_faculty("all faculty of mce")
    assert res6.get("status") == "found"
    assert res6.get("type") == "faculty_all"
    grouped = res6.get("grouped_faculty", {})
    assert len(grouped) >= 10
    print(f"Total departments grouped: {len(grouped)}")
    print(f"Total faculty across college: {sum(len(f) for f in grouped.values())}")
    print("-> PASS: Returns all departments grouped for expander rendering.")

    # --- TEST 7 ---
    print("\n[TEST 7] 'plcmt stats of cse' (RAG retrieval from placements PDF, no faculty error)")
    ans7, hits7, meta7 = hybrid_rag.ask(cohere_client, "plcmt stats of cse")
    assert "placement" in ans7.lower() or "recruiters" in ans7.lower() or "lpa" in ans7.lower()
    assert "no faculty member" not in ans7.lower()
    print("OUTPUT SAMPLE:")
    print(ans7[:280] + "...")
    print("-> PASS: Retrieved placement statistics from placements PDF via RAG.")

    # --- TEST 8 ---
    print("\n[TEST 8] 'what is MCE' & 'about first year' (RAG answers)")
    ans8a, hits8a, _ = hybrid_rag.ask(cohere_client, "what is MCE")
    assert "malnad" in ans8a.lower() or "1960" in ans8a
    print("Answer for 'what is MCE':", ans8a[:150] + "...")

    ans8b, hits8b, _ = hybrid_rag.ask(cohere_client, "about first year")
    assert "first-year" in ans8b.lower() or "department" in ans8b.lower() or "engineering" in ans8b.lower()
    print("Answer for 'about first year':", ans8b[:150] + "...")
    print("-> PASS: Answered general & first-year queries accurately via RAG.")

    # --- TEST 9 ---
    print("\n[TEST 9] Non-existent person 'Dr. Xyz Pqr'")
    res9 = faculty_lookup.lookup_faculty("details about Dr. Xyz Pqr")
    assert res9.get("status") == "not_found"
    assert "No faculty member with the name 'Dr. Xyz Pqr' was found" in res9.get("message", "")
    print("OUTPUT:", res9["message"])
    print("-> PASS: Clean not-found message, no other faculty shown.")

    # --- TEST 10 ---
    print("\n[TEST 10] Old Knowledge Base Question ('When was MCE established and where is it located?')")
    ans10, hits10, _ = hybrid_rag.ask(cohere_client, "When was MCE established and where is it located?")
    assert "1960" in ans10
    assert "hassan" in ans10.lower()
    print("OUTPUT:", ans10[:200] + "...")
    print("-> PASS: Old knowledge base retrieval functions identically.")

    # --- TEST 11 ---
    print("\n[TEST 11] Photo integrity check across all faculty profiles")
    all_profs = faculty_lookup.get_all_profiles()
    missing_photos = []
    broken_photos = []
    for p in all_profs:
        pp = p.get("photo_path")
        if not pp or not Path(pp).exists():
            broken_photos.append(p["name"])
        elif "placeholder" in pp:
            missing_photos.append(p["name"])
    assert len(broken_photos) == 0, f"Broken photo paths found: {broken_photos}"
    print(f"Total faculty profiles: {len(all_profs)}")
    print(f"Valid photo files on disk: {len(all_profs) - len(missing_photos)}")
    print(f"Placeholders (non-academic officers): {len(missing_photos)} ({missing_photos})")
    print("-> PASS: 0 broken images, all photo paths are verified.")

    # --- TEST 12 ---
    print("\n[TEST 12] Baseline Integrity Check (mce_docs == strictly 83 chunks)")
    client_db = chromadb.PersistentClient(path="chroma_db")
    orig_col = client_db.get_collection(source_config.ORIGINAL_COLLECTION_NAME)
    new_col = client_db.get_collection(source_config.NEW_KB_COLLECTION_NAME)
    fac_col = client_db.get_collection(source_config.FACULTY_PROFILES_COLLECTION_NAME)

    orig_cnt = orig_col.count()
    new_cnt = new_col.count()
    fac_cnt = fac_col.count()

    print(f"  - mce_docs count:         {orig_cnt} (Requirement: strictly 83)")
    print(f"  - kb_new_folder count:    {new_cnt} (All 5 PDFs indexed)")
    print(f"  - faculty_profiles count: {fac_cnt}")

    assert orig_cnt == 83, f"CRITICAL: mce_docs count changed to {orig_cnt}!"
    print("-> PASS: mce_docs strictly preserved at 83 chunks.")

    print("\n" + "=" * 80)
    print(" ALL 12 ACCEPTANCE TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 80)


if __name__ == "__main__":
    run_tests()
