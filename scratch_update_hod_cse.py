import json
from pathlib import Path

# 1. Update hod_verified.json
hod_path = Path("hod_verified.json")
with open(hod_path, "r", encoding="utf-8") as f:
    hod_data = json.load(f)

hod_data["CSE"] = {
    "dept_code": "CSE",
    "canonical_name": "Computer Science and Engineering",
    "hod_name": "Dr. Chandrika.J",
    "designation": "Professor and Head of Department (HOD)",
    "qualification": "B.E., M.Tech., Ph.D.",
    "specialization": "Computer Science & Engineering",
    "email": "cj@mcehassan.ac.in",
    "phone": "9448871082",
    "photo_path": r"D:\MINI Project\faculty_photos_new\dr_chandrikaj.jpg",
    "source_file": "all department faculty.pdf",
    "source_page": 31,
    "status": "verified"
}

with open(hod_path, "w", encoding="utf-8") as f:
    json.dump(hod_data, f, indent=2, ensure_ascii=False)
print("Updated hod_verified.json for CSE -> Dr. Chandrika.J")

# 2. Update faculty_profiles_new.json
profs_path = Path("faculty_profiles_new.json")
with open(profs_path, "r", encoding="utf-8") as f:
    profiles = json.load(f)

new_profiles = []
removed_duplicate = 0
updated_chandrika = 0

for p in profiles:
    # If Dr. Ananda Babu J in CSE, remove duplicate
    if "ananda" in p.get("name", "").lower() and "babu" in p.get("name", "").lower():
        if p.get("department") == "Computer Science and Engineering":
            removed_duplicate += 1
            continue
    # Update Dr. Chandrika.J
    if "chandrika" in p.get("name", "").lower() and p.get("department") == "Computer Science and Engineering":
        p["designation"] = "Professor and Head of Department (HOD)"
        p["specialization"] = "Computer Science & Engineering"
        updated_chandrika += 1
    new_profiles.append(p)

with open(profs_path, "w", encoding="utf-8") as f:
    json.dump(new_profiles, f, indent=2, ensure_ascii=False)

print(f"Updated faculty_profiles_new.json: removed {removed_duplicate} duplicate(s), updated {updated_chandrika} Chandrika profile, total profiles: {len(new_profiles)}")

