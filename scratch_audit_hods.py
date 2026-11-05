import json
from pathlib import Path

with open("hod_verified.json", "r", encoding="utf-8") as f:
    hods = json.load(f)

with open("faculty_profiles_new.json", "r", encoding="utf-8") as f:
    profiles = json.load(f)

prof_by_name = {}
for p in profiles:
    name_clean = p.get("name", "").lower().replace(".", "").replace(" ", "")
    prof_by_name[name_clean] = p

print("=" * 110)
print(f"{'Dept Code':<10} | {'HOD Name':<25} | {'Person Own Dept':<30} | {'Photo Exists':<12} | {'Email':<25}")
print("=" * 110)

for code, d in hods.items():
    hod_name = d.get("hod_name", "N/A")
    name_clean = hod_name.lower().replace(".", "").replace(" ", "")
    person = prof_by_name.get(name_clean)
    person_dept = person.get("department", "NOT IN PROFILES") if person else "NOT IN PROFILES"
    photo_path = d.get("photo_path", "")
    photo_exists = Path(photo_path).exists() if photo_path else False
    email = d.get("email", "N/A")
    print(f"{code:<10} | {hod_name:<25} | {person_dept:<30} | {str(photo_exists):<12} | {email:<25}")

print("=" * 110)

