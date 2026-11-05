import hybrid_rag
import rag
import faculty_lookup
import ui_cards

# Reset caches
faculty_lookup._PROFILES_CACHE = None
ui_cards._PHOTO_BYTES_CACHE.clear()

cohere_client, coll = rag.get_cohere_client(), rag.get_collection()

test_cases = [
    ("balaji prabhu", "Dr. Balaji Prabhu B V", "Computer Science and Engineering", "AIDS"),
    ("cse hod", "Dr. Ananda Babu J", "Computer Science and Engineering", "HOD"),
    ("overview of cse department", "Dr. Ananda Babu J", "Computer Science and Engineering", "About"),
    ("faculty of cse", "Dr. Ananda Babu J", "Dr. Balaji Prabhu B V", "27 faculty"),
    ("faculty of aids", "Dr. Balaji Prabhu B V", "Artificial Intelligence and Data Science", "faculty"),
    ("admission contact details", "08172-268371", "office@mcehassan.ac.in", "Admission"),
    ("eligibility criteria for admission", "45% aggregate", "40%", "KCET"),
    ("Fee structure", "Rs. 2,50,000", "Rs. 1,25,000", "Tuition Fees"),
    ("K MOHAN", "G K MOHAN", "Electrical and Electronics Engineering", "elec_k_mohan.jpg"),
    ("Mrs. Prathima H .V.", "Mrs. Prathima H .V.", "Electrical and Electronics Engineering", "elec_prathima_h_v.jpg"),
    ("PRAMODH H. K.", "PRAMODH H. K.", "Electrical and Electronics Engineering", "elec_pramodh_h_k.jpg"),
]

print("=" * 60)
print("RUNNING COMPREHENSIVE VERIFICATION WITH AUTHENTIC USER PHOTOS")
print("=" * 60)

passed = 0
failed = 0

for item in test_cases:
    query = item[0]
    expected_keywords = item[1:]
    print(f"\n[TEST QUERY]: '{query}'")

    gen, hits, meta = hybrid_rag.ask_stream(cohere_client, query, [])
    full_text = "".join(list(gen))
    if not full_text and meta.get("message"):
        full_text = meta.get("message")
    if meta.get("person"):
        p = meta["person"]
        full_text += f"\nPERSON: {p.get('name')} | Dept: {p.get('department')} | Desig: {p.get('designation')} | Photo: {p.get('photo_path')} | Details: {p.get('other_details')}"
    if meta.get("overview_markdown"):
        full_text += f"\nOVERVIEW: {meta.get('overview_markdown')}"

    missing = [kw for kw in expected_keywords if kw.lower() not in full_text.lower()]
    if not missing:
        print(f"  PASS: found all {expected_keywords}")
        passed += 1
    else:
        print(f"  FAIL: missing keywords {missing}")
        print(f"  Preview: {full_text[:300]}")
        failed += 1

print("\n" + "=" * 60)
print(f"RESULTS: {passed} PASSED, {failed} FAILED (TOTAL {len(test_cases)})")
print("=" * 60)

# Check Chroma count
assert coll.count() == 83, f"mce_docs count altered! {coll.count()}"
print("SAFETY CHECK: mce_docs count strictly 83! Verified.")
