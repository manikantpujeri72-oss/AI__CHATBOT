import json

with open("faculty_profiles_new.json", "r", encoding="utf-8") as f:
    profiles = json.load(f)

print(f"Total profiles in faculty_profiles_new.json: {len(profiles)}")

depts = {}
for p in profiles:
    d = p.get("department", "Unknown")
    depts[d] = depts.get(d, 0) + 1

for d, count in sorted(depts.items()):
    print(f"  {d}: {count} profiles")

