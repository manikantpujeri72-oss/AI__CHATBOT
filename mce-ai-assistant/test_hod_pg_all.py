import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import faculty_lookup

test_queries = [
    ("hod of ise", "Dr. Ananda Babu J"),
    ("ise hod", "Dr. Ananda Babu J"),
    ("who is the head of information science", "Dr. Ananda Babu J"),
    ("eee hod", "Rajanna"),
    ("hod of electrical and electronics", "Rajanna"),
    ("civil hod", "Sumana"),
    ("hod of civil engineering", "Sumana"),
    ("E&I hod", "Naveen"),
    ("hod of electronics and instrumentation", "Naveen"),
    ("EIE hod", "Naveen"),
    ("hod of first year", "Kalavathi"),
    ("first year hod", "Kalavathi"),
    ("who is hod of 1st year", "Kalavathi"),
    ("mathematics hod", "Mohana"),
    ("maths hod", "Mohana"),
    ("hod of mathematics department", "Mohana"),
    ("mca hod", "Margaret"),
    ("mca faculty", 5),
    ("faculty of mca", 5),
    ("faculty of cads", 7),
    ("decs faculty", 7),
    ("power and energy systems faculty", 2),
    ("ai and ds faculty", 2),
    ("mtech faculty", 18),
    ("faculty of ise", 14),
    ("hod of chemistry", "Krishnakumar"),
    ("hod of physics", "Prasanna"),
    ("mba faculty", "not listed"),
]

all_passed = True
print("=" * 80)
print(" RUNNING COMPREHENSIVE HOD & FACULTY LOOKUP TESTS")
print("=" * 80)

for q, expected in test_queries:
    res = faculty_lookup.lookup_faculty(q)
    status = res.get("status")
    if isinstance(expected, int):
        fac = res.get("faculty_list", [])
        ok = (len(fac) == expected)
        res_str = "PASS" if ok else "FAIL"
        if not ok: all_passed = False
        print(f"{q:42} -> count={len(fac):2} (expected {expected:2}) -> {res_str}")
    else:
        msg = res.get("message", "")
        ok = (expected.lower() in msg.lower())
        res_str = "PASS" if ok else "FAIL"
        if not ok: all_passed = False
        print(f"{q:42} -> status={status:10} (expected '{expected}') -> {res_str}")
        if not ok:
            print(f"  OUTPUT: {msg[:140]}")

print("=" * 80)
print("OVERALL RESULT:", "ALL PASSED (100%)" if all_passed else "SOME TESTS FAILED")
print("=" * 80)

