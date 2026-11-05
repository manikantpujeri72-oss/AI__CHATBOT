import os
import sys

# Ensure DEBUG_ROUTING is enabled
import source_config
source_config.DEBUG_ROUTING = True

import short_forms
import faculty_lookup
import hybrid_rag
import rag

client = rag.get_cohere_client()

queries = [
    "hi",
    "overview of ise department",
    "overview of cse department'",
    "tell me about mathematics department",
    "fee structure",
    "clubs at mce",
    "overview of aiml department",
]

print("=" * 80)
print("REPRODUCING 6 (7) BUGS")
print("=" * 80)

for q in queries:
    print(f"\n>>> QUERY: {repr(q)}")
    # 1. Resolve department directly
    dept_code, canonical, score = short_forms.resolve_department(q)
    print(f"  [short_forms.resolve_department] -> code: {dept_code}, canonical: {canonical}, score: {score}")

    # 2. Classify intent
    intent, d_code, person_name = faculty_lookup.classify_intent(q)
    print(f"  [faculty_lookup.classify_intent] -> intent: {intent}, dept_code: {d_code}, person_name: {person_name}")

    # 3. Faculty lookup check
    fac_res = faculty_lookup.lookup_faculty(q)
    print(f"  [faculty_lookup.lookup_faculty] -> handled: {fac_res.get('handled')}, status: {fac_res.get('status')}")
    if fac_res.get("handled"):
        print(f"    person: {fac_res.get('person', {}).get('name') if fac_res.get('person') else None}")
        print(f"    message snippet: {repr(fac_res.get('message', '')[:120])}")

    # 4. hybrid_rag.ask
    try:
        ans, hits, meta = hybrid_rag.ask(client, q)
        print(f"  [hybrid_rag.ask] -> meta: {meta}")
        print(f"    hits count: {len(hits)}")
        print(f"    answer snippet: {repr(ans[:200])}")
        if not ans.strip():
            print("    *** WARNING: ANSWER IS EMPTY/BLANK! ***")
    except Exception as exc:
        print(f"  [hybrid_rag.ask] -> EXCEPTION: {exc}")

print("\n" + "=" * 80)
print("REPRODUCTION RUN COMPLETE")
print("=" * 80)

