import faculty_lookup

# Clear cache
faculty_lookup._PROFILES_CACHE = None

test_queries = [
    # Section 6 mandatory queries
    "Who is the First-Year HOD?",
    "Who is the Mathematics HOD?",
    "Who is the CSE HOD?",
    "Who heads the Computer Science and Engineering Department?",
    "Tell me about the CSE HOD.",
    "Who is the MCA HOD?",
    "Tell me about MCA faculty.",
    "Tell me about Dr. Santosh Kumar K.B.",
    "What is the qualification of First-Year HOD?",
    "What is the contact number of Dr. Santosh Kumar K.B.?",
    # Previous HOD & PG regressions
    "Who is the HOD of ise?",
    "Who is the HOD of eee?",
    "Who is the HOD of civil?",
    "Who is the HOD of eie?",
    "Tell me about CADS faculty.",
    "Tell me about DECS faculty.",
    "Tell me about PES faculty.",
    "Tell me about AIDS faculty.",
]

for q in test_queries:
    res = faculty_lookup.lookup_faculty(q)
    print("=" * 60)
    print(f"QUERY: {q}")
    print(f"HANDLED: {res.get('handled')}, STATUS: {res.get('status')}, TYPE: {res.get('type')}")
    if res.get("person"):
        p = res["person"]
        print(f"PERSON: {p.get('name')} | {p.get('department')} | {p.get('designation')}")
        print(f"PHOTO: {p.get('photo_path')}")
        print(f"QUALIFICATION: {p.get('qualification')}")
        print(f"SHOW PHONE: {res.get('show_phone')}")
    if res.get("faculty_list"):
        fac_names = [f["name"] for f in res["faculty_list"]]
        print(f"FACULTY LIST ({len(fac_names)}): {fac_names}")
