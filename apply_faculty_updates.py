import json
import shutil
from pathlib import Path

# 1. Update hod_verified.json
hod_path = Path("hod_verified.json")
with open(hod_path, "r", encoding="utf-8") as f:
    hod_data = json.load(f)

hod_data["CSE"] = {
    "dept_code": "CSE",
    "canonical_name": "Computer Science and Engineering",
    "hod_name": "Dr. Ananda Babu J",
    "designation": "Professor and Head of Department (HOD)",
    "qualification": "B.E., M.Tech., Ph.D.",
    "specialization": "Computer Science & Engineering / Information Science",
    "email": "gabj@mcehassan.ac.in",
    "phone": "9844081383",
    "photo_path": r"D:\MINI Project\faculty_photos_new\ise_ananda_babu_j.jpg",
    "source_file": "hod s of college.pdf",
    "source_page": 1,
    "status": "verified"
}

with open(hod_path, "w", encoding="utf-8") as f:
    json.dump(hod_data, f, indent=2, ensure_ascii=False)
print("Updated hod_verified.json: CSE HOD is now Dr. Ananda Babu J")

# 2. Update placeholder photos for EEE faculty with broken/missing source images
photos_dir = Path(r"D:\MINI Project\faculty_photos_new")
assets_dir = Path("assets/faculty")
placeholder_path = photos_dir / "placeholder_avatar.jpg"

if placeholder_path.exists():
    for fname in ["elec_k_mohan.jpg", "elec_prathima_h_v.jpg", "elec_pramodh_h_k.jpg", "elec_suchithra_m_m.jpg", "mrs_prathima_h_v.jpg"]:
        dest1 = photos_dir / fname
        shutil.copy2(placeholder_path, dest1)
        if assets_dir.exists():
            dest2 = assets_dir / fname
            shutil.copy2(placeholder_path, dest2)
    print("Replaced broken EEE photos with placeholder avatar")

# 3. Update faculty_profiles_new.json
profs_path = Path("faculty_profiles_new.json")
with open(profs_path, "r", encoding="utf-8") as f:
    profiles = json.load(f)

new_profiles = []
has_ananda_cse = False

for p in profiles:
    p_name = p.get("name", "")
    p_dept = p.get("department", "")

    # Dr. Chandrika.J is Professor, NOT HOD
    if "chandrika" in p_name.lower() and "computer" in p_dept.lower():
        p["designation"] = "Professor"
        p["specialization"] = "Computer Science & Engineering"
        p["other_details"] = ""

    # Dr. Balaji Prabhu B V is CSE faculty and part of AIDS
    if "balaji" in p_name.lower() and "prabhu" in p_name.lower():
        p["department"] = "Computer Science and Engineering"
        p["department_code"] = "CSE"
        p["parent_department"] = "Department of Computer Science and Engineering"
        p["designation"] = "Assistant Professor"
        p["qualification"] = "Ph.D., PostDoc (IISc.)"
        p["specialization"] = "Artificial Intelligence & Data Science"
        p["other_details"] = "Faculty member in Computer Science & Engineering, also part of the Department of Artificial Intelligence and Data Science (AIDS)."
        p["email"] = "bvb@mcehassan.ac.in"
        p["photo_path"] = r"D:\MINI Project\faculty_photos_new\dr_balaji_prabhu_b_v.jpg"

    # Dr. Ananda Babu J in CSE
    if "ananda" in p_name.lower() and "babu" in p_name.lower() and "computer" in p_dept.lower():
        has_ananda_cse = True
        p["designation"] = "Professor and Head of Department (HOD)"
        p["specialization"] = "Computer Science & Engineering / Information Science"

    # EEE broken photos -> placeholder
    if any(k.lower() in p_name.lower() for k in ["k mohan", "prathima h", "pramodh h", "suchithra m"]):
        if "electrical" in p_dept.lower():
            p["photo_path"] = str(placeholder_path)

    new_profiles.append(p)

if not has_ananda_cse:
    new_profiles.insert(0, {
        "id": "anandababuj_computerscienceandengineering",
        "name": "Dr. Ananda Babu J",
        "normalized_name": "anandababuj",
        "designation": "Professor and Head of Department (HOD)",
        "department": "Computer Science and Engineering",
        "department_code": "CSE",
        "parent_department": "Department of Computer Science and Engineering",
        "qualification": "B.E., M.Tech., Ph.D.",
        "experience": "",
        "specialization": "Computer Science & Engineering / Information Science",
        "email": "gabj@mcehassan.ac.in",
        "phone": "9844081383",
        "photo_path": r"D:\MINI Project\faculty_photos_new\ise_ananda_babu_j.jpg",
        "source_file": "hod s of college.pdf",
        "page": 1
    })
    print("Added Dr. Ananda Babu J as CSE HOD to faculty_profiles_new.json")

with open(profs_path, "w", encoding="utf-8") as f:
    json.dump(new_profiles, f, indent=2, ensure_ascii=False)

print(f"Updated faculty_profiles_new.json, total profiles: {len(new_profiles)}")

