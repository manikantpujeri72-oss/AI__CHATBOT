import json

with open("hod_verified.json", "r", encoding="utf-8") as f:
    hods = json.load(f)

with open("faculty_profiles_new.json", "r", encoding="utf-8") as f:
    profiles = json.load(f)

# Update CSE in hods
hods["CSE"] = {
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

# Update Dr. Chandrika.J in profiles to Professor and Head of Department (HOD)
for p in profiles:
    if "chandrika" in p.get("name", "").lower():
        p["designation"] = "Professor and Head of Department (HOD)"

# Ensure Dr. Arjun B C has department AIML in profiles or profile exists for AIML
for p in profiles:
    if "arjun" in p.get("name", "").lower():
        print("Arjun profile dept:", p.get("department"))

# Ensure Dr. Kalavathi G K has First-Year Department
for p in profiles:
    if "kalavathi" in p.get("name", "").lower():
        print("Kalavathi profile dept:", p.get("department"))

