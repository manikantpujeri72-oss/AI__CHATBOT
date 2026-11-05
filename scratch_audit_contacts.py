import json
import re

with open("hod_verified.json", "r", encoding="utf-8") as f:
    hods = json.load(f)

with open("faculty_profiles_new.json", "r", encoding="utf-8") as f:
    profiles = json.load(f)

print("--- AUDITING HOD CONTACTS ---")
for code, d in hods.items():
    name = d.get("hod_name", "N/A")
    email = d.get("email", "")
    phone = d.get("phone", "")
    
    suspicious = []
    if email:
        if any(bad in email.lower() for bad in ["abc@", "test@", "xxx", "example"]):
            suspicious.append(f"email '{email}' looks like initials/placeholder")
    if phone:
        if phone in ["0000000000", "1234567890"] or re.match(r"^(\d)\1{9}$", phone):
            suspicious.append(f"phone '{phone}' has repeated digits")
    if suspicious:
        print(f"HOD {code} ({name}): {', '.join(suspicious)} | source: {d.get('source_file')} p.{d.get('source_page')}")

print("\n--- AUDITING ALL FACULTY PROFILES CONTACTS ---")
flagged_profs = []
for p in profiles:
    name = p.get("name", "N/A")
    dept = p.get("department", "N/A")
    email = p.get("email", "")
    phone = p.get("phone", "")
    suspicious = []
    if email:
        if any(bad in email.lower() for bad in ["abc@", "test@", "xxx", "example", "placeholder"]):
            suspicious.append(f"email '{email}'")
    if phone:
        if phone in ["0000000000", "1234567890"] or re.match(r"^(\d)\1{9}$", phone):
            suspicious.append(f"phone '{phone}'")
    if suspicious:
        flagged_profs.append((name, dept, ", ".join(suspicious)))

print(f"Total flagged faculty: {len(flagged_profs)}")
for name, dept, reasons in flagged_profs:
    print(f"  {name} ({dept}): {reasons}")

