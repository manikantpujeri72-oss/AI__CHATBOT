import json

with open("faculty_profiles_new.json", "r", encoding="utf-8") as f:
    profiles = json.load(f)

print("--- Mechanical Engineering Faculty with HOD or Professor ---")
for p in profiles:
    if "mechanical" in p.get("department", "").lower():
        desig = p.get("designation", "").lower()
        if "hod" in desig or "head" in desig or "professor" in desig or "pradeep" in p.get("name", "").lower():
            print(f"Name: {p.get('name')}, Desig: {p.get('designation')}, Dept: {p.get('department')}, Email: {p.get('email')}, Phone: {p.get('phone')}")

