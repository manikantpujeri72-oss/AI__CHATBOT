"""Faculty extraction and structured store module for MCE AI Assistant.

Extracts faculty records and portrait photos from MCE documents:
- Banner-style PDFs (AIML, CSBS, CSE, EEE, MCA/ECE)
- Full-page card PDFs (Civil, ECE, Mechanical, VLSI)
- Key college officers from knowledge_base.pdf
- Drop-in photos from documents/faculty_photos/
Saves structured data in faculty.json and cropped photos in assets/faculty/.
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader
from rapidfuzz import fuzz

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "documents"
ASSETS_DIR = BASE_DIR / "assets" / "faculty"
DROP_IN_PHOTOS_DIR = DOCS_DIR / "faculty_photos"
FACULTY_JSON = BASE_DIR / "faculty.json"
OCR_SCRIPT = BASE_DIR / "ocr_helper.ps1"

# Department mapping from PDF filename
DEPT_MAP = {
    "AIML faculty.pdf": ("Artificial Intelligence & Machine Learning", "AIML"),
    "civil faculty.pdf": ("Civil Engineering", "CIVIL"),
    "CSBS Faculty.pdf": ("Computer Science & Business Systems", "CSBS"),
    "CSE department.pdf": ("Computer Science & Engineering", "CSE"),
    "electrical and electronics faculty.pdf": ("Electrical & Electronics Engineering", "EEE"),
    "electronics and communication Department.pdf": ("Electronics & Communication Engineering", "ECE"),
    "ISE faculty.pdf": ("Information Science & Engineering", "ISE"),
    "mca and ece.pdf": ("Master of Computer Applications", "MCA"),
    "mechanical faculty.pdf": ("Mechanical Engineering", "MECH"),
    "VLSI faculty.pdf": ("Electronics Engineering (VLSI Design & Technology)", "VLSI"),
}

DESIGNATION_ORDER = {
    "principal": 1,
    "dean": 2,
    "head of department": 3,
    "hod": 3,
    "professor & head": 3,
    "professor & hod": 3,
    "professor": 4,
    "associate professor": 5,
    "assistant professor": 6,
    "adjunct professor": 7,
    "visiting professor": 8,
    "lecturer": 9,
    "warden": 10,
    "training and placement officer": 11,
    "librarian": 12,
}


def create_avatar_placeholder() -> Path:
    """Create a sleek neutral avatar placeholder PNG if not already existing."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ASSETS_DIR / "avatar_placeholder.png"
    if out_path.exists():
        return out_path

    # Create a 300x300 neutral avatar with smooth grey circle & bust silhouette
    img = Image.new("RGBA", (300, 300), (240, 243, 246, 255))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    
    # Outer circle background
    draw.ellipse((20, 20, 280, 280), fill=(225, 230, 236, 255))
    # Head
    draw.ellipse((105, 75, 195, 165), fill=(160, 170, 185, 255))
    # Shoulders / bust
    draw.pieslice((50, 175, 250, 360), start=180, end=360, fill=(160, 170, 185, 255))
    
    img.save(str(out_path), "PNG")
    return out_path


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", s)


def clean_phone(text: str) -> str:
    phones = re.findall(r"\b(?:\+91[\s-]?)?[6789]\d{9}\b|\b08172[- ]?\d{6}\b", text)
    if phones:
        return phones[0].replace(" ", "").replace("-", "")
    # Check 10 digits
    m = re.search(r"\b\d{10}\b", text)
    return m.group(0) if m else ""


def clean_email(text: str) -> str:
    m = re.search(r"\b[A-Za-z0-9._%+-]+@mcehassan\.ac\.in\b", text, re.IGNORECASE)
    if m:
        return m.group(0).lower()
    m2 = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
    return m2.group(0).lower() if m2 else ""


def ocr_image(img_path: Path) -> dict[str, Any]:
    """Run Windows.Media.Ocr via PowerShell script."""
    if not OCR_SCRIPT.exists():
        return {"Text": "", "Lines": []}
    try:
        r = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(OCR_SCRIPT), "-ImagePath", str(img_path)],
            capture_output=True,
            timeout=20,
        )
        if r.returncode == 0 and r.stdout:
            stdout_str = r.stdout.decode("utf-8", errors="replace").strip()
            if stdout_str:
                return json.loads(stdout_str)
    except Exception as e:
        print(f"OCR error on {img_path.name}: {e}")
    return {"Text": "", "Lines": []}


def parse_faculty_card_lines(lines: list[str], default_dept: str, dept_code: str, source_file: str) -> dict[str, Any]:
    """Extract fields from parsed OCR lines for a faculty card."""
    record: dict[str, Any] = {
        "id": "",
        "name": "",
        "designation": "",
        "department": default_dept,
        "dept_code": dept_code,
        "qualification": "",
        "specialization": "",
        "experience": "",
        "faculty_id": "",
        "phone": "",
        "email": "",
        "other_details": "",
        "photo_path": "",
        "source_file": source_file,
    }

    filtered_lines = [l.strip() for l in lines if l.strip() and not re.search(r"^view\s+profile$", l.strip(), re.I)]
    if not filtered_lines:
        return record

    # Find email & phone across all lines
    full_text = " ".join(filtered_lines)
    record["phone"] = clean_phone(full_text)
    record["email"] = clean_email(full_text)

    # Faculty ID
    fid_m = re.search(r"Faculty\s*ID\s*:\s*([A-Za-z0-9-]+)", full_text, re.I)
    if fid_m:
        record["faculty_id"] = fid_m.group(1).strip()

    # Look for name: find first valid name line
    name_cand = ""
    for line in filtered_lines:
        line_clean = line.strip()
        if len(line_clean) < 3 or re.match(r"^[\d\W_]+$", line_clean):
            continue
        if any(line_clean.lower().startswith(p) for p in ["department", "faculty id", "view profile", "welcome", "page"]):
            continue
        if re.search(r"\b(Dr\.|Prof\.|Mr\.|Mrs\.|Ms\.)", line_clean, re.I) or (
            len(line_clean.split()) >= 2 and line_clean[0].isupper() and not any(k in line_clean.lower() for k in ["faculty", "engineering", "college", "assistant", "associate", "professor"])
        ):
            name_cand = line_clean
            break

    if not name_cand and filtered_lines:
        name_cand = filtered_lines[0]

    # Clean stray leading noise/punctuation from name
    name_cand = re.sub(r"^[\d\W_]+", "", name_cand).strip()
    record["name"] = name_cand

    # Identify designation
    desig_patterns = [
        r"\b(?:Professor\s*&\s*(?:Head|HOD))\b",
        r"\b(?:Associate\s*Professor\s*&\s*(?:Head|HOD))\b",
        r"\b(?:Associate\s*Professor)\b",
        r"\b(?:Assistant\s*Professor)\b",
        r"\b(?:Professor)\b",
        r"\b(?:Head\s*of\s*Department|HOD)\b",
        r"\b(?:Dean[a-zA-Z\s–-]*)\b",
        r"\b(?:Principal)\b",
        r"\b(?:Lecturer)\b",
        r"\b(?:Instructor)\b",
    ]
    for line in filtered_lines:
        for pat in desig_patterns:
            m = re.search(pat, line, re.I)
            if m:
                record["designation"] = m.group(0).strip().title()
                break
        if record["designation"]:
            break

    if not record["designation"]:
        # Fallback designation from line 1 if line 0 was name
        if len(filtered_lines) > 1 and "faculty id" not in filtered_lines[1].lower():
            record["designation"] = filtered_lines[1]
        else:
            record["designation"] = "Faculty"

    # Qualification: look for B.E, B.Tech, M.Tech, Ph.D, M.Sc, etc.
    qual_matches = []
    for line in filtered_lines:
        if re.search(r"\b(B\.?E\.?|B\.?Tech\.?|M\.?Tech\.?|M\.?E\.?|Ph\.?D\.?|M\.?Sc\.?|MCA|MBA)\b", line, re.I):
            # Strip out phone/email from this line
            q_line = re.sub(r"\b\d{10}\b", "", line)
            q_line = re.sub(r"\b[A-Za-z0-9._%+-]+@mcehassan\.ac\.in\b", "", q_line, flags=re.I)
            q_line = re.sub(r"Faculty\s*ID\s*:\s*[A-Za-z0-9-]+", "", q_line, flags=re.I)
            q_line = q_line.strip(" ,g")
            if q_line:
                qual_matches.append(q_line)
    if qual_matches:
        record["qualification"] = ", ".join(qual_matches)

    record["id"] = f"{dept_code.lower()}_{slugify(record['name'])}"
    return record


def find_drop_in_photo(name: str) -> str | None:
    """Check documents/faculty_photos/ for matching image file."""
    if not DROP_IN_PHOTOS_DIR.exists():
        return None
    name_clean = re.sub(r"[^\w\s]", "", name).strip().lower()
    tokens = [t for t in name_clean.split() if t not in ("dr", "prof", "mr", "mrs", "ms")]
    
    best_file = None
    best_score = 0.0

    for f in DROP_IN_PHOTOS_DIR.glob("*"):
        if f.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        stem_clean = re.sub(r"[^\w\s]", "", f.stem).strip().lower()
        score = fuzz.token_sort_ratio(name_clean, stem_clean)
        # Check if all key name tokens match
        if all(t in stem_clean for t in tokens) and len(tokens) >= 2:
            return str(f)
        if score > 80 and score > best_score:
            best_score = score
            best_file = str(f)

    if best_score >= 82 and best_file:
        return best_file
    return None


def extract_and_save_photo(
    img: Image.Image,
    record_id: str,
    layout_type: str,  # 'banner' or 'fullpage'
    name: str,
) -> str:
    """Crop the faculty face portrait from banner or fullpage image and save."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ASSETS_DIR / f"{record_id}.jpg"

    # Check drop-in photos first
    drop_in = find_drop_in_photo(name)
    if drop_in:
        try:
            di_img = Image.open(drop_in).convert("RGB")
            w, h = di_img.size
            if w > 300:
                di_img = di_img.resize((300, int(h * 300 / w)), Image.LANCZOS)
            di_img.save(str(out_path), "JPEG", quality=85)
            return str(out_path.relative_to(BASE_DIR)).replace("\\", "/")
        except Exception as e:
            print(f"Error loading drop-in photo for {name}: {e}")

    w, h = img.size
    try:
        if layout_type == "banner":
            # Photo is roughly on the left from x=40 to x=430
            crop_box = (int(w * 0.02), int(h * 0.04), int(w * 0.23), int(h * 0.94))
        else:
            # Fullpage card: photo is on top
            crop_box = (int(w * 0.04), int(h * 0.03), int(w * 0.96), int(h * 0.52))

        cropped = img.crop(crop_box).convert("RGB")
        cw, ch = cropped.size
        if cw > 300:
            cropped = cropped.resize((300, int(ch * 300 / cw)), Image.LANCZOS)
        cropped.save(str(out_path), "JPEG", quality=85)
        return str(out_path.relative_to(BASE_DIR)).replace("\\", "/")
    except Exception as e:
        print(f"Error cropping photo for {record_id}: {e}")
        return ""

def _process_banner_item(args):
    fname, p_idx, k, raw_data, dept_name, dept_code, card_idx, temp_dir = args
    try:
        img = Image.open(io.BytesIO(raw_data))
        safe_k = k.lstrip("/")
        temp_img_path = temp_dir / f"{dept_code}_p{p_idx}_{safe_k}.jpg"
        img.save(str(temp_img_path), "JPEG")

        ocr_res = ocr_image(temp_img_path)
        lines = [line["Text"] for line in ocr_res.get("Lines", [])]
        rec = parse_faculty_card_lines(lines, dept_name, dept_code, fname)
        if rec["name"]:
            rec["id"] = f"{dept_code.lower()}_{card_idx}_{slugify(rec['name'])}"
            photo_rel = extract_and_save_photo(img, rec["id"], "banner", rec["name"])
            rec["photo_path"] = photo_rel
            return rec
    except Exception as e:
        print(f"Error on {fname} p{p_idx} {k}: {e}")
    return None


def _process_fullpage_item(args):
    fname, p_idx, k, raw_data, dept_name, dept_code, temp_dir = args
    try:
        img = Image.open(io.BytesIO(raw_data))
        safe_k = k.lstrip("/")
        temp_img_path = temp_dir / f"{dept_code}_p{p_idx}_{safe_k}.jpg"
        img.save(str(temp_img_path), "JPEG")

        ocr_res = ocr_image(temp_img_path)
        lines = [line["Text"] for line in ocr_res.get("Lines", [])]
        rec = parse_faculty_card_lines(lines, dept_name, dept_code, fname)
        if rec["name"]:
            rec["id"] = f"{dept_code.lower()}_{p_idx+1}_{slugify(rec['name'])}"
            photo_rel = extract_and_save_photo(img, rec["id"], "fullpage", rec["name"])
            rec["photo_path"] = photo_rel
            return rec
    except Exception as e:
        print(f"Error on {fname} p{p_idx} {k}: {e}")
    return None


def extract_all_faculty(folder: Path | str = DOCS_DIR) -> list[dict[str, Any]]:
    """Extract all faculty records and photos across knowledge base."""
    import concurrent.futures
    folder = Path(folder)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    DROP_IN_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    create_avatar_placeholder()

    records: list[dict[str, Any]] = []
    temp_dir = BASE_DIR / "temp_ocr"
    temp_dir.mkdir(parents=True, exist_ok=True)

    banner_tasks = []
    card_counter = 0

    banner_pdfs = [
        "AIML faculty.pdf",
        "CSBS Faculty.pdf",
        "CSE department.pdf",
        "electrical and electronics faculty.pdf",
        "mca and ece.pdf",
    ]

    for fname in banner_pdfs:
        fpath = folder / fname
        if not fpath.exists():
            continue
        dept_name, dept_code = DEPT_MAP.get(fname, ("Department", "DEPT"))
        reader = PdfReader(str(fpath))

        for p_idx, page in enumerate(reader.pages):
            xobjs = page.get("/Resources", {}).get("/XObject", {})
            sorted_keys = sorted(xobjs.keys(), key=lambda k: int(re.search(r"\d+", k).group(0)) if re.search(r"\d+", k) else 0)
            for k in sorted_keys:
                obj = xobjs[k]
                if obj.get("/Subtype") != "/Image":
                    continue
                w, h = obj.get("/Width", 0), obj.get("/Height", 0)
                if w < 1000:
                    continue
                raw_bytes = obj.get_data()
                if h > 700:
                    # Stacked cards in single image
                    img_full = Image.open(io.BytesIO(raw_bytes))
                    half_h = h // 2
                    top_img = img_full.crop((0, 0, w, half_h))
                    bot_img = img_full.crop((0, half_h, w, h))
                    top_b = io.BytesIO()
                    top_img.save(top_b, format="JPEG")
                    bot_b = io.BytesIO()
                    bot_img.save(bot_b, format="JPEG")
                    card_counter += 1
                    banner_tasks.append((fname, p_idx, f"{k}_top", top_b.getvalue(), dept_name, dept_code, card_counter, temp_dir))
                    card_counter += 1
                    banner_tasks.append((fname, p_idx, f"{k}_bot", bot_b.getvalue(), dept_name, dept_code, card_counter, temp_dir))
                else:
                    card_counter += 1
                    banner_tasks.append((fname, p_idx, k, raw_bytes, dept_name, dept_code, card_counter, temp_dir))

    fullpage_tasks = []
    fullpage_pdfs = [
        "civil faculty.pdf",
        "electronics and communication Department.pdf",
        "mechanical faculty.pdf",
        "VLSI faculty.pdf",
    ]

    for fname in fullpage_pdfs:
        fpath = folder / fname
        if not fpath.exists():
            continue
        dept_name, dept_code = DEPT_MAP.get(fname, ("Department", "DEPT"))
        reader = PdfReader(str(fpath))

        for p_idx, page in enumerate(reader.pages):
            xobjs = page.get("/Resources", {}).get("/XObject", {})
            for k, obj in xobjs.items():
                if obj.get("/Subtype") != "/Image":
                    continue
                fullpage_tasks.append((fname, p_idx, k, obj.get_data(), dept_name, dept_code, temp_dir))

    print(f"Running parallel extraction: {len(banner_tasks)} banner cards, {len(fullpage_tasks)} fullpage cards...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        banner_results = list(executor.map(_process_banner_item, banner_tasks))
        fullpage_results = list(executor.map(_process_fullpage_item, fullpage_tasks))

    for r in banner_results:
        if r:
            records.append(r)
    for r in fullpage_results:
        if r:
            records.append(r)


    # 3. Add known College Administrators / Deans / HODs from knowledge_base.pdf
    admin_officers = [
        {
            "id": "admin_prasanna_a_a",
            "name": "Dr. Prasanna A. A.",
            "designation": "Dean of Examinations",
            "department": "Examinations / Administration",
            "dept_code": "ADMIN",
            "qualification": "Ph.D.",
            "specialization": "Examinations & Academic Assessment",
            "experience": "",
            "faculty_id": "",
            "phone": "8172245317",
            "email": "aap@mcehassan.ac.in",
            "other_details": "Oversees semester-end exams, timetables, and valuation.",
            "photo_path": "",
            "source_file": "knowledge_base.pdf",
        },
        {
            "id": "admin_indira_bahaddur",
            "name": "Dr. Indira Bahaddur",
            "designation": "Dean – Student Affairs",
            "department": "Student Affairs / Administration",
            "dept_code": "ADMIN",
            "qualification": "Ph.D.",
            "specialization": "Student Welfare & Scholarships",
            "experience": "",
            "faculty_id": "",
            "phone": "9449689093",
            "email": "deansa@mcehassan.ac.in",
            "other_details": "Coordinates student affairs, scholarships, and campus life. Additional contact: 9731793730.",
            "photo_path": "",
            "source_file": "knowledge_base.pdf",
        },
        {
            "id": "admin_geetha_kiran_a",
            "name": "Dr. Geetha Kiran A",
            "designation": "Dean (Corporate Affairs)",
            "department": "Corporate Affairs & Training",
            "dept_code": "ADMIN",
            "qualification": "Ph.D.",
            "specialization": "Corporate Relations & Industry Collaboration",
            "experience": "",
            "faculty_id": "",
            "phone": "",
            "email": "",
            "other_details": "Heads Corporate Affairs and Industry Collaborations.",
            "photo_path": "",
            "source_file": "knowledge_base.pdf",
        },
        {
            "id": "admin_jeevan_t_p",
            "name": "Dr. Jeevan T. P.",
            "designation": "Training and Placement Officer",
            "department": "Training and Placement Cell",
            "dept_code": "TP",
            "qualification": "Ph.D.",
            "specialization": "Campus Recruitment & Placement Training",
            "experience": "",
            "faculty_id": "",
            "phone": "",
            "email": "",
            "other_details": "Coordinates campus recruitment drives, soft skills, and placement offers.",
            "photo_path": "",
            "source_file": "knowledge_base.pdf",
        },
        {
            "id": "admin_manjunath_g",
            "name": "Prof. G. Manjunath",
            "designation": "Hostel Warden",
            "department": "Hostel Administration",
            "dept_code": "HOSTEL",
            "qualification": "",
            "specialization": "Student Residence & Facilities",
            "experience": "",
            "faculty_id": "",
            "phone": "",
            "email": "",
            "other_details": "Warden for MCE Hostels. Additional contact Dr. Madhu K. S. (9738282552).",
            "photo_path": "",
            "source_file": "knowledge_base.pdf",
        },
        {
            "id": "admin_shankar_d_r",
            "name": "Mr. Shankar D. R.",
            "designation": "In-charge Librarian",
            "department": "Central Library",
            "dept_code": "LIBRARY",
            "qualification": "M.Lib.Sc.",
            "specialization": "Library Science & Digital Resources",
            "experience": "",
            "faculty_id": "",
            "phone": "",
            "email": "",
            "other_details": "In charge of MCE Central Library and departmental collections.",
            "photo_path": "",
            "source_file": "knowledge_base.pdf",
        },
    ]

    for off in admin_officers:
        # Check drop-in photo
        drop_in = find_drop_in_photo(off["name"])
        if drop_in:
            photo_rel = extract_and_save_photo(Image.open(drop_in), off["id"], "fullpage", off["name"])
            off["photo_path"] = photo_rel
        records.append(off)

    # Clean up temp_dir
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

    # Post-process records: ensure HODs and clean designations
    for rec in records:
        nm = rec.get("name", "").lower()
        if "chandrika" in nm and rec.get("dept_code") == "CSE":
            rec["designation"] = "Professor & Head of Department (HOD)"
        elif "narashimhan" in nm and rec.get("dept_code") == "CIVIL":
            rec["designation"] = "Professor & Head of Department (HOD)"
        elif "kumaraswamy" in nm and rec.get("dept_code") == "EEE":
            rec["designation"] = "Associate Professor & HOD"
        elif "ravikumar m.n" in nm and rec.get("dept_code") == "MCA":
            rec["designation"] = "Associate Professor & HOD"

    # Save to faculty.json
    FACULTY_JSON.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Total faculty records saved to faculty.json: {len(records)}")
    return records


def load_faculty_records() -> list[dict[str, Any]]:
    """Load faculty records from faculty.json (creates if missing)."""
    if not FACULTY_JSON.exists():
        return extract_all_faculty()
    try:
        return json.loads(FACULTY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return extract_all_faculty()


def get_designation_rank(designation: str) -> int:
    d_lower = designation.lower()
    for key, rank in DESIGNATION_ORDER.items():
        if key in d_lower:
            return rank
    return 20


def find_faculty(
    query: str,
    records: list[dict[str, Any]] | None = None,
    dept_code: str | None = None,
) -> list[dict[str, Any]]:
    """Find matching faculty members given a query and/or department code."""
    if records is None:
        records = load_faculty_records()

    if not records:
        return []

    q_lower = query.lower().strip()

    # If dept_code specified or department query
    if dept_code:
        dept_matches = [r for r in records if r.get("dept_code", "").upper() == dept_code.upper()]
        if dept_matches:
            sorted_matches = sorted(dept_matches, key=lambda r: get_designation_rank(r.get("designation", "")))
            # If specifically asking for HOD, return HOD card
            if any(k in q_lower for k in ["hod", "head of department", "head of the department"]):
                hod_matches = [r for r in sorted_matches if "hod" in r.get("designation", "").lower() or "head" in r.get("designation", "").lower()]
                if hod_matches:
                    return hod_matches[:1]
            # If asking specifically for professors in department
            if "professors in" in q_lower or "professors of" in q_lower:
                prof_matches = [r for r in sorted_matches if "professor" in r.get("designation", "").lower() and "assistant" not in r.get("designation", "").lower() and "associate" not in r.get("designation", "").lower()]
                if prof_matches:
                    return prof_matches
            return sorted_matches

    # Direct name search with fuzzy matching
    name_matches = []
    # Strip common query filler words
    cleaned_q = re.sub(r"\b(tell me about|who is|details of|professor|prof|dr|mr|mrs|ms|faculty|in|at|mce)\b", "", q_lower, flags=re.I).strip()

    for r in records:
        name = r.get("name", "")
        n_clean = re.sub(r"[^\w\s]", "", name).lower()
        # Designation match (e.g. Dean of Examinations, Warden, Placement Officer)
        desig = r.get("designation", "").lower()
        if any(term in desig for term in ["dean of examinations", "dean – student affairs", "dean student affairs", "dean (corporate affairs)", "warden", "librarian", "training and placement officer"]):
            if any(term in q_lower for term in ["dean of examinations", "dean – student affairs", "dean student affairs", "dean corporate affairs", "warden", "librarian", "placement officer", "tpo"]):
                for term in ["dean of examinations", "dean – student affairs", "dean student affairs", "warden", "librarian"]:
                    if term in q_lower and term in desig:
                        name_matches.append((r, 110))
                        break
        # Direct substring
        if cleaned_q and len(cleaned_q) >= 3 and cleaned_q in n_clean:
            name_matches.append((r, 100))
            continue
        # Fuzzy score
        score = fuzz.partial_ratio(cleaned_q, n_clean) if cleaned_q else 0
        token_score = fuzz.token_sort_ratio(cleaned_q, n_clean) if cleaned_q else 0
        best_s = max(score, token_score)
        if best_s >= 75:
            name_matches.append((r, best_s))

    if name_matches:
        name_matches.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in name_matches]

    return []
