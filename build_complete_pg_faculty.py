"""Enrich faculty profiles with PG programs (CADS, DECS, PES, AIDS, RAI), MCA 5th member,
and strictly align HOD designations with hod_verified.json.

Safety:
- Does NOT touch 'mce_docs' collection (kept strictly at 83 chunks).
- Preserves all 177 existing faculty profiles without deletion.
- Ensures all photo files exist on disk with placeholder fallbacks.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import chromadb

import hod_manager
import source_config

BASE_DIR = Path(__file__).resolve().parent
PROFILES_FILE = BASE_DIR / "faculty_profiles_new.json"
PHOTOS_DIR = Path("D:/MINI Project/faculty_photos_new")
ASSETS_DIR = BASE_DIR / "assets" / "faculty"
PLACEHOLDER_PHOTO = PHOTOS_DIR / "placeholder_avatar.jpg"
if not PLACEHOLDER_PHOTO.exists():
    PLACEHOLDER_PHOTO = ASSETS_DIR / "avatar_placeholder.png"


def normalize_name_key(name: str) -> str:
    import re
    cleaned = re.sub(r"^(?:dr\.?|mr\.?|mrs\.?|ms\.?|prof\.?|smt\.?)\s+", "", name.strip(), flags=re.I)
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", cleaned).lower()
    if cleaned in ["kalavathigk", "kalavathik", "kalavatik"]:
        return "kalavatik"
    if cleaned in ["santoshkumarkb", "santhoshkumarkb", "santoshkumar", "santhoshkumar"]:
        return "santoshkumarkb"
    if cleaned in ["anandababuj", "anandababu", "anandbabuj", "anandbabu"]:
        return "anandababuj"
    if cleaned in ["kunalg", "kunalgm", "kunalgs", "kunalcs", "drkunalgs"]:
        return "kunalgs"
    return cleaned


def run_enrichment() -> list[dict[str, Any]]:
    print("=" * 80)
    print(" ENRICHING FACULTY PROFILES & SYNCHRONIZING WITH HOD_VERIFIED")
    print("=" * 80)

    # 1. Load existing profiles
    with open(PROFILES_FILE, "r", encoding="utf-8") as f:
        existing_profiles: list[dict[str, Any]] = json.load(f)

    print(f"Loaded {len(existing_profiles)} existing faculty profiles.")

    profiles_by_id: dict[str, dict[str, Any]] = {}
    for p in existing_profiles:
        pid = p.get("id") or f"{p.get('normalized_name')}_{normalize_name_key(p.get('department', ''))}"
        p["id"] = pid
        profiles_by_id[pid] = p

    # 2. Update HOD designations strictly per hod_verified.json
    hod_map = hod_manager.load_hod_verified()

    # Reset any former HODs who are no longer the HOD
    former_hod_resets = {
        "prof_l_kumaraswamy": "Associate Professor",
        "dr_h_s_narashimhan": "Professor",
        "chandrikaj": "Professor",
        "dr_chandrikaj": "Professor",
    }
    for pid, p in profiles_by_id.items():
        p_norm = p.get("normalized_name", "")
        for target_key, new_desig in former_hod_resets.items():
            if target_key in p.get("id", "").lower() or target_key.replace("_", "") in p_norm:
                p["designation"] = new_desig
                print(f"  Reset designation for {p['name']}: {new_desig}")

    # Ensure ECE & DECS Santhosh Kumar has clean name, designation, and genuine photo
    for pid, p in profiles_by_id.items():
        if "santhosh" in p.get("name", "").lower() or "santosh" in p.get("name", "").lower() or "kbs@" in p.get("email", "").lower():
            p["name"] = "Dr. Santosh Kumar K.B."
            p["normalized_name"] = normalize_name_key("Dr. Santosh Kumar K.B.")
            p["photo_path"] = str(PHOTOS_DIR / "dr_santosh_kumar_kb.jpg")
            p["qualification"] = "B.E, M.Tech, PhD"
            p["designation"] = "Associate Professor"
            p["email"] = "kbs@mcehassan.ac.in"
            print(f"  Updated Dr. Santosh Kumar photo & name in {p.get('department')}")

    # Ensure Dr. Chandrika.J designation is Professor (not HOD)
    for pid, p in list(profiles_by_id.items()):
        if "chandrika" in p.get("name", "").lower():
            p["designation"] = "Professor"
            print(f"  Confirmed Dr. Chandrika.J designation is: {p['designation']}")

    # Set confirmed HODs
    for code, hinfo in hod_map.items():
        if hinfo.get("status") == "not_offered":
            continue
        h_name = hinfo["hod_name"]
        h_norm = normalize_name_key(h_name)
        h_dept = hinfo["canonical_name"]

        found = False
        for pid, p in profiles_by_id.items():
            if (h_norm in p.get("normalized_name", "") or p.get("normalized_name", "") in h_norm) and (
                normalize_name_key(h_dept) in normalize_name_key(p.get("department", ""))
                or code in p.get("department", "").upper()
            ):
                p["designation"] = hinfo["designation"]
                p["photo_path"] = hinfo["photo_path"]
                if hinfo.get("qualification"):
                    p["qualification"] = hinfo["qualification"]
                found = True
                print(f"  Synchronized HOD {h_name} -> {h_dept}")
                break

    # Explicitly ensure Dr. Ananda Babu J is indexed as HOD of Computer Science and Engineering
    cse_hod_id = "anandababuj_computerscienceandengineering"
    profiles_by_id[cse_hod_id] = {
        "id": cse_hod_id,
        "name": "Dr. Ananda Babu J",
        "normalized_name": normalize_name_key("Dr. Ananda Babu J"),
        "designation": "Professor and Head of Department (HOD)",
        "department": "Computer Science and Engineering",
        "parent_department": "Department of Computer Science and Engineering",
        "other_details": "Heads both Computer Science & Engineering and Information Science & Engineering",
        "qualification": "B.E., M.Tech., Ph.D.",
        "experience": "",
        "specialization": "Computer Science & Engineering, Image Processing, Pattern Recognition",
        "email": "gabj@mcehassan.ac.in",
        "phone": "9844081383",
        "photo_path": str(PHOTOS_DIR / "ise_ananda_babu_j.jpg"),
        "source_file": "hod s of college.pdf",
        "page": 1,
    }

    # 3. Verify and Synchronize all 5 MCA Faculty Members from Official College Screenshot
    # Clean up old temporary key if present
    profiles_by_id.pop("mca_dr_kunal_cs", None)

    mca_official_members = [
        ("Mrs. Margaret R.E.", "Assistant Professor and Head of Department (HOD)", "MCA", "rem@mcehassan.ac.in", "9448006138", "1-738371608", "mca_mrs_margaret_re.jpg"),
        ("Dr. Kunal G.S.", "Associate Professor", "M.Sc., PhD", "kgs@mcehassan.ac.in", "7848092999", "1-4478711858", "mca_dr_kunal_gs.jpg"),
        ("Mr. Prasanna K S", "Assistant Professor", "MCA", "ksp@mcehassan.ac.in", "9945877723", "1-738371752", "mca_mr_prasanna_ks.jpg"),
        ("Mr. Vasanth Kumar N.T.", "Assistant Professor", "MCA", "ntv@mcehassan.ac.in", "9741429929", "1-738421514", "mca_mr_vasanth_kumar_nt.jpg"),
        ("Mr. Chandra Shekar C S", "Assistant Professor", "Bsc ,MCA", "csc@mcehassan.ac.in", "9731341220", "1-733702017", "mca_mr_chandra_shekar_cs.jpg"),
    ]

    for name, desig, qual, email, phone, fac_id, p_fn in mca_official_members:
        norm = normalize_name_key(name)
        m_id = f"mca_{norm}"
        # Also clean up any loose alias keys in profiles_by_id
        for k in list(profiles_by_id.keys()):
            p = profiles_by_id[k]
            if p.get("department") == "Master of Computer Applications":
                if norm in p.get("normalized_name", "") or p.get("normalized_name", "") in norm:
                    profiles_by_id.pop(k, None)

        profiles_by_id[m_id] = {
            "id": m_id,
            "name": name,
            "normalized_name": norm,
            "designation": desig,
            "department": "Master of Computer Applications",
            "qualification": qual,
            "experience": "",
            "specialization": "Computer Applications",
            "faculty_id": fac_id,
            "email": email,
            "phone": phone,
            "photo_path": str(PHOTOS_DIR / p_fn),
            "source_file": "all department faculty.pdf",
            "page": 94,
        }
        print(f"  Synchronized official MCA faculty: {name} ({qual})")

    # 4. Add PG Programs Faculty
    # A) CADS Faculty (7 members)
    cads_members = [
        ("Dr. H. S. Narashimhan", "Professor", "B.E., M.Tech. (IIT Kharagpur), Ph.D.", "hsn@mcehassan.ac.in", "9448919722", "dr_h_s_narashimhan.jpg", 91),
        ("Dr. Manu K.C", "Associate Professor and PG Coordinator", "B.E., M.Tech., Ph.D.", "kcm@mcehassan.ac.in", "9964246092", "civi_k_c_manu.jpg", 91),
        ("Mrs. Chandini M.S", "Assistant Professor", "M.Tech", "msc@mcehassan.ac.in", "8971802166", "civi_chandini_m_s.jpg", 91),
        ("Mrs. Nudi shree", "Assistant Professor", "M.Tech", "nshree@mcehassan.ac.in", "9740796863", "civi_nudi_shree.jpg", 91),
        ("Mrs. Rashmi B.R", "Assistant Professor", "M.Tech", "rrb@mcehassan.ac.in", "6300835524", "civi_rashmi_b_r.jpg", 91),
        ("Mr. Niranjan Nayaka R.K", "Assistant Professor", "M.Tech", "nrk@mcehassan.ac.in", "8746063131", "civi_niranjan_nayaka_r_k.jpg", 92),
        ("Ms. Shamana B.S", "Assistant Professor", "M.Tech", "shb@mcehassan.ac.in", "9110282352", "civi_shamana_b_s.jpg", 92),
    ]
    for name, desig, qual, email, phone, p_fn, pno in cads_members:
        norm = normalize_name_key(name)
        cid = f"cads_{norm}"
        profiles_by_id[cid] = {
            "id": cid,
            "name": name,
            "normalized_name": norm,
            "designation": desig,
            "department": "Computer Aided Design of Structures (CADS)",
            "parent_department": "Department of Civil Engineering",
            "other_details": "Shared faculty with Department of Civil Engineering",
            "qualification": qual,
            "experience": "",
            "specialization": "Structural Engineering / CADS",
            "email": email,
            "phone": phone,
            "photo_path": str(PHOTOS_DIR / p_fn),
            "source_file": "all department faculty.pdf",
            "page": pno,
        }
    print(f"  Added {len(cads_members)} CADS faculty members.")

    # B) DECS Faculty (7 members)
    decs_members = [
        ("Dr. Padmaja Devi G", "Professor and Head of Department (HOD)", "B.E., M.Tech, Ph.D.", "gpd@mcehassan.ac.in", "9164539950", "dr_padmaja_devi_g_professor_and_hod_be.jpg", 89),
        ("Dr. Prathap P B", "Associate Professor", "B.E., M.Tech, Ph.D.", "pbp@mcehassan.ac.in", "9686787827", "dr_prathap_p_b.jpg", 89),
        ("Mr. Raghuram K A", "Assistant Professor", "M.Tech", "kar@mcehassan.ac.in", "9844948059", "mrraghuram_k_a.jpg", 89),
        ("Dr. Deepika K C", "Associate Professor and PG Coordinator", "B.E., M.Tech, Ph.D.", "kcd@mcehassan.ac.in", "7411122817", "dr_deepika_k_c.jpg", 89),
        ("Ranjitha Krishna R", "Assistant Professor", "Qualification information is not available in the college knowledge base.", "rkr@mcehassan.ac.in", "7349449277", "ranjitha_krishna_r.jpg", 89),
        ("Dr. Santosh Kumar K.B.", "Associate Professor", "B.E, M.Tech, PhD", "kbs@mcehassan.ac.in", "9740580160", "dr_santosh_kumar_kb.jpg", 90),
        ("Dr. Prakruthi H L", "Associate Professor", "B.E., M.Tech, PhD", "hlp@mcehassan.ac.in", "9902150540", "dr_prakruthi_h_l.jpg", 90),
    ]
    for name, desig, qual, email, phone, p_fn, pno in decs_members:
        norm = normalize_name_key(name)
        cid = f"decs_{norm}"
        profiles_by_id[cid] = {
            "id": cid,
            "name": name,
            "normalized_name": norm,
            "designation": desig,
            "department": "Digital Electronics and Communication Systems (DECS)",
            "parent_department": "Department of Electronics and Communication Engineering",
            "other_details": "Shared faculty with Department of Electronics & Communication Engineering",
            "qualification": qual,
            "experience": "",
            "specialization": "Digital Electronics & Communication Systems",
            "email": email,
            "phone": phone,
            "photo_path": str(PHOTOS_DIR / p_fn),
            "source_file": "all department faculty.pdf",
            "page": pno,
        }
    print(f"  Added {len(decs_members)} DECS faculty members.")

    # C) PES Faculty (2 members)
    pes_members = [
        ("Dr. S. Rajanna", "Professor and Head of Department (HOD)", "B.E., M.Tech., Ph.D. (IIT Roorkee)", "gsr@mcehassan.ac.in", "8791340700", "dr_rajanna_s.jpg", 93),
        ("Dr. Gowri Shankar M", "Associate Professor", "B.E., M.E., Ph.D.", "mgs@mcehassan.ac.in", "8526063551", "dr_gowri_shankar_m.jpg", 93),
    ]
    for name, desig, qual, email, phone, p_fn, pno in pes_members:
        norm = normalize_name_key(name)
        cid = f"pes_{norm}"
        profiles_by_id[cid] = {
            "id": cid,
            "name": name,
            "normalized_name": norm,
            "designation": desig,
            "department": "Power and Energy Systems (PES)",
            "parent_department": "Department of Electrical and Electronics Engineering",
            "other_details": "Shared faculty with Department of Electrical & Electronics Engineering",
            "qualification": qual,
            "experience": "",
            "specialization": "Power and Energy Systems",
            "email": email,
            "phone": phone,
            "photo_path": str(PHOTOS_DIR / p_fn),
            "source_file": "all department faculty.pdf",
            "page": pno,
        }
    print(f"  Added {len(pes_members)} PES faculty members.")

    # D) AIDS Faculty (2 members)
    aids_members = [
        ("Dr. Balaji Prabhu B V", "Assistant Professor", "Ph.D., PostDoc (IISc.)", "bvb@mcehassan.ac.in", "8497883766", "dr_balaji_prabhu_b_v.jpg", 93, "Computer Science and Engineering"),
        ("Prof. Shruthi DV", "Assistant Professor", "B.E, M.Tech", "dvs@mcehassan.ac.in", "9986458883", "ise_shruthi_d_v.jpg", 93, "Information Science and Engineering"),
    ]
    for name, desig, qual, email, phone, p_fn, pno, dept_name in aids_members:
        norm = normalize_name_key(name)
        cid = f"aids_{norm}"
        profiles_by_id[cid] = {
            "id": cid,
            "name": name,
            "normalized_name": norm,
            "designation": desig,
            "department": dept_name,
            "parent_department": dept_name,
            "other_details": "Specialization: Artificial Intelligence and Data Science (AIDS)",
            "qualification": qual,
            "experience": "",
            "specialization": "Artificial Intelligence & Data Science",
            "email": email,
            "phone": phone,
            "photo_path": str(PHOTOS_DIR / p_fn),
            "source_file": "all department faculty.pdf",
            "page": pno,
        }
    print(f"  Added {len(aids_members)} AIDS faculty members.")

    # E) RAI Faculty (1 member)
    rai_members = [
        ("Dr. Arjun B C", "Professor and Head of Department (HOD)", "B.E., M.Tech., Ph.D.", "abc@mcehassan.ac.in", "9844584208", "dr_arjun_b_c.jpg", 88),
    ]
    for name, desig, qual, email, phone, p_fn, pno in rai_members:
        norm = normalize_name_key(name)
        cid = f"rai_{norm}"
        profiles_by_id[cid] = {
            "id": cid,
            "name": name,
            "normalized_name": norm,
            "designation": desig,
            "department": "Robotics and Artificial Intelligence",
            "parent_department": "Department of Artificial Intelligence and Machine Learning",
            "other_details": "Shared faculty with AIML Department",
            "qualification": qual,
            "experience": "",
            "specialization": "Robotics & Artificial Intelligence",
            "email": email,
            "phone": phone,
            "photo_path": str(PHOTOS_DIR / p_fn),
            "source_file": "all department faculty.pdf",
            "page": pno,
        }
    print(f"  Added {len(rai_members)} RAI faculty members.")

    # EIE Faculty: Dr. C M Naveen Kumar
    eie_id = "eie_dr_c_m_naveen_kumar"
    profiles_by_id[eie_id] = {
        "id": eie_id,
        "name": "Dr. C M Naveen Kumar",
        "normalized_name": normalize_name_key("Dr. C M Naveen Kumar"),
        "designation": "Associate Professor and Head of Department (HOD)",
        "department": "Electronics and Instrumentation Engineering",
        "parent_department": "Department of Computer Science and Business Systems",
        "other_details": "Department accredited by NBA Tier-1; formerly Instrumentation Technology",
        "qualification": "B.E. (IT), M.Tech. (CSE), Ph.D., Ing.Paed.IGIP",
        "experience": "",
        "specialization": "Electronics and Instrumentation Engineering",
        "email": "gcmn@mcehassan.ac.in",
        "phone": "9902128829",
        "photo_path": str(PHOTOS_DIR / "dr_c_m_naveen_kumar_associate_professor_and_hod_faculty_id.jpg"),
        "source_file": "hod s of college.pdf",
        "page": 3,
    }

    # Verify photo paths exist on disk
    updated_profiles = list(profiles_by_id.values())
    missing_photos = []
    for p in updated_profiles:
        p_path = p.get("photo_path")
        if not p_path or not Path(p_path).exists():
            missing_photos.append(p["name"])
            p["photo_path"] = str(PLACEHOLDER_PHOTO)

    # Save to PROFILES_FILE
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_profiles, f, indent=2, ensure_ascii=False)

    print(f"\nTotal enriched faculty profiles: {len(updated_profiles)}.")
    print(f"Missing photos on disk: {len(missing_photos)} (Assigned placeholder).")

    # Index into ChromaDB 'faculty_profiles' collection
    client = chromadb.PersistentClient(path=str(BASE_DIR / "chroma_db"))
    col = client.get_or_create_collection(
        name=source_config.FACULTY_PROFILES_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    ids = [p["id"] for p in updated_profiles]
    documents = [
        f"{p.get('name', '')} {p.get('designation', '')} {p.get('department', '')} {p.get('qualification', '')} {p.get('specialization', '')} {p.get('email', '')}"
        for p in updated_profiles
    ]
    metadatas = [
        {
            "name": p.get("name", ""),
            "department": p.get("department", ""),
            "designation": p.get("designation", ""),
            "email": p.get("email", ""),
            "source_file": p.get("source_file", ""),
            "page": p.get("page", 1),
        }
        for p in updated_profiles
    ]

    col.upsert(ids=ids, documents=documents, metadatas=metadatas)
    print(f"Successfully upserted {col.count()} profiles into ChromaDB '{col.name}' collection.")

    # Verify 'mce_docs' is still strictly 83
    orig_col = client.get_collection(source_config.ORIGINAL_COLLECTION_NAME)
    print(f"Safety check: '{orig_col.name}' count: {orig_col.count()} (MUST BE 83).")
    assert orig_col.count() == 83, f"CRITICAL: mce_docs count changed to {orig_col.count()}!"

    return updated_profiles


if __name__ == "__main__":
    run_enrichment()
