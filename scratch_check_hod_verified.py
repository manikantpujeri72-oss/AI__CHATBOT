import json

# Let's inspect hod_verified.json to see what it currently has for all departments
with open("hod_verified.json", "r", encoding="utf-8") as f:
    h = json.load(f)

for code, d in h.items():
    print(f"CODE: {code:10} | HOD: {d.get('hod_name'):25} | Dept: {d.get('canonical_name')}")

