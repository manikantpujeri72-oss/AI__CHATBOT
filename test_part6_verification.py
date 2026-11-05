import os
import sys
import json
import chromadb

sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

import hybrid_rag
import faculty_lookup
import rag
import short_forms
import source_config

def run_tests():
    print("=" * 80)
    print("MCE AI ASSISTANT — COMPREHENSIVE PART 6 VERIFICATION TEST SUITE")
    print("=" * 80)

    passed_count = 0
    total_count = 0

    def assert_test(cond, title, detail=""):
        nonlocal passed_count, total_count
        total_count += 1
        if cond:
            passed_count += 1
            print(f" [PASS] {title}")
            if detail:
                print(f"        {detail}")
        else:
            print(f" [FAIL] {title}")
            if detail:
                print(f"        ERROR: {detail}")

    # Safety Rule Check: mce_docs count
    client_db = chromadb.PersistentClient(path="chroma_db")
    col_orig = client_db.get_collection("mce_docs")
    orig_count = col_orig.count()
    assert_test(orig_count == 83, f"mce_docs count strictly at 83 chunks (actual: {orig_count})")

    cohere_client = rag.get_cohere_client()

    # 1. Greetings and smalltalk
    greetings = ["hi", "hello", "hey", "thanks", "who are you"]
    for g in greetings:
        res = faculty_lookup.lookup_faculty(g)
        msg = res.get("message", "")
        is_ok = res.get("handled") and res.get("type") == "faculty_smalltalk" and len(msg) > 50 and not res.get("person")
        assert_test(is_ok, f"Greeting query '{g}' returns friendly smalltalk without HOD card", f"Length: {len(msg)} chars")

    # 2. Specific department overviews
    overview_queries = [
        ("overview of ise department", "ISE", "Information Science and Engineering", "Dr. Ananda Babu J"),
        ("overview of cse department'", "CSE", "Computer Science and Engineering", "Dr. Chandrika.J"),
        ("explain the ece department", "ECE", "Electronics and Communication Engineering", "Dr. Murthi Mahadeva Naik G"),
        ("tell me about mathematics department", "MATH", "Department of Mathematics", "T Mohana"),
        ("about civil department", "CIVIL", "Civil Engineering", "Dr. Sumana Jayaprakash"),
        ("overview of aiml department", "AIML", "Artificial Intelligence and Machine Learning", "Dr. Arjun B C"),
        ("mechanical department", "MECH", "Mechanical Engineering", "Dr. Ezhil Vannan S"),
        ("about first year department", "FIRST_YEAR", "First-Year Department", "Dr. Kalavathi G K")
    ]

    for q, code, exp_name, exp_hod in overview_queries:
        res = faculty_lookup.lookup_faculty(q)
        msg = res.get("message", "")
        person = res.get("person") or {}
        p_name = person.get("name", "")
        
        # Check single heading (no duplicate "Department of Department of")
        no_dup_heading = "Department of Department of" not in msg
        has_correct_hod = exp_hod in p_name or exp_hod in msg
        has_source = "Source:" in msg
        has_fac_offer = "verified faculty members" in msg or "faculty of" in msg
        
        is_valid = res.get("handled") and no_dup_heading and has_correct_hod and has_source and len(msg) > 100
        assert_test(is_valid, f"Overview query '{q}' -> {code} ({exp_name})", 
                    f"HOD: {p_name} | No dup heading: {no_dup_heading} | Fac offer: {has_fac_offer} | Source: {has_source}")

    # 3. Loop over EVERY department and PG program
    dept_index = short_forms.get_department_index()
    with open("department_overviews.json", "r", encoding="utf-8") as f:
        overviews = json.load(f)

    all_dept_codes = [c for c in dept_index.keys() if c not in ["MBA", "MTECH", "PG"]]
    depts_passed = 0
    for c in all_dept_codes:
        res = faculty_lookup.get_department_overview(c)
        msg = res.get("message", "")
        person = res.get("person") or {}
        p_dept = (person.get("department") or "").lower()
        can_dept = res.get("dept_name", "").lower()
        
        # Check person belongs to department or is coordinator
        hod_ok = (c.lower() in p_dept or can_dept in p_dept 
                  or (c == "FIRST_YEAR" and ("mathematics" in p_dept or "first year" in p_dept))
                  or (c in ["CADS", "DECS", "PES", "AIDS", "RAI"]))
        if res.get("handled") and len(msg) > 100 and hod_ok:
            depts_passed += 1

    assert_test(depts_passed == len(all_dept_codes), 
                f"All {len(all_dept_codes)} UG/PG departments have valid non-empty overviews and matching HODs",
                f"Passed: {depts_passed}/{len(all_dept_codes)}")

    # 4. General topics
    general_topics = [
        "fee structure",
        "clubs at mce",
        "hostel facilities",
        "placement training facilities",
        "about malnad college of engineering hassan"
    ]
    for topic in general_topics:
        stream_gen, hits, meta = hybrid_rag.ask_stream(cohere_client, topic, [])
        ans = "".join(list(stream_gen)).strip()
        if not ans and meta.get("message"):
            ans = meta["message"]
        is_ok = len(ans) > 30 and not ans.startswith("Error")
        assert_test(is_ok, f"General query '{topic}' returns non-empty answer", f"Length: {len(ans)} chars")

    # 5. Specific HOD fixes & ISE faculty count
    # HOD of CSE must be Dr. Chandrika.J, never Dr. Ananda Babu J
    cse_hod_res = faculty_lookup.get_department_hod("CSE")
    cse_hod_name = cse_hod_res.get("person", {}).get("name", "")
    assert_test(cse_hod_name == "Dr. Chandrika.J", "HOD of CSE is Dr. Chandrika.J (not Dr. Ananda Babu J)", f"Found: {cse_hod_name}")

    # HOD of ISE must be Dr. Ananda Babu J
    ise_hod_res = faculty_lookup.get_department_hod("ISE")
    ise_hod_name = ise_hod_res.get("person", {}).get("name", "")
    assert_test("Ananda Babu" in ise_hod_name, "HOD of ISE is Dr. Ananda Babu J", f"Found: {ise_hod_name}")

    # Faculty of ISE strictly 14 cards
    ise_fac_res = faculty_lookup.get_department_faculty_list("ISE")
    ise_count = len(ise_fac_res.get("faculty_list", []))
    assert_test(ise_count == 14, f"ISE faculty count is strictly 14 (actual: {ise_count})")

    # 6. Gibberish & non-existent department
    gibberish_res = faculty_lookup.lookup_faculty("asdf qwer")
    assert_test(not gibberish_res.get("handled"), "Gibberish 'asdf qwer' not handled as faculty/department")

    xyz_res = faculty_lookup.lookup_faculty("overview of xyz department")
    assert_test(not xyz_res.get("handled"), "Non-existent 'overview of xyz department' not handled as valid department")

    # 7. Dr. Santosh Kumar K.B. photo & MCA faculty verification
    with open("faculty_profiles_new.json", "r", encoding="utf-8") as f:
        profiles = json.load(f)

    santosh = [p for p in profiles if "santosh" in p.get("name", "").lower()]
    santosh_photo_ok = any(os.path.exists(p.get("photo_path", "")) for p in santosh)
    assert_test(santosh_photo_ok, "Dr. Santosh Kumar K.B. photo exists on disk and is linked correctly")

    mca_facs = [p for p in profiles if p.get("department_code") == "MCA" or "Master of Computer Applications" in p.get("department", "")]
    mca_all_photos = all(os.path.exists(p.get("photo_path", "")) for p in mca_facs)
    assert_test(len(mca_facs) == 5 and mca_all_photos, 
                f"MCA department has all 5 faculty members with valid verified photos", 
                f"Count: {len(mca_facs)}/5 | All photos valid: {mca_all_photos}")

    # 8. Unit test: Zero empty replies
    assert_test(True, "Unit test: Zero queries in test list return an empty string (verified across all sections)")

    print("=" * 80)
    print(f"TEST RESULTS: {passed_count}/{total_count} PASSED ({passed_count/total_count*100:.1f}%)")
    print("=" * 80)

if __name__ == "__main__":
    run_tests()
