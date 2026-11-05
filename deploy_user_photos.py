import json
import shutil
from pathlib import Path

# 1. Copy photos to faculty_photos_new and assets/faculty
src_dir = Path(r"D:\MINI Project\scratch_user_crops")
dest_dir1 = Path(r"D:\MINI Project\faculty_photos_new")
dest_dir2 = Path("assets/faculty")

mapping = {
    "elec_k_mohan.jpg": ["elec_k_mohan.jpg", "k_mohan.jpg", "gk_mohan.jpg"],
    "elec_pramodh_h_k.jpg": ["elec_pramodh_h_k.jpg", "pramodh_h_k.jpg"],
    "elec_prathima_h_v.jpg": ["elec_prathima_h_v.jpg", "prathima_h_v.jpg", "mrs_prathima_h_v.jpg"],
    "elec_suchithra_m_m.jpg": ["elec_suchithra_m_m.jpg", "suchithra_m_m.jpg"],
}

for src_name, dest_names in mapping.items():
    src_file = src_dir / src_name
    if src_file.exists():
        for dname in dest_names:
            shutil.copy2(src_file, dest_dir1 / dname)
            if dest_dir2.exists():
                shutil.copy2(src_file, dest_dir2 / dname)
        print(f"Deployed {src_name} -> {dest_names}")

# 2. Update faculty_profiles_new.json
profs_path = Path("faculty_profiles_new.json")
with open(profs_path, "r", encoding="utf-8") as f:
    profiles = json.load(f)

for p in profiles:
    p_name = p.get("name", "")
    p_dept = p.get("department", "")

    if "electrical" in p_dept.lower():
        # G K Mohan
        if "mohan" in p_name.lower() and "lakshmi" not in p_name.lower():
            p["name"] = "G K MOHAN"
            p["normalized_name"] = "gkmohan"
            p["email"] = "mgk@mcehassan.ac.in"
            p["phone"] = "8317462582"
            p["qualification"] = "B.E., M.Tech."
            p["photo_path"] = str(dest_dir1 / "elec_k_mohan.jpg")
            p["faculty_id"] = "1-44069644422"

        # Pramodh H. K.
        if "pramodh" in p_name.lower():
            p["name"] = "PRAMODH H. K."
            p["normalized_name"] = "pramodhhk"
            p["email"] = "phk@mcehassan.ac.in"
            p["phone"] = "9036285929"
            p["qualification"] = "B.E., M.E"
            p["photo_path"] = str(dest_dir1 / "elec_pramodh_h_k.jpg")
            p["faculty_id"] = "1-1506628983"

        # Mrs. Prathima H .V.
        if "prathima" in p_name.lower():
            p["name"] = "Mrs. Prathima H .V."
            p["normalized_name"] = "prathimahv"
            p["email"] = "phv@mcehassan.ac.in"
            p["phone"] = "9036868991"
            p["qualification"] = "B.E., M.Tech. (Ph.D)"
            p["photo_path"] = str(dest_dir1 / "elec_prathima_h_v.jpg")
            p["faculty_id"] = "1-43805213684"

        # Suchithra M. M.
        if "suchithra" in p_name.lower():
            p["name"] = "Suchithra M. M."
            p["normalized_name"] = "suchithramm"
            p["email"] = "ms@mcehassan.ac.in"
            p["phone"] = "9008916293"
            p["qualification"] = "B.E., M.Tech."
            p["photo_path"] = str(dest_dir1 / "elec_suchithra_m_m.jpg")
            p["faculty_id"] = "1-43365869784"

with open(profs_path, "w", encoding="utf-8") as f:
    json.dump(profiles, f, indent=2, ensure_ascii=False)

print("Updated faculty_profiles_new.json with authentic user photos and details.")

