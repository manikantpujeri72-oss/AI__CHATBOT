"""Authoritative HOD Manager for Malnad College of Engineering (MCE).

Provides single-source-of-truth HOD records verified against official college documents:
- 'hod s of college.pdf'
- 'overview of mce.pdf'
- 'about first year department.pdf'
- Department Faculty PDFs
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HOD_VERIFIED_PATH = Path(__file__).resolve().parent / "hod_verified.json"
PHOTOS_DIR = Path("D:/MINI Project/faculty_photos_new")
PLACEHOLDER_PATH = Path(__file__).resolve().parent / "assets" / "faculty" / "avatar_placeholder.png"

# Official, verified HOD master data grounded in college documents
VERIFIED_HOD_DATA: dict[str, dict[str, Any]] = {
    "ISE": {
        "dept_code": "ISE",
        "canonical_name": "Information Science and Engineering",
        "hod_name": "Dr. Ananda Babu J",
        "designation": "Professor and Head of Department (HOD)",
        "qualification": "B.E., M.Tech., Ph.D.",
        "specialization": "Information Science",
        "email": "gabj@mcehassan.ac.in",
        "phone": "9844081383",
        "photo_path": str(PHOTOS_DIR / "ise_ananda_babu_j.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 1,
        "status": "verified",
    },
    "EEE": {
        "dept_code": "EEE",
        "canonical_name": "Electrical and Electronics Engineering",
        "hod_name": "Dr. Rajanna S.",
        "designation": "Professor and Head of Department (HOD)",
        "qualification": "B.E., M.Tech., Ph.D. (IIT Roorkee)",
        "specialization": "Electrical & Electronics Engineering",
        "email": "gsr@mcehassan.ac.in",
        "phone": "8791340700",
        "photo_path": str(PHOTOS_DIR / "dr_rajanna_s.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 2,
        "status": "verified",
    },
    "CIVIL": {
        "dept_code": "CIVIL",
        "canonical_name": "Civil Engineering",
        "hod_name": "Dr. Sumana Jayaprakash",
        "designation": "Associate Professor and Head of Department (HOD)",
        "qualification": "Ph.D.",
        "specialization": "Civil Engineering",
        "email": "sj@mcehassan.ac.in",
        "phone": "9449888177",
        "photo_path": str(PHOTOS_DIR / "dr_sumana_jayaprakash.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 2,
        "status": "verified",
    },
    "EIE": {
        "dept_code": "EIE",
        "canonical_name": "Electronics and Instrumentation Engineering",
        "hod_name": "Dr. C M Naveen Kumar",
        "designation": "Associate Professor and Head of Department (HOD)",
        "qualification": "B.E. (IT), M.Tech. (CSE), Ph.D., Ing.Paed.IGIP",
        "specialization": "Electronics & Instrumentation Engineering",
        "email": "gcmn@mcehassan.ac.in",
        "phone": "9902128829",
        "photo_path": str(PHOTOS_DIR / "dr_c_m_naveen_kumar_associate_professor_and_hod_faculty_id.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 3,
        "status": "verified",
    },
    "FIRST_YEAR": {
        "dept_code": "FIRST_YEAR",
        "canonical_name": "First-Year Department",
        "hod_name": "Dr. Kalavathi G K",
        "designation": "Professor and Head of Department (HOD)",
        "qualification": "M.Sc., M.Phil., Ph.D.",
        "specialization": "Applied Mathematics, Fluid Mechanics",
        "email": "gkk@mcehassan.ac.in",
        "phone": "9844241717",
        "photo_path": str(PHOTOS_DIR / "math_dr_kalavathi_g_k.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 4,
        "status": "verified",
    },
    "MATH": {
        "dept_code": "MATH",
        "canonical_name": "Department of Mathematics",
        "hod_name": "T Mohana",
        "designation": "Associate Professor and Head of Department (HOD)",
        "qualification": "M.Sc.",
        "specialization": "Mathematics",
        "email": "tm@mcehassan.ac.in",
        "phone": "8618648617",
        "photo_path": str(PHOTOS_DIR / "math_t_mohana.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 4,
        "status": "verified",
    },
    "CSE": {
        "dept_code": "CSE",
        "canonical_name": "Computer Science and Engineering",
        "hod_name": "Dr. Ananda Babu J",
        "designation": "Professor and Head of Department (HOD)",
        "qualification": "B.E., M.Tech., Ph.D.",
        "specialization": "Computer Science & Engineering",
        "email": "gabj@mcehassan.ac.in",
        "phone": "9844081383",
        "photo_path": str(PHOTOS_DIR / "ise_ananda_babu_j.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 1,
        "status": "verified",
    },
    "MECH": {
        "dept_code": "MECH",
        "canonical_name": "Mechanical Engineering",
        "hod_name": "Dr. Ezhil Vannan S",
        "designation": "Professor and Head of Department (HOD)",
        "qualification": "B.E., M.E., Ph.D.",
        "specialization": "Mechanical Engineering",
        "email": "gevs@mcehassan.ac.in",
        "phone": "9845575450",
        "photo_path": str(PHOTOS_DIR / "dr_ezhil_vannan_s.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 1,
        "status": "verified",
    },
    "ECE": {
        "dept_code": "ECE",
        "canonical_name": "Electronics and Communication Engineering",
        "hod_name": "Dr. Murthi Mahadeva Naik G",
        "designation": "Professor and Head of Department (HOD)",
        "qualification": "B.E., M.Tech, Ph.D.",
        "specialization": "Electronics & Communication Engineering",
        "email": "gmmn@mcehassan.ac.in",
        "phone": "9482522918",
        "photo_path": str(PHOTOS_DIR / "dr_murthi_mahadeva_naik_g.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 2,
        "status": "verified",
    },
    "AIML": {
        "dept_code": "AIML",
        "canonical_name": "Artificial Intelligence and Machine Learning",
        "hod_name": "Dr. Arjun B C",
        "designation": "Professor and Head of Department (HOD)",
        "qualification": "B.E., M.Tech., Ph.D.",
        "specialization": "Artificial Intelligence & Machine Learning",
        "email": "abc@mcehassan.ac.in",
        "phone": "9844584208",
        "photo_path": str(PHOTOS_DIR / "dr_arjun_b_c.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 3,
        "status": "verified",
    },
    "CSBS": {
        "dept_code": "CSBS",
        "canonical_name": "Computer Science and Business Systems",
        "hod_name": "Dr. Naveen Kumar C M",
        "designation": "Associate Professor and Head of Department (HOD)",
        "qualification": "B.E (IT), M.Tech (CSE), Ph.D., Ing.Paed.IGIP",
        "specialization": "Computer Science & Business Systems",
        "email": "gcmn@mcehassan.ac.in",
        "phone": "9902128829",
        "photo_path": str(PHOTOS_DIR / "dr_naveen_kumar_c_m.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 2,
        "status": "verified",
    },
    "VLSI": {
        "dept_code": "VLSI",
        "canonical_name": "VLSI Design and Technology",
        "hod_name": "Dr. Hemanth Kumar B M",
        "designation": "Associate Professor and Head of Department (HOD)",
        "qualification": "BE, M.Tech, PhD",
        "specialization": "VLSI Design and Technology",
        "email": "bmh@mcehassan.ac.in",
        "phone": "7829150029",
        "photo_path": str(PHOTOS_DIR / "dr_hemanth_kumar_b_m.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 3,
        "status": "verified",
    },
    "MCA": {
        "dept_code": "MCA",
        "canonical_name": "Master of Computer Applications",
        "hod_name": "Mrs. Margaret R.E.",
        "designation": "Assistant Professor and Head of Department (HOD)",
        "qualification": "MCA",
        "specialization": "Computer Applications",
        "email": "rem@mcehassan.ac.in",
        "phone": "9448006138",
        "photo_path": str(PHOTOS_DIR / "mrs_margaret_re.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 3,
        "status": "verified",
    },
    "CHEM": {
        "dept_code": "CHEM",
        "canonical_name": "Department of Chemistry",
        "hod_name": "Mr. K. N. Krishnakumar",
        "designation": "Associate Professor and Head of Department (HOD)",
        "qualification": "M.Sc.",
        "specialization": "Chemistry",
        "email": "knk@mcehassan.ac.in",
        "phone": "9480264142",
        "photo_path": str(PHOTOS_DIR / "chemistry_mr_k_n_krishnakumar.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 5,
        "status": "verified",
    },
    "PHY": {
        "dept_code": "PHY",
        "canonical_name": "Department of Physics",
        "hod_name": "Dr. Prasanna A. A.",
        "designation": "Professor and Head of Department (HOD)",
        "qualification": "M.Sc., Ph.D.",
        "specialization": "Physics",
        "email": "aap@mcehassan.ac.in",
        "phone": "9535004515",
        "photo_path": str(PHOTOS_DIR / "physics_dr_prasanna_a_a.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 5,
        "status": "verified",
    },
    "RAI": {
        "dept_code": "RAI",
        "canonical_name": "Robotics and Artificial Intelligence",
        "hod_name": "Dr. Arjun B C",
        "designation": "Professor and Head of Department (HOD)",
        "qualification": "B.E., M.Tech., Ph.D.",
        "specialization": "Robotics & Artificial Intelligence",
        "email": "abc@mcehassan.ac.in",
        "phone": "9844584208",
        "photo_path": str(PHOTOS_DIR / "dr_arjun_b_c.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 4,
        "status": "verified",
    },
    "DECS": {
        "dept_code": "DECS",
        "canonical_name": "Digital Electronics and Communication Systems",
        "hod_name": "Dr. Padmaja Devi G",
        "designation": "Professor and Head of Department (HOD)",
        "qualification": "B.E., M.Tech, Ph.D.",
        "specialization": "Digital Electronics & Communication Systems",
        "email": "gpd@mcehassan.ac.in",
        "phone": "9164539950",
        "photo_path": str(PHOTOS_DIR / "dr_padmaja_devi_g_professor_and_hod_be.jpg"),
        "source_file": "hod s of college.pdf",
        "source_page": 4,
        "is_pg_program": True,
        "parent_department": "Electronics and Communication Engineering",
        "status": "verified",
    },
    "CADS": {
        "dept_code": "CADS",
        "canonical_name": "Computer Aided Design of Structures",
        "hod_name": "Dr. Manu K.C",
        "designation": "Associate Professor and PG Coordinator",
        "qualification": "B.E., M.Tech., Ph.D.",
        "specialization": "Structural Engineering / CADS",
        "email": "kcm@mcehassan.ac.in",
        "phone": "9964246092",
        "photo_path": str(PHOTOS_DIR / "civi_k_c_manu.jpg"),
        "source_file": "overview of mce.pdf",
        "source_page": 9,
        "is_pg_program": True,
        "parent_department": "Civil Engineering",
        "status": "verified",
    },
    "PES": {
        "dept_code": "PES",
        "canonical_name": "Power and Energy Systems",
        "hod_name": "Dr. S. Rajanna",
        "designation": "Professor and Head of Department (HOD)",
        "qualification": "B.E., M.Tech., Ph.D. (IIT Roorkee)",
        "specialization": "Power and Energy Systems",
        "email": "gsr@mcehassan.ac.in",
        "phone": "8791340700",
        "photo_path": str(PHOTOS_DIR / "dr_rajanna_s.jpg"),
        "source_file": "all department faculty.pdf",
        "source_page": 93,
        "is_pg_program": True,
        "parent_department": "Electrical and Electronics Engineering",
        "status": "verified",
    },
    "AIDS": {
        "dept_code": "AIDS",
        "canonical_name": "Artificial Intelligence and Data Science",
        "hod_name": "Dr. Keerthi Kumar H.M.",
        "designation": "Associate Professor and PG Coordinator",
        "qualification": "B.E., M.Tech., Ph.D.",
        "specialization": "Artificial Intelligence & Data Science",
        "email": "hsk@mcehassan.ac.in",
        "phone": "",
        "photo_path": str(PHOTOS_DIR / "dr_keerthi_kumar_h_m.jpg"),
        "source_file": "overview of mce.pdf",
        "source_page": 9,
        "is_pg_program": True,
        "parent_department": "Computer Science and Engineering",
        "status": "verified",
    },
    "MBA": {
        "dept_code": "MBA",
        "canonical_name": "Master of Business Administration",
        "hod_name": None,
        "designation": None,
        "qualification": None,
        "specialization": None,
        "email": None,
        "phone": None,
        "photo_path": None,
        "source_file": "overview of mce.pdf",
        "source_page": 1,
        "status": "not_offered",
        "message": "Faculty details for Master of Business Administration (MBA) are not listed in the documents because MCE Hassan does not offer an MBA program.",
    },
}


def save_hod_verified() -> None:
    """Save verified HOD records to hod_verified.json."""
    with open(HOD_VERIFIED_PATH, "w", encoding="utf-8") as f:
        json.dump(VERIFIED_HOD_DATA, f, indent=2, ensure_ascii=False)


def load_hod_verified() -> dict[str, dict[str, Any]]:
    """Load verified HOD records from hod_verified.json."""
    if not HOD_VERIFIED_PATH.exists():
        save_hod_verified()
    with open(HOD_VERIFIED_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_verified_hod(dept_code: str) -> dict[str, Any] | None:
    """Retrieve verified HOD for a canonical department code."""
    data = load_hod_verified()
    code_up = dept_code.upper().strip()
    return data.get(code_up)


def audit_hod_data(profiles: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Audit HOD records against profile database and photo disk existence."""
    from pathlib import Path
    data = load_hod_verified()
    audit_rows = []

    for code, entry in data.items():
        if entry.get("status") == "not_offered":
            audit_rows.append({
                "dept_code": code,
                "department": entry["canonical_name"],
                "hod_name": "Not Offered at MCE",
                "designation": "N/A",
                "source": f"{entry['source_file']} (p. {entry['source_page']})",
                "photo_ok": "N/A",
                "profile_matched": "N/A (Program not offered)",
            })
            continue

        p_path = entry.get("photo_path")
        photo_exists = bool(p_path and Path(p_path).exists())

        matched = False
        if profiles:
            h_name = entry["hod_name"].lower()
            for p in profiles:
                if h_name in p.get("name", "").lower() or p.get("name", "").lower() in h_name:
                    matched = True
                    break

        audit_rows.append({
            "dept_code": code,
            "department": entry["canonical_name"],
            "hod_name": entry["hod_name"],
            "designation": entry["designation"],
            "source": f"{entry['source_file']} (p. {entry['source_page']})",
            "photo_ok": "YES" if photo_exists else "MISSING",
            "profile_matched": "YES" if matched else ("NO" if profiles else "UNCHECKED"),
        })

    return audit_rows


if __name__ == "__main__":
    save_hod_verified()
    print(f"Successfully generated {HOD_VERIFIED_PATH} with {len(VERIFIED_HOD_DATA)} departments.")

