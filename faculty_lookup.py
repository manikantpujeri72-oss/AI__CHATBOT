"""Faculty Lookup & Intent Routing system for MCE AI Assistant.

Handles:
- Intent detection: HOD_QUERY, DEPARTMENT_FACULTY_LIST, ALL_FACULTY, FACULTY_QUERY, GENERAL.
- Auto-discovered layered department resolution via short_forms.py.
- Exact single-faculty lookup with photo-first side-by-side format.
- Department faculty directory rendering with heading: '<Department>: N faculty'.
- All-departments college directory with expanders.
- Ambiguity detection when multiple people share a name.
- Non-person queries safely fall through to multi-source RAG.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from rapidfuzz import fuzz

import short_forms
import source_config
import ui_cards

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PHOTOS_DIR = source_config.FACULTY_PHOTOS_NEW_DIR
PROFILES_FILE = BASE_DIR / "faculty_profiles_new.json"

_PROFILES_CACHE: list[dict[str, Any]] | None = None


def get_all_profiles() -> list[dict[str, Any]]:
    """Load cached faculty profiles from JSON."""
    global _PROFILES_CACHE
    if _PROFILES_CACHE is not None:
        return _PROFILES_CACHE

    if PROFILES_FILE.exists():
        try:
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                _PROFILES_CACHE = json.load(f)
            return _PROFILES_CACHE
        except Exception:
            pass
    _PROFILES_CACHE = []
    return _PROFILES_CACHE


def normalize_name_key(name: str) -> str:
    cleaned = re.sub(r"\b(?:dr\.?|prof\.?|mr\.?|mrs\.?|ms\.?|sri\.?|smt\.?)\s+", "", name, flags=re.I)
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


def is_contact_query(query: str) -> bool:
    """Return True if query explicitly asks for contact/phone number of a person."""
    q = query.lower()
    return bool(re.search(r"\b(?:contact(?:\s+number|\s+details|\s+info|\s+no)?|phone(?:\s+number|\s+no)?|mobile(?:\s+number|\s+no)?|cell(?:\s+number|\s+no)?|telephone)\b", q, re.I))


def is_qualification_query(query: str) -> bool:
    """Return True if query explicitly asks about educational qualifications."""
    q = query.lower()
    return bool(re.search(r"\b(?:qualifications?|educational\s+qualifications?|degrees?|education)\b", q, re.I))


def extract_person_name(query: str) -> str:
    """Extract candidate person name by removing filler phrases, question words, and honorifics."""
    q = query.strip()

    # 1. Remove filler prefixes (including contact & qualification prefixes, and typos)
    filler_patterns = [
        r"^(?:what\s+is\s+)?(?:the\s+)?(?:contact(?:\s+number|\s+details|\s+no)?|phone(?:\s+number|\s+no)?|mobile(?:\s+number|\s+no)?|call\s+number|qualification[s]?)\s+(?:of|for|about)\s*",
        r"^(?:contact(?:\s+number|\s+details|\s+no)?|phone(?:\s+number|\s+no)?|mobile(?:\s+number|\s+no)?|qualification[s]?)\s+(?:of|for|about)\s*",
        r"^(?:can\s+you\s+)?(?:please\s+)?(?:give|show|tell|provide|get|find)\s+(?:me\s+)?(?:the\s+)?(?:details?|detailes?|detials?|info(?:rmation)?|profile|photo|picture|image|contact(?:\s+number)?|phone(?:\s+number)?)\s+(?:about|of|for)?\s*",
        r"^(?:give|show|tell|provide|get)\s+(?:me\s+)?(?:details?|detailes?|detials?|info(?:rmation)?)\s+(?:about|of|for)?\s*",
        r"^(?:who\s+is|who\s*'?s|who\s+was)\s+(?:the\s+)?(?:faculty\s+(?:named|called)?\s*)?",
        r"^(?:details?|detailes?|detials?|info(?:rmation)?|profile|photo|picture|image)\s+(?:about|of|for)\s*",
        r"^(?:show\s+photo\s+of|show\s+picture\s+of|show\s+image\s+of|picture\s+of|photo\s+of|image\s+of)\s*",
        r"^(?:about|tell\s+about)\s*",
    ]
    for pat in filler_patterns:
        q = re.sub(pat, "", q, flags=re.I).strip()

    # 2. Remove filler suffixes
    q = re.sub(r"\s+(?:details?|detailes?|detials?|info(?:rmation)?|profile|photo|picture|image|contact(?:\s+number)?|phone(?:\s+number)?|qualifications?|please)$", "", q, flags=re.I).strip()

    # 3. Strip honorifics
    q = re.sub(r"^(?:dr\.?|prof\.?|mr\.?|mrs\.?|ms\.?|sri\.?|smt\.?)\s+", "", q, flags=re.I).strip()

    # 4. Clean surrounding punctuation
    q = q.strip(" ?.!,:;\"'")
    return q


def classify_intent(query: str) -> tuple[str, str | None, str | None]:
    """Classify the user intent:
    
    Returns:
      (intent, dept_code, extracted_name)
      where intent is one of:
        - 'SMALLTALK'
        - 'DEPARTMENT_OVERVIEW'
        - 'CLUBS_QUERY'
        - 'FEE_STRUCTURE'
        - 'HOD_QUERY'
        - 'DEPARTMENT_FACULTY_LIST'
        - 'ALL_FACULTY'
        - 'FACULTY_CONTACT'
        - 'FACULTY_QUERY'
        - 'GENERAL'
    """
    q_raw = query.strip()
    q_lower = q_raw.lower()
    is_contact = is_contact_query(q_raw)
    is_qual = is_qualification_query(q_raw)

    # 0. Check for SMALLTALK first (instant greeting, bye, help, capabilities)
    smalltalk_set = {
        "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
        "thanks", "thank you", "bye", "goodbye", "who are you", "what can you do", "help"
    }
    q_clean_smalltalk = re.sub(r"[^a-zA-Z\s]", "", q_lower).strip()
    if q_clean_smalltalk in smalltalk_set:
        return "SMALLTALK", None, None

    # Fast check for Student Clubs
    if re.search(r"\b(?:clubs?|student\s+clubs?|technical\s+clubs?|cultural\s+clubs?|sports\s+clubs?)\b", q_lower) and not re.search(r"\b(?:dr\.?|prof\.?|mr\.?|mrs\.?)\b", q_raw, re.I):
        return "CLUBS_QUERY", None, None

    # Fast check for Fee Structure
    if re.search(r"\b(?:fee\s+structure|fees?\s+structure|tuition\s+fees?|fee\s+details|fees?\s+details|management\s+quota\s+fees?)\b", q_lower):
        return "FEE_STRUCTURE", None, None

    # Fast check for Admission Contact details
    if re.search(r"\b(?:admission\s+contact(?:\s+details)?|admission\s+office|admission\s+enquir(?:y|ies)|admission\s+phone(?:\s+number)?|admission\s+helpdesk|pro\s+contact|mtes\s+office)\b", q_lower):
        return "ADMISSION_CONTACT", None, None

    # Fast check for Eligibility criteria
    if re.search(r"\b(?:eligibility\s+criteria(?:\s+for\s+admission)?|admission\s+eligibility|eligibility\s+for\s+(?:b\.?e\.?|mca|m\.?tech|admission)|criteria\s+for\s+admission)\b", q_lower):
        return "ELIGIBILITY_CRITERIA", None, None

    # Fast check for Hostel Query (Boys hostel, Girls hostel, Hostels, Warden)
    if re.search(r"\b(?:hostels?|boys?\s+hostels?|girls?\s+hostels?|hostel\s+facilities|hostel\s+warden|hostel\s+rooms?|hostel\s+mess|hostel\s+food)\b", q_lower):
        return "HOSTEL_QUERY", None, None

    # Fast check for Placement Query
    if re.search(r"\b(?:placements?|placement\s+records?|placement\s+statistics|placement\s+cell|recruiting\s+companies|top\s+recruiters|companies\s+visiting|highest\s+package|average\s+package|placement\s+training|tpo|tap)\b", q_lower):
        return "PLACEMENT_QUERY", None, None

    # Fast check for Library Query
    if re.search(r"\b(?:library|central\s+library|digital\s+library|library\s+books|library\s+timings|librarian|easylib|reading\s+room|book\s+bank)\b", q_lower):
        return "LIBRARY_QUERY", None, None

    # Fast check for Scholarships Query
    if re.search(r"\b(?:scholarships?|financial\s+aid|fee\s+concession|fee\s+waiver|ssp|nsp|vidyasiri)\b", q_lower):
        return "SCHOLARSHIPS_QUERY", None, None

    # Fast check for Sports and Campus Facilities
    if re.search(r"\b(?:sports|games|gym|gymnasium|athletic|grounds?|canteen|cafeteria|campus\s+facilities|medical\s+facility|health\s+centre|transport|bus\s+facility)\b", q_lower):
        return "SPORTS_QUERY", None, None

    # Fast check for About MCE / History / Establishment
    if re.search(r"\b(?:about\s+mce|history\s+of\s+mce|when\s+was\s+mce\s+established|who\s+founded\s+mce|autonomous|accreditation|vtu\s+affiliation|naac|nba)\b", q_lower) and not re.search(r"\b(?:dr\.?|prof\.?)\b", q_raw, re.I):
        return "ABOUT_MCE_QUERY", None, None

    # Check for All Faculty query: e.g. "all faculty of mce", "faculty of all departments", "all faculty"
    if re.search(r"\b(?:all\s+faculty|faculty\s+of\s+all\s+departments?|all\s+teachers|all\s+professors)\b", q_lower, re.I):
        return "ALL_FACULTY", None, None

    # Check for M.Tech / PG faculty query
    if re.search(r"\b(?:m\.?tech|pg|post\s*graduate)\s+(?:faculty|staff|professors?|teachers?|members?)\b", q_lower, re.I) or q_lower.strip() in ["mtech faculty", "pg faculty", "faculty of mtech", "faculty of pg"]:
        return "DEPARTMENT_FACULTY_LIST", "MTECH", None

    # Check for Principal explicitly
    if re.search(r"\b(?:who\s+is\s+)?(?:the\s+)?principal\b", q_lower, re.I):
        if is_contact:
            return "FACULTY_CONTACT", "PRINCIPAL", "Dr. S. Pradeep"
        return "HOD_QUERY", "PRINCIPAL", "Dr. S. Pradeep"

    # Layered department detection via short_forms.py (with trailing punctuation cleaned)
    dept_code, canonical_dept = short_forms.detect_department(q_raw)

    # 1. HOD Query: mentions hod / head of department / head plus a department
    is_hod_mention = bool(re.search(r"\b(?:hod|h\.o\.d\.?|head\s+of\s+dept(?:artment)?|head\s+of|heads?)\b", q_lower, re.I))
    if is_hod_mention and dept_code:
        if is_contact:
            return "FACULTY_CONTACT", dept_code, f"{canonical_dept} HOD"
        return "HOD_QUERY", dept_code, None

    # Inverted HOD mention: "ise hod", "cse hod", "hod cse", "head of ise", "head of dept IS&E"
    if dept_code and (
        re.search(rf"\b{re.escape(dept_code.lower())}\s+hod\b", q_lower)
        or re.search(rf"\bhod\s+{re.escape(dept_code.lower())}\b", q_lower)
        or re.search(r"\bhead\s+of\s+dept\b", q_lower)
    ):
        if is_contact:
            return "FACULTY_CONTACT", dept_code, f"{canonical_dept} HOD"
        return "HOD_QUERY", dept_code, None

    # 2. Department Faculty List or Qualification List: "faculty of ise", "qualifications of first-year faculty members"
    is_list_mention = bool(re.search(r"\b(?:faculty|staff|professors?|teachers?|lecturers?|members?|list\s+of\s+faculty|all\s+faculty)\b", q_lower, re.I))
    has_honorific = bool(re.search(r"\b(?:dr\.?|prof\.?|mr\.?|mrs\.?|ms\.?|sri\.?|smt\.?)\b", q_raw, re.I))

    if (is_list_mention or is_qual) and dept_code and not has_honorific:
        return "DEPARTMENT_FACULTY_LIST", dept_code, None

    # 3. Department Overview: "overview of ise department", "tell me about mathematics department", "mechanical department"
    is_overview_word = bool(re.search(r"\b(?:overview|about|tell\s+me\s+about|explain|details\s+of|info(?:rmation)?\s+about|department|dept|branch|program|programs?)\b", q_lower))
    if dept_code and not is_hod_mention and not is_list_mention and not has_honorific:
        # If overview word is present or query is short (e.g. "mathematics department", "ise", "cse branch")
        if is_overview_word or len(q_lower.split()) <= 4:
            return "DEPARTMENT_OVERVIEW", dept_code, canonical_dept

    # 3. Faculty Person Query or Contact Query
    extracted_name = extract_person_name(q_raw)

    # Exclude broad non-person college topics from being treated as faculty names
    non_person_keywords = {
        "mce", "college", "malnad", "placement", "placements", "plcmt", "tnp", "tap",
        "fee", "fees", "hostel", "admission", "admissions", "admn", "cutoff", "cut off",
        "syllabus", "curriculum", "courses", "library", "scholarship", "exam", "exams",
        "results", "sports", "canteen", "bus", "transport", "facilities", "ranking",
        "vision", "mission", "history", "about", "what", "where", "how", "when",
        "first", "year", "engineering", "department", "program", "branch", "stats",
        "contact", "contacts", "details", "office", "mtes", "number", "numbers",
        "info", "general", "helpdesk", "enquiry", "inquiry", "pro", "criteria",
        "eligibility", "club", "clubs"
    }

    words = set(re.findall(r"\b[a-z]+\b", extracted_name.lower()))
    q_words = set(re.findall(r"\b[a-z]+\b", q_lower))

    # Organizational / general college topics must NEVER be treated as faculty contact queries
    org_contact_keywords = {
        "admission", "admissions", "admn", "office", "mtes", "college", "hostel", "hostels",
        "placement", "placements", "exam", "exams", "examination", "library", "general",
        "helpdesk", "enquiry", "inquiry", "pro", "fee", "fees", "tuition", "course", "courses",
        "club", "clubs", "eligibility", "criteria"
    }
    if not has_honorific and (words.intersection(org_contact_keywords) or q_words.intersection(org_contact_keywords)):
        return "GENERAL", None, None

    if words and words.issubset(non_person_keywords) and not has_honorific:
        return "GENERAL", None, None

    if is_contact and extracted_name and len(extracted_name) >= 3:
        return "FACULTY_CONTACT", None, extracted_name

    if has_honorific:
        return "FACULTY_QUERY", None, extracted_name

    # Check if query starts with person lookup phrases
    person_lead = bool(re.search(r"^(?:who\s+is|who\s*'?s|show\s+photo\s+of|profile\s+of|photo\s+of|give\s+details?\s+about|details?\s+about|tell\s+me\s+about)\s+", q_lower, re.I))
    if person_lead and len(extracted_name) >= 3 and not (dept_code and len(words) == 1):
        return "FACULTY_QUERY", None, extracted_name

    # Short 1-4 word queries that might be a name (e.g. "anand babu", "anand bab", "kalavati k")
    if 1 <= len(extracted_name.split()) <= 4 and len(extracted_name) >= 3:
        if not words.intersection(non_person_keywords) and not (dept_code and len(words) == 1):
            return "FACULTY_QUERY", None, extracted_name

    return "GENERAL", None, None


def get_department_hod(dept_code: str) -> dict[str, Any]:
    """Retrieve HOD information using hod_verified.json as authoritative single source of truth."""
    import hod_manager
    canonical_dept = short_forms.get_department_index().get(dept_code.upper(), {}).get("canonical", dept_code)
    code_up = dept_code.upper().strip()

    # Special check for Principal
    if code_up == "PRINCIPAL":
        profiles = get_all_profiles()
        for p in profiles:
            if "principal" in p.get("designation", "").lower():
                title = f"{p['name']} - Principal of MCE"
                msg = ui_cards.format_cards_markdown([p], title=title, show_phone=False)
                return {
                    "handled": True,
                    "status": "found",
                    "type": "faculty_single",
                    "title": title,
                    "dept_name": "Principal of MCE",
                    "person": p,
                    "show_phone": False,
                    "photo_path": p.get("photo_path"),
                    "message": msg,
                }

    # 1. Read hod_verified.json FIRST
    v_hod = hod_manager.get_verified_hod(dept_code)
    if v_hod:
        if v_hod.get("status") == "not_offered":
            msg = v_hod.get("message", f"Faculty details for {canonical_dept} are not listed in the documents because MCE does not offer this program.")
            return {
                "handled": True,
                "status": "not_offered",
                "type": "faculty_not_offered",
                "dept_name": v_hod.get("canonical_name", canonical_dept),
                "message": msg,
            }

        profiles = get_all_profiles()
        norm_name = normalize_name_key(v_hod["hod_name"])
        matched_p = None
        for p in profiles:
            p_norm = p.get("normalized_name", "")
            if norm_name == p_norm or norm_name in p_norm or p_norm in norm_name:
                matched_p = p
                break

        hod_person = dict(matched_p) if matched_p else dict(v_hod)
        hod_person["name"] = v_hod["hod_name"]
        hod_person["designation"] = v_hod["designation"]
        # Retain person's own department; fallback to canonical if not present
        if not hod_person.get("department"):
            hod_person["department"] = v_hod["canonical_name"]
        if v_hod.get("qualification"):
            hod_person["qualification"] = v_hod["qualification"]
        if v_hod.get("photo_path") and Path(v_hod["photo_path"]).exists():
            hod_person["photo_path"] = v_hod["photo_path"]
        if v_hod.get("email"):
            hod_person["email"] = v_hod["email"]
        if v_hod.get("phone"):
            hod_person["phone"] = v_hod["phone"]

        # Assert: person belongs to resolved department (or coordinator for FIRST_YEAR / CADS / PES / AIDS)
        p_dept = (hod_person.get("department") or "").lower()
        can_dept = canonical_dept.lower()
        code_str = code_up.lower()
        dept_match = (
            code_str in p_dept
            or can_dept in p_dept
            or (code_up == "FIRST_YEAR" and ("mathematics" in p_dept or "first year" in p_dept))
            or (code_up == "RAI" and "artificial intelligence" in p_dept)
            or (code_up == "DECS" and ("digital electronics" in p_dept or "electronics" in p_dept))
            or (code_up == "CADS" and ("civil" in p_dept or "design" in p_dept or "structures" in p_dept))
            or (code_up == "PES" and ("electrical" in p_dept or "power" in p_dept))
            or (code_up == "AIDS" and "artificial intelligence" in p_dept)
        )
        if not dept_match:
            msg = f"The HOD of {canonical_dept} is not listed in the documents."
            return {
                "handled": True,
                "status": "not_listed",
                "type": "faculty_not_listed",
                "dept_name": canonical_dept,
                "message": msg,
            }

        title = f"Head of Department, {v_hod['canonical_name']}"
        msg = ui_cards.format_cards_markdown([hod_person], title=title, show_phone=False)
        return {
            "handled": True,
            "status": "found",
            "type": "faculty_single",
            "title": title,
            "dept_name": v_hod["canonical_name"],
            "person": hod_person,
            "show_phone": False,
            "photo_path": hod_person.get("photo_path"),
            "message": msg,
        }

    # 2. Fall back to extracted data ONLY if department is missing from hod_verified.json
    # In that case, verify designation strictly contains HOD/Head AND department matches.
    # Never return the "most senior" or "first" person as the HOD.
    profiles = get_all_profiles()
    hod_candidates = []
    for p in profiles:
        p_dept = p.get("department", "").lower()
        p_desig = p.get("designation", "").lower()
        if (dept_code.lower() in p_dept or canonical_dept.lower() in p_dept) and (
            "hod" in p_desig or "head of department" in p_desig
        ):
            hod_candidates.append(p)

    if hod_candidates:
        hod_person = hod_candidates[0]
        title = f"Head of Department, {canonical_dept}"
        msg = ui_cards.format_cards_markdown([hod_person], title=title, show_phone=False)
        return {
            "handled": True,
            "status": "found",
            "type": "faculty_single",
            "title": title,
            "dept_name": canonical_dept,
            "person": hod_person,
            "show_phone": False,
            "photo_path": hod_person.get("photo_path"),
            "message": msg,
        }

    return {
        "handled": False,
        "status": "not_found",
        "message": f"HOD information for the Department of {canonical_dept} is currently not available in college records.",
    }


def get_department_faculty_list(dept_code: str) -> dict[str, Any]:
    """Retrieve all faculty members for a department or program, sorted by seniority."""
    code_up = dept_code.upper().strip()
    canonical_dept = short_forms.get_department_index().get(code_up, {}).get("canonical", dept_code)
    profiles = get_all_profiles()

    # 1. MBA handling
    if code_up == "MBA":
        msg = "Faculty details for Master of Business Administration (MBA) are not listed in the documents because MCE Hassan does not offer an MBA program."
        return {
            "handled": True,
            "status": "not_offered",
            "type": "faculty_not_offered",
            "dept_name": "Master of Business Administration",
            "message": msg,
        }

    # 2. M.Tech / PG aggregate handling
    if code_up in ["MTECH", "PG"]:
        mtech_depts = [
            "Computer Aided Design of Structures (CADS)",
            "Digital Electronics and Communication Systems (DECS)",
            "Power and Energy Systems (PES)",
            "Artificial Intelligence and Data Science (AIDS)",
        ]
        matching_faculty = [
            p for p in profiles
            if any(md in p.get("department", "") for md in mtech_depts)
            or ("balaji" in p.get("name", "").lower() and "prabhu" in p.get("name", "").lower())
        ]
        sorted_fac = ui_cards.sort_faculty_list(matching_faculty)
        title = f"Postgraduate (M.Tech) Programmes: {len(sorted_fac)} faculty"
        msg = ui_cards.format_cards_markdown(sorted_fac, title=title, show_phone=False)
        return {
            "handled": True,
            "status": "found",
            "type": "faculty_list",
            "title": title,
            "dept_name": "Postgraduate Programmes",
            "faculty_list": sorted_fac,
            "show_phone": False,
            "message": msg,
        }

    # 3. First-Year handling
    if code_up in ["FIRST_YEAR", "FY"]:
        seen_names = set()
        matching_faculty = []
        for p in profiles:
            p_dept = p.get("department", "").lower()
            if any(k in p_dept for k in ["first-year", "first year", "mathematics", "physics", "chemistry"]):
                norm_n = normalize_name_key(p["name"])
                if norm_n not in seen_names:
                    seen_names.add(norm_n)
                    matching_faculty.append(p)
        sorted_fac = ui_cards.sort_faculty_list(matching_faculty)
        title = f"First-Year Department Faculty Qualifications and Directory: {len(sorted_fac)} faculty"
        msg = ui_cards.format_cards_markdown(sorted_fac, title=title, show_phone=False)
        return {
            "handled": True,
            "status": "found",
            "type": "faculty_list",
            "title": title,
            "dept_name": "First-Year Department",
            "faculty_list": sorted_fac,
            "show_phone": False,
            "message": msg,
        }

    # 4. Standard department / program handling (CADS, DECS, PES, AIDS, MCA, ISE, CSE, etc.)
    matching_faculty = []
    seen_names = set()
    is_aids_query = code_up in ["AIDS", "AI_DS"] or "data science" in canonical_dept.lower()
    for p in profiles:
        p_dept = p.get("department", "").lower()
        matches = dept_code.lower() in p_dept or canonical_dept.lower() in p_dept
        if not matches and is_aids_query:
            extra_info = (p.get("other_details", "") + " " + p.get("specialization", "")).lower()
            if "aids" in extra_info or "artificial intelligence" in extra_info:
                matches = True
        if matches:
            norm_n = normalize_name_key(p["name"])
            if norm_n not in seen_names:
                seen_names.add(norm_n)
                matching_faculty.append(p)

    if not matching_faculty:
        return {
            "handled": True,
            "status": "not_listed",
            "type": "faculty_not_listed",
            "dept_name": canonical_dept,
            "message": f"Faculty details for {canonical_dept} are not listed in the documents.",
        }

    sorted_fac = ui_cards.sort_faculty_list(matching_faculty)
    title = f"{canonical_dept}: {len(sorted_fac)} faculty"
    msg = ui_cards.format_cards_markdown(sorted_fac, title=title, show_phone=False)
    return {
        "handled": True,
        "status": "found",
        "type": "faculty_list",
        "title": title,
        "dept_name": canonical_dept,
        "faculty_list": sorted_fac,
        "show_phone": False,
        "message": msg,
    }


def get_all_departments_directory() -> dict[str, Any]:
    """Retrieve full college faculty directory grouped by department."""
    profiles = get_all_profiles()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for p in profiles:
        dept = p.get("department") or "Other"
        grouped[dept].append(p)

    lines = ["### Malnad College of Engineering - All Departments Directory\n"]
    for dept, fac in grouped.items():
        lines.append(f"#### {dept} ({len(fac)} faculty)")
        for person in ui_cards.sort_faculty_list(fac):
            lines.append(f"- **{person['name']}** - {person.get('designation', 'Faculty')}")
        lines.append("")

    return {
        "handled": True,
        "status": "found",
        "type": "faculty_all",
        "grouped_faculty": dict(grouped),
        "show_phone": False,
        "message": "\n".join(lines),
    }


def find_person_profile(extracted_name: str, profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """Helper to match a person name against cached profiles."""
    norm_target = normalize_name_key(extracted_name)

    matches: list[tuple[dict, float]] = []
    target_tokens = set(re.findall(r"\b[a-z0-9]+\b", extracted_name.lower()))

    for p in profiles:
        p_name = p.get("name", "")
        norm_p = normalize_name_key(p_name)
        p_tokens = set(re.findall(r"\b[a-z0-9]+\b", p_name.lower()))

        # Exact key match
        if norm_target == norm_p:
            matches.append((p, 100.0))
            continue

        # Substring match on full canonical key
        if len(norm_target) >= 5 and (norm_target in norm_p or norm_p in norm_target):
            matches.append((p, 95.0))
            continue

        # Token overlap & prefix matching (e.g. "anand babu" vs "Dr. Ananda Babu J")
        token_matches = 0
        for t in target_tokens:
            if any(t == pt or (len(t) >= 4 and pt.startswith(t)) or (len(pt) >= 4 and t.startswith(pt)) for pt in p_tokens):
                token_matches += 1
        if len(target_tokens) > 0 and token_matches == len(target_tokens):
            matches.append((p, 92.0))
            continue

        # Fuzzy similarity on clean names
        clean_p = re.sub(r"\b(?:dr\.?|prof\.?|mr\.?|mrs\.?|ms\.?|sri\.?|smt\.?)\s+", "", p_name.lower()).strip()
        clean_t = re.sub(r"\b(?:dr\.?|prof\.?|mr\.?|mrs\.?|ms\.?|sri\.?|smt\.?)\s+", "", extracted_name.lower()).strip()
        score = max(
            fuzz.token_sort_ratio(clean_t, clean_p),
            fuzz.ratio(clean_t, clean_p),
            fuzz.partial_ratio(clean_t, clean_p) if len(clean_t) >= 5 else 0,
        )
        if score >= 80:
            matches.append((p, float(score)))

    if not matches:
        return {"status": "not_found"}

    matches.sort(key=lambda x: x[1], reverse=True)
    top_score = matches[0][1]
    top_candidates = [m[0] for m in matches if m[1] >= max(80.0, top_score - 4)]

    # Deduplicate by canonical key
    unique_candidates: list[dict] = []
    seen_cand = set()
    for cand in top_candidates:
        ck = normalize_name_key(cand["name"])
        if ck not in seen_cand:
            seen_cand.add(ck)
            unique_candidates.append(cand)

    if len(unique_candidates) == 1:
        return {"status": "found", "person": unique_candidates[0]}
    else:
        return {"status": "ambiguous", "candidates": unique_candidates}


def format_dept_heading(canonical: str) -> str:
    """Build the title from the official name and add 'Department of ' only if the name doesn't already start with 'Department'."""
    c = canonical.strip()
    if c.lower().startswith("department"):
        return c
    return f"Department of {c}"


def get_smalltalk_response() -> dict[str, Any]:
    """Instant friendly smalltalk response listing bot capabilities and 4 example questions."""
    msg = (
        "Hello! 👋 I am the **MCE AI Assistant**, your official guide to Malnad College of Engineering (MCE), Hassan.\n\n"
        "Here is what I can help you with:\n"
        "- 🏛️ **Department Overviews & Programmes** (e.g. ISE, CSE, AIML, Mechanical, Civil)\n"
        "- 👨‍🏫 **Head of Departments (HODs)** & Verified Faculty Profiles with Photos\n"
        "- 🎓 **Admissions & Eligibility Criteria** (KCET, COMEDK, Management Quota)\n"
        "- 💰 **Fee Structure & Scholarships** (SSP, NSP, Fee concessions)\n"
        "- 💼 **Training & Placements** (Recruiters, Placement statistics)\n"
        "- 🎪 **Student Clubs & Campus Facilities** (Eco Club, Leo Club, LIT, Hostels, Sports)\n\n"
        "**Try asking:**\n"
        "1. *Overview of ISE department*\n"
        "2. *Who is the HOD of CSE?*\n"
        "3. *What are the clubs at MCE?*\n"
        "4. *Tell me about the fee structure*"
    )
    return {
        "handled": True,
        "status": "smalltalk",
        "type": "faculty_smalltalk",
        "message": msg,
    }


def get_department_overview(dept_code: str) -> dict[str, Any]:
    """Retrieve precomputed department overview with single clean heading, sections, verified HOD card, and faculty offer."""
    code_up = dept_code.upper().strip()
    overviews_path = BASE_DIR / "department_overviews.json"
    data = {}
    if overviews_path.exists():
        try:
            with open(overviews_path, "r", encoding="utf-8") as f:
                all_overviews = json.load(f)
                data = all_overviews.get(code_up, {})
        except Exception:
            pass

    if not data:
        return {"handled": False}

    canonical = data.get("official_name") or data.get("canonical_name") or code_up
    heading = format_dept_heading(canonical)

    overview_lines = [f"## {heading}\n"]

    if data.get("about"):
        overview_lines.append(f"### About\n{data['about']}\n")
    if data.get("vision"):
        overview_lines.append(f"### Vision\n{data['vision']}\n")
    if data.get("mission"):
        overview_lines.append(f"### Mission\n{data['mission']}\n")
    if data.get("programs_offered"):
        overview_lines.append(f"### Programmes Offered\n{data['programs_offered']}\n")
    if data.get("labs_and_facilities"):
        overview_lines.append(f"### Labs & Facilities\n{data['labs_and_facilities']}\n")
    if data.get("achievements"):
        overview_lines.append(f"### Key Achievements\n{data['achievements']}\n")

    overview_markdown = "\n".join(overview_lines)

    # Get verified HOD
    hod_res = get_department_hod(code_up)
    hod_person = hod_res.get("person") if hod_res.get("handled") else None
    if hod_person and not hod_person.get("department"):
        hod_person["department"] = canonical

    # Footer markdown: faculty count offer + source
    footer_lines = []
    profiles = get_all_profiles()
    fac_count = len([p for p in profiles if p.get("department_code") == code_up or canonical.lower() in p.get("department", "").lower()])
    if fac_count > 0:
        footer_lines.append(f"💡 *The {heading} has **{fac_count} verified faculty members**. Ask `'faculty of {dept_code.lower()}'` to view all faculty profiles with photographs.*")

    src_file = data.get("source_file", "overview of mce.pdf")
    src_page = data.get("source_page")
    page_str = f", Page {src_page}" if src_page else ""
    footer_lines.append(f"\n*[Source: {src_file}{page_str}]*")
    footer_markdown = "\n\n".join(footer_lines)

    # Build full markdown message for CLI and stream consumers
    full_lines = [overview_markdown]
    if hod_person:
        full_lines.append(ui_cards.format_cards_markdown([hod_person], title=f"Head of Department ({heading})"))
    full_lines.append(footer_markdown)
    full_message = "\n\n".join(full_lines)

    return {
        "handled": True,
        "status": "found",
        "type": "faculty_department_overview",
        "dept_name": canonical,
        "heading": heading,
        "person": hod_person,
        "photo_path": hod_person.get("photo_path") if hod_person else None,
        "overview_markdown": overview_markdown,
        "footer_markdown": footer_markdown,
        "message": full_message,
    }


def get_clubs_response() -> dict[str, Any]:
    """Retrieve verified student clubs from clubs.json / overview of mce.pdf."""
    clubs_file = BASE_DIR / "clubs.json"
    clubs_data = []
    if clubs_file.exists():
        try:
            with open(clubs_file, "r", encoding="utf-8") as f:
                clubs_data = json.load(f)
        except Exception:
            pass

    lines = [
        "## Student Clubs at Malnad College of Engineering (MCE), Hassan\n",
        "The college encourages a vibrant campus life through a wide variety of technical, cultural, environmental, and service clubs:\n"
    ]

    for c in clubs_data:
        c_name = c.get("name", "Club")
        lines.append(f"### {c_name}")
        if c.get("category"):
            lines.append(f"**Category:** {c['category']}")
        if c.get("motto"):
            lines.append(f"**Motto:** *\"{c['motto']}\"*")
        if c.get("description"):
            lines.append(f"{c['description']}")
        if c.get("flagship_events"):
            lines.append(f"**Flagship Events:** {c['flagship_events']}")
        if c.get("activities"):
            lines.append("**Key Activities:**")
            for act in c["activities"][:3]:
                lines.append(f"- {act}")
        if c.get("website") and "http" in c.get("website", ""):
            lines.append(f"**Website:** {c['website']}")
        lines.append("")

    lines.append("*[Source: overview of mce.pdf, Pages 10-22]*")
    msg = "\n".join(lines)

    return {
        "handled": True,
        "status": "clubs",
        "type": "faculty_clubs",
        "message": msg,
    }


def get_admission_contact_response() -> dict[str, Any]:
    """Retrieve verified admission contact details from overview of mce.pdf (Page 48)."""
    lines = [
        "## MCE Admission Contact Details\n",
        "Official admission and institutional contact details for Malnad College of Engineering (MCE), Hassan:\n",
        "- **MTES Office:** `08172-268371`",
        "- **Principal's Office:** `08172-245317`",
        "- **Dean - Student Affairs:** `9449689093`",
        "- **Admission Enquiry / PRO:** `9141305843`",
        "- **Official Email:** [office@mcehassan.ac.in](mailto:office@mcehassan.ac.in)",
        "- **College Address:** No. 21, Salagame Road, Rangoli Halla, Hassan, Karnataka - 573202\n",
        "### Official Admission Portals & Links",
        "- [MCE Admission Process 2026-27](https://www.mcehassan.ac.in)",
        "- [MCE Management Admission Portal](https://www.mcehassan.ac.in)",
        "- [MCE Admission Enquiry](https://www.mcehassan.ac.in)",
        "- [Karnataka Examinations Authority (KEA)](https://cetonline.karnataka.gov.in/kea/)",
        "- [COMEDK Official Website](https://www.comedk.org)\n",
        "*[Source: overview of mce.pdf, Page 48]*"
    ]
    msg = "\n".join(lines)
    return {
        "handled": True,
        "status": "admission_contact",
        "type": "faculty_admission_contact",
        "message": msg,
    }


def get_eligibility_criteria_response() -> dict[str, Any]:
    """Retrieve verified admission eligibility criteria from overview of mce.pdf (Pages 50-51)."""
    lines = [
        "## Eligibility Criteria for Admission to MCE Hassan (2026-27)\n",
        "According to official admission records, eligibility requirements depend on the programme and entry route:\n",
        "### 1. Undergraduate (B.E.) Programmes",
        "- **Educational Qualification:** Pass 2nd PUC, Class 12, or an equivalent qualifying examination.",
        "- **Compulsory Subjects:** Physics and Mathematics, along with Chemistry / Bio-Technology / Biology / Computer Science / Electronics.",
        "- **Minimum Marks:** Minimum of **45% aggregate** in compulsory subjects for General Category candidates, and **40% aggregate** for Karnataka SC/ST/OBC category candidates.",
        "- **Admission Routes:** KCET (KEA quota), COMEDK UGET, or Management Quota.\n",
        "### 2. Diploma Lateral Entry (Direct 2nd Year B.E.)",
        "- **Qualification:** 3-year diploma in a relevant engineering discipline recognized by the state board.",
        "- **Minimum Marks:** Minimum **45% marks** for General Merit (40% for eligible reserved categories).",
        "- **Admission Route:** D-CET counselling through KEA.\n",
        "### 3. Postgraduate M.Tech Programmes",
        "- **Qualification:** Relevant B.E./B.Tech degree or equivalent qualification.",
        "- **Minimum Marks:** Prescribed qualifying aggregate/CGPA by VTU/Government.",
        "- **Admission Route:** Valid Karnataka PGCET or GATE score followed by counselling.\n",
        "### 4. Master of Computer Applications (MCA)",
        "- **Qualification:** Recognized Bachelor's degree with Mathematics at 10+2 level or degree level.",
        "- **Minimum Marks:** Prescribed qualifying aggregate (50% for GM, 45% for reserved categories).",
        "- **Admission Route:** Valid PGCET score or MCE MCA selection test.\n",
        "### 5. Management Quota Admissions",
        "- Candidates must satisfy academic eligibility requirements. Applications are processed directly through the **MTES Office** in Hassan.\n",
        "*[Source: overview of mce.pdf, Pages 50-51]*"
    ]
    msg = "\n".join(lines)
    return {
        "handled": True,
        "status": "eligibility",
        "type": "faculty_eligibility",
        "message": msg,
    }


def get_fee_structure_response() -> dict[str, Any]:
    """Retrieve official 2026-27 fee structure from overview of mce.pdf."""
    lines = [
        "## Malnad College of Engineering (MCE) - Fee Structure (2026-27)\n",
        "According to the official 2026-27 management quota fee notice and admission documents published by Malnad College of Engineering (MCE), Hassan:\n",
        "### 1. Management Quota Annual Tuition Fees (First-Year B.E. & MCA)",
        "| No. | Course / Branch | Listed Annual Fee (Rs. ) |",
        "| :--- | :--- | :--- |",
        "| 1 | Civil Engineering | Rs. 1,25,000 |",
        "| 2 | Mechanical Engineering | Rs. 1,25,000 |",
        "| 3 | Electrical & Electronics Engineering (EEE) | Rs. 1,25,000 |",
        "| 4 | Electronics & Instrumentation Engineering (EIE) | Rs. 1,25,000 |",
        "| 5 | Electronics & Communication Engineering (ECE) | Rs. 2,25,000 |",
        "| 6 | Computer Science & Engineering (CSE) | Rs. 2,50,000 |",
        "| 7 | Information Science & Engineering (ISE) | Rs. 2,50,000 |",
        "| 8 | Artificial Intelligence & Machine Learning (AIML) | Rs. 2,50,000 |",
        "| 9 | Computer Science & Business Systems (CSBS) | Rs. 2,25,000 |",
        "| 10 | Master of Computer Applications (MCA) | Rs. 1,25,000 |\n",
        "### 2. Government & Entrance Quota Fees (KCET & COMEDK)",
        "- **KCET / KEA Quota:** Prescribed by the Government of Karnataka / KEA at the time of counselling (Aided: Rs. 44,200, Unaided: Rs. 1,12,410 first-year).",
        "- **COMEDK Quota:** Prescribed by the COMEDK authority under the private engineering college consortium notification.\n",
        "### 3. Scholarships & Fee Concessions",
        "- **State Scholarship Portal (SSP):** Post-matric scholarships for SC/ST/OBC/Minority students.",
        "- **National Scholarship Portal (NSP):** Central government merit-cum-means scholarships.",
        "- **Alumni & Merit Scholarships:** Offered through MTES for deserving students.\n",
        "### 4. Admission Office & MTES Contact",
        "- **MTES Office:** `08172-268371`",
        "- **Principal's Office:** `08172-245317`",
        "- **Dean - Student Affairs:** `9449689093`",
        "- **Admission Enquiry / PRO:** `9141305843` | **Email:** [office@mcehassan.ac.in](mailto:office@mcehassan.ac.in)\n",
        "*[Source: overview of mce.pdf, Pages 48, 52]*"
    ]
    msg = "\n".join(lines)
    return {
        "handled": True,
        "status": "fee_structure",
        "type": "faculty_fee_structure",
        "message": msg,
    }


def get_hostel_response(query: str) -> dict[str, Any]:
    """Retrieve verified hostel details from official college documents."""
    q_lower = query.lower()
    is_boys = bool(re.search(r"\b(?:boys?|male|men)\b", q_lower))
    is_girls = bool(re.search(r"\b(?:girls?|female|women|ladies)\b", q_lower))

    if is_boys and not is_girls:
        lines = [
            "## 🏢 MCE Boys' Hostel Facilities",
            "Malnad College of Engineering (MCE), Hassan provides dedicated on-campus residential facilities for male students:\n",
            "### Overview & Purpose",
            "- **Establishment:** Established in **1961**.",
            "- **Purpose:** Provides secure, comfortable accommodation for outstation students pursuing degree programmes at MCE Hassan.\n",
            "### Capacity & Residential Blocks",
            "- **Capacity:** Approximately **600–650 students** across **324 rooms**.",
            "- **Hostel Blocks:** Three major residential blocks:",
            "  1. **Hoysala Block**",
            "  2. **Hemavathi Block**",
            "  3. **Hasanamba Block**",
            "- **Room Furnishings:** Each room is furnished with cots, study tables, chairs, and ceiling fans.\n",
            "### Dining & Food Services",
            "- **Modern Kitchen & Dining:** Hygienic dining hall accommodating approximately **260 students** simultaneously.",
            "- **Cuisine:** Wholesome, nutritious vegetarian and non-vegetarian meals prepared in clean, modern kitchen facilities.\n",
            "### Amenities & Infrastructure",
            "- **Water Supply:** 24-hour uninterrupted water supply with Aquaguard-filtered drinking water.",
            "- **Hot Water:** Hot water facilities available for bathing.",
            "- **Power Backup:** Dedicated generator facility ensuring continuous electricity.",
            "- **Internet Connectivity:** Internet browsing centre for academic use and project work.",
            "- **Recreation:** Two TV entertainment rooms and indoor game facilities (Table Tennis, Carrom, Chess).",
            "- **Discipline & Safety:** 24/7 campus security personnel and a strictly **ragging-free environment**.\n",
            "### 📞 Hostel Administration & Warden Contacts",
            "- **Hostel Warden:** **Prof. G. Manjunath**",
            "- **Additional Contact:** **Dr. Madhu K. S.** — `9738282552` / `9141305847`",
            "- **Email:** [mks@mcehassan.ac.in](mailto:mks@mcehassan.ac.in)",
        ]
    elif is_girls and not is_boys:
        lines = [
            "## 🏢 MCE Girls' Hostel Facilities",
            "Malnad College of Engineering (MCE), Hassan provides dedicated, secure residential accommodations for female students:\n",
            "### Overview & Purpose",
            "- **Establishment:** Established in **1990**.",
            "- **Location:** Located in a secure building outside the main campus.",
            "- **Purpose:** Provides a supportive, safe, and homely atmosphere for female students.\n",
            "### Accommodation & Building Structure",
            "- **Capacity:** Approximately **250 female students**.",
            "- **Structure:** Well-maintained four-storey building.",
            "- **Boarding & Lodging:** Complete residential and catering arrangements under institutional care.\n",
            "### Amenities & Facilities",
            "- **Internet:** High-speed Wi-Fi connectivity throughout the hostel premises.",
            "- **Transportation:** Dedicated college bus facility providing hassle-free transit between the hostel and college campus.",
            "- **Dining:** Hygienic kitchen providing fresh, nutritious meals.",
            "- **Safety & Supervision:** Supervised by **two resident wardens** with round-the-clock security and a zero-tolerance ragging policy.\n",
            "### 📞 Girls' Hostel Contacts",
            "- **Landline:** `08172-269234`",
            "- **Mobile:** `9480885317`",
        ]
    else:
        lines = [
            "## 🏢 MCE Hostel Facilities (Boys' & Girls' Hostels)",
            "Malnad College of Engineering (MCE), Hassan provides separate, comfortable, and highly secure hostel facilities for male and female students:\n",
            "### 1. Boys' Hostel (On-Campus)",
            "- **Established:** 1961",
            "- **Capacity:** ~600–650 students in 324 rooms across 3 blocks (**Hoysala**, **Hemavathi**, and **Hasanamba**).",
            "- **Facilities:** Furnished rooms (cots, tables, chairs, fans), 260-seat modern dining hall, 24-hr water, Aquaguard drinking water, hot water, generator power backup, internet browsing centre, two TV rooms, and indoor games.",
            "- **Warden Contact:** Prof. G. Manjunath | **Additional Contact:** Dr. Madhu K. S. (`9738282552` / `9141305847`) | **Email:** [mks@mcehassan.ac.in](mailto:mks@mcehassan.ac.in)\n",
            "### 2. Girls' Hostel",
            "- **Established:** 1990",
            "- **Location:** Dedicated residential building outside the main campus.",
            "- **Capacity:** Approximately 250 female students in a four-storey building.",
            "- **Facilities:** Complete boarding and lodging, Wi-Fi connectivity, dedicated college bus transport facility to/from campus, and two resident wardens.",
            "- **Contact:** Landline `08172-269234` | Mobile `9480885317`\n",
            "### 3. Comparison Overview",
            "| Facility | Boys' Hostel | Girls' Hostel |",
            "| :--- | :--- | :--- |",
            "| **Location** | On Campus | Outside Main Campus |",
            "| **Capacity** | 600–650 students | ~250 students |",
            "| **Rooms/Structure** | 324 rooms (3 blocks) | Four-storey building |",
            "| **Internet** | Browsing Centre | Wi-Fi Connectivity |",
            "| **Transport** | Walking distance on campus | Dedicated college bus facility |",
            "| **Supervision** | Warden & Resident Staff | Two Resident Wardens |",
            "| **Safety** | 24/7 Security & Ragging-free | 24/7 Security & Ragging-free |",
        ]

    msg = "\n".join(lines)
    return {
        "handled": True,
        "status": "hostel",
        "type": "faculty_hostel",
        "message": msg,
    }


def get_placement_response(query: str) -> dict[str, Any]:
    """Retrieve verified placement information and statistics from official records."""
    lines = [
        "## 💼 Training & Placement Department — MCE Hassan",
        "The **Department of Training & Placement** at Malnad College of Engineering (established in the early 1990s) provides rigorous placement training, industry tie-ups, and campus recruitment opportunities for students:\n",
        "### 📈 Placement Records & Statistics",
        "- **Academic Year 2024–25:** **455 total offers** reported in the placement report.",
        "- **Academic Year 2023–24:** **334 total offers** reported in the placement report.",
        "- **Trend:** Consistent recruitment year-on-year across circuit branches, core engineering branches, and postgraduate programmes (MCA).\n",
        "### 🏢 Major Recruiting Companies",
        "Prominent national and multinational companies that actively recruit from MCE Hassan include:",
        "- **IT & Technology:** Tata Consultancy Services (TCS), Infosys, Wipro, Accenture, IBM, Tech Mahindra, Mindtree",
        "- **Core & Automotive:** Mercedes-Benz, Robert Bosch, Toyota Kirloskar, Toshiba, Bharat Electronics Limited (BEL), Larsen & Toubro (L&T)",
        "- *Recruiting partners vary annually based on industry hiring cycles.*\n",
        "### 🎯 Training & Employability Initiatives",
        "- **Aptitude Training:** Intensive coaching on quantitative aptitude, logical reasoning, and verbal ability.",
        "- **Communication & Soft Skills:** Professional English, personality development, mock group discussions, and personal interview coaching.",
        "- **Programming Courses:** Hands-on C and C++ crash courses for non-circuit engineering branches.",
        "- **Technical Preparation:** Curated aptitude question banks, interview coding puzzles, and industry-oriented workshops.",
        "- **Higher Education Guidance:** Advisory support for competitive exams including GATE, GRE, TOEFL, and IELTS.\n",
        "### 📝 6-Step Placement Process",
        "1. **Student Registration:** Enrolment commences at the start of the 6th semester.",
        "2. **Orientation:** Briefing on corporate expectations and placement guidelines.",
        "3. **Skill Development:** Pre-placement aptitude and technical training sessions.",
        "4. **Company Drive Enrolment:** Eligible candidates apply for specific visiting companies.",
        "5. **Selection Rounds:** Written/Online aptitude tests, technical interviews, and HR rounds.",
        "6. **Final Offer:** Issuance of official offer letters by recruiting firms.\n",
        "### 📞 Training & Placement Office Contacts",
        "- **Dean (Corporate Affairs):** **Dr. Geetha Kiran A** — [deanca@mcehassan.ac.in](mailto:deanca@mcehassan.ac.in)",
        "- **Training and Placement Officer (TPO):** **Dr. Jeevan T. P.** — [tap@mcehassan.ac.in](mailto:tap@mcehassan.ac.in)",
        "- **Placement Phone:** `+91 9743448889` / `+91 9141305846`",
        "- **Office Location:** Training & Placement Block, MCE Hassan Campus.",
    ]
    msg = "\n".join(lines)
    return {
        "handled": True,
        "status": "placement",
        "type": "faculty_placement",
        "message": msg,
    }


def get_library_response(query: str) -> dict[str, Any]:
    """Retrieve verified library resources and timings from official records."""
    lines = [
        "## 📚 Central Library & Information Centre — MCE Hassan",
        "The Central Library at Malnad College of Engineering is a comprehensive knowledge hub supporting undergraduate, postgraduate, and research scholars:\n",
        "### 📖 Print & Media Collections",
        "- **Total Volumes:** **99,414 volumes**",
        "- **Total Titles:** **20,896 titles** across engineering, computer science, and basic sciences.",
        "- **Newspapers & Periodicals:** 13 daily newspapers and 12 magazine subscriptions.",
        "- **Journals:** Extensive national and international peer-reviewed journals.",
        "- **Digital Media & Theses:** ~1,700 educational CDs, conference proceedings, and student project reports.",
        "- **Special Book Banks:** Dedicated **SC/ST Book Bank** and **Merit Incentive Book Bank** providing semester-long textbook sets.\n",
        "### 💻 Digital Library & E-Resources",
        "Students and researchers have access to premier global electronic research databases through the VTU Consortium:",
        "- **IEEE Xplore Digital Library**",
        "- **Elsevier / ScienceDirect**",
        "- **Springer Nature**",
        "- **Taylor & Francis**",
        "- **Emerald Insight**",
        "- **ProQuest**",
        "- **KNIMBUS E-Books & Remote Access**",
        "- **National Digital Library of India (NDLI)**",
        "- **DrillBit Anti-Plagiarism Checker**\n",
        "### ⏰ Working Hours",
        "| Section | Monday – Friday | Saturday |",
        "| :--- | :--- | :--- |",
        "| **Book Issue & Return** | 10:00 AM – 5:30 PM | 9:30 AM – 1:30 PM |",
        "| **Reference & Reading Section** | 8:00 AM – 8:00 PM | 8:00 AM – 5:00 PM |",
        "- *Sundays and holidays: Check with the library notice board for special reading room schedules.*\n",
        "### 📞 Library Administration & Catalogue",
        "- **In-charge Librarian:** **Mr. Shankar D. R.**",
        "- **Contact Number:** `9740595772`",
        "- **Library Automation Software:** **EasyLib (MCE Hassan)** for instant book search and issue tracking.",
    ]
    msg = "\n".join(lines)
    return {
        "handled": True,
        "status": "library",
        "type": "faculty_library",
        "message": msg,
    }


def get_scholarships_response(query: str) -> dict[str, Any]:
    """Retrieve verified scholarship details from official records."""
    lines = [
        "## 🎓 Scholarships & Financial Aid at MCE Hassan",
        "Malnad College of Engineering assists students in securing government, institutional, alumni, and private scholarships to support their technical education:\n",
        "### 🏛️ 1. Government Scholarships",
        "- **State Scholarship Portal (SSP - Karnataka):**",
        "  - Post-Matric Scholarship for SC/ST students (Social Welfare Dept.).",
        "  - Post-Matric Scholarship for OBC, Cat-1, 2A, 3A, 3B students (Backward Classes Welfare Dept.).",
        "  - Fee Concession & Vidyasiri (Free Food & Accommodation Scheme).",
        "  - Karnataka Minorities Development Corporation (KMDC) / Arivu Education Loan.",
        "- **National Scholarship Portal (NSP - Central Government):**",
        "  - Central Sector Scheme of Scholarships for College and University Students.",
        "  - AICTE Pragati Scholarship Scheme for girl students in technical degree programmes.",
        "  - AICTE Saksham Scholarship Scheme for differently-abled students.\n",
        "### 🤝 2. Institutional & Alumni Scholarships",
        "- **MTES Scholarships:** Need-cum-merit financial aid administered directly by the Malnad Technical Education Society.",
        "- **Shri Ramesh Scholarship:** Alumni-endowed scholarship awarded to deserving engineering students.",
        "- **Merit Incentive Book Bank:** Semester-long free textbook allocation to high-performing students.\n",
        "### 📄 3. Key Documents Required for Application",
        "- Aadhaar Card (linked with bank account)",
        "- Income Certificate & Caste/Category Certificate (issued by Revenue Authority/Tahsildar)",
        "- 10th (SSLC) and 12th (PUC) / Diploma Marks Cards",
        "- Previous Semester College Marks Cards",
        "- College Admission Receipt & CET/COMEDK Allotment Letter",
        "- Active Student Bank Account Passbook (with IFSC code)\n",
        "### 🌐 Where to Apply",
        "- **Karnataka SSP Portal:** [ssp.postmatric.karnataka.gov.in](https://ssp.postmatric.karnataka.gov.in)",
        "- **National NSP Portal:** [scholarships.gov.in](https://scholarships.gov.in)",
        "- **MCE Scholarship Section:** Submit printouts of online applications along with verified document sets to the College Scholarship Desk.",
    ]
    msg = "\n".join(lines)
    return {
        "handled": True,
        "status": "scholarships",
        "type": "faculty_scholarships",
        "message": msg,
    }


def get_sports_facilities_response(query: str) -> dict[str, Any]:
    """Retrieve sports, canteen, and campus facilities from official records."""
    lines = [
        "## 🏅 Sports, Fitness & Campus Amenities — MCE Hassan",
        "Malnad College of Engineering provides comprehensive athletic, recreational, and student wellness infrastructure across its 44-acre green campus:\n",
        "### 🏃 1. Sports & Athletics Infrastructure",
        "- **Outdoor Grounds:** Sprawling full-size athletic ground supporting Cricket, Football, and 400m Track & Field athletic events.",
        "- **Dedicated Courts:** Well-maintained outdoor courts for Basketball, Volleyball, Tennis, and Ball Badminton.",
        "- **Indoor Sports Complex:** Dedicated facilities for Table Tennis, Badminton, Chess, and Carrom.",
        "- **Gymnasium & Fitness:** Multi-station modern gymnasium equipped with fitness trainers and conditioning equipment.",
        "- **Competitions:** Host and active participant in annual VTU Inter-Collegiate Tournaments, Mysore Zone meets, and college Athletic Meets.\n",
        "### ☕ 2. Campus Canteen & Cafeteria",
        "- Clean, hygienic campus cafeteria serving nutritious South Indian and North Indian meals, snacks, and beverages at subsidized student rates.",
        "- Separate seating arrangements for students and faculty members.\n",
        "### 🚌 3. Transport & Transit Facilities",
        "- Dedicated fleet of college buses connecting various key residential areas of Hassan city and the Girls' Hostel directly to the campus.",
        "- Convenient for day scholars and outstation staff.\n",
        "### 🏥 4. Health & Wellness Centre",
        "- On-campus First-Aid health centre providing prompt medical attention, emergency first aid, and basic healthcare consultations.",
        "- Tie-ups with prominent local hospitals in Hassan for emergency medical requirements.",
    ]
    msg = "\n".join(lines)
    return {
        "handled": True,
        "status": "sports_facilities",
        "type": "faculty_sports_facilities",
        "message": msg,
    }


def get_about_mce_response(query: str) -> dict[str, Any]:
    """Retrieve verified institutional overview of MCE Hassan."""
    lines = [
        "## 🏛️ Malnad College of Engineering (MCE), Hassan",
        "**Malnad College of Engineering** is one of Karnataka's oldest, most prestigious autonomous engineering institutions, celebrated for academic excellence and technical leadership:\n",
        "### 📜 History & Legacy",
        "- **Established:** Founded in **1960** during the golden jubilee celebration of Sri Malnad Technical Education Society (MTES).",
        "- **Founding Visionaries:** Established under the leadership of Late Sri. B. D. Jatti (former Acting President of India), Late Sri. G. Venkataswamy, and prominent visionaries of the Malnad region.\n",
        "### 🎖️ Affiliation & Accreditations",
        "- **Autonomous Institution:** Conferred Autonomous Status by UGC and VTU, designing cutting-edge, industry-relevant curricula.",
        "- **University Affiliation:** Affiliated with **Visvesvaraya Technological University (VTU), Belagavi**.",
        "- **AICTE Approval:** Approved by the **All India Council for Technical Education (AICTE), New Delhi**.",
        "- **Accreditations:** Accredited by **NAAC** and **NBA** for undergraduate engineering programmes.\n",
        "### 🏫 Campus & Academic Environment",
        "- **Campus Size:** Sprawling **44-acre green campus** located in the heart of Hassan city, Karnataka.",
        "- **Academic Offerings:** 11 Undergraduate B.E. programmes, 5 Postgraduate M.Tech programmes, MCA, and recognized Doctoral research centres.",
        "- **Principal:** **Dr. S. Pradeep**\n",
        "### 📞 Official College Contact Information",
        "- **Address:** No. 21, Salagame Road, Rangoli Halla, Hassan, Karnataka - 573202",
        "- **MTES Office:** `08172-268371`",
        "- **Principal's Office:** `08172-245317`",
        "- **Email:** [office@mcehassan.ac.in](mailto:office@mcehassan.ac.in)",
        "- **Official Website:** [www.mcehassan.ac.in](https://www.mcehassan.ac.in)",
    ]
    msg = "\n".join(lines)
    return {
        "handled": True,
        "status": "about_mce",
        "type": "faculty_about_mce",
        "message": msg,
    }


def lookup_faculty(query: str) -> dict[str, Any]:
    """Main routing and lookup function with try/except fallback."""
    if not source_config.ENABLE_FACULTY_LOOKUP:
        return {"handled": False}

    try:
        intent, dept_code, extracted_name = classify_intent(query)
        is_contact = is_contact_query(query)

        # 0. Smalltalk
        if intent == "SMALLTALK":
            return get_smalltalk_response()

        # 1. All Faculty Directory
        if intent == "ALL_FACULTY":
            return get_all_departments_directory()

        # 2. HOD Query
        if intent == "HOD_QUERY" and dept_code:
            return get_department_hod(dept_code)

        # 3. Department Faculty List (or Department Qualifications)
        if intent == "DEPARTMENT_FACULTY_LIST" and dept_code:
            return get_department_faculty_list(dept_code)

        # 4. Department Overview
        if intent == "DEPARTMENT_OVERVIEW" and dept_code:
            return get_department_overview(dept_code)

        # 5. Clubs Query
        if intent == "CLUBS_QUERY":
            return get_clubs_response()

        # 6. Fee Structure Query
        if intent == "FEE_STRUCTURE":
            return get_fee_structure_response()

        # 7. Admission Contact Details
        if intent == "ADMISSION_CONTACT":
            return get_admission_contact_response()

        # 8. Admission Eligibility Criteria
        if intent == "ELIGIBILITY_CRITERIA":
            return get_eligibility_criteria_response()

        # 8b. Hostel Facilities
        if intent == "HOSTEL_QUERY":
            return get_hostel_response(query)

        # 8c. Placement Information & Statistics
        if intent == "PLACEMENT_QUERY":
            return get_placement_response(query)

        # 8d. Central Library & E-Resources
        if intent == "LIBRARY_QUERY":
            return get_library_response(query)

        # 8e. Scholarships & Financial Aid
        if intent == "SCHOLARSHIPS_QUERY":
            return get_scholarships_response(query)

        # 8f. Sports, Canteen & Campus Facilities
        if intent == "SPORTS_QUERY":
            return get_sports_facilities_response(query)

        # 8g. About MCE, History & Overview
        if intent == "ABOUT_MCE_QUERY":
            return get_about_mce_response(query)

        # 9. Explicit Contact Number Query (Strictly for faculty persons or HOD)
        if intent == "FACULTY_CONTACT" and (extracted_name or dept_code):
            profiles = get_all_profiles()

            # If asking for contact of HOD
            if dept_code and (re.search(r"\bhod\b", query, re.I) or not extracted_name):
                hod_res = get_department_hod(dept_code)
                if hod_res.get("handled") and hod_res.get("person"):
                    person = hod_res["person"]
                    phone = (person.get("phone") or "").strip()
                    if phone:
                        msg = f"The contact number of **{person['name']}** ({person.get('designation', 'HOD')}, {person.get('department', 'MCE')}) is **{phone}**."
                    else:
                        msg = f"Contact number for **{person['name']}** is not available in the verified college records."
                    return {
                        "handled": True,
                        "status": "found",
                        "type": "faculty_contact",
                        "person": person,
                        "show_phone": True,
                        "photo_path": person.get("photo_path", ""),
                        "message": msg,
                    }

            # Search person
            lookup_name = extracted_name or query
            match_res = find_person_profile(lookup_name, profiles)
            if match_res.get("status") == "found":
                person = match_res["person"]
                phone = (person.get("phone") or "").strip()
                if phone:
                    msg = f"The contact number of **{person['name']}** ({person.get('designation', 'Faculty')}, {person.get('department', 'MCE')}) is **{phone}**."
                else:
                    msg = f"Contact number for **{person['name']}** is not available in the verified college records."
                return {
                    "handled": True,
                    "status": "found",
                    "type": "faculty_contact",
                    "person": person,
                    "show_phone": True,
                    "photo_path": person.get("photo_path", ""),
                    "message": msg,
                }
            elif match_res.get("status") == "ambiguous":
                cand_lines = [f"- **{c['name']}** ({c.get('department', 'MCE')})" for c in match_res["candidates"]]
                ambig_msg = f"Multiple faculty members matched '{lookup_name}'. Please specify which one you would like contact details for:\n" + "\n".join(cand_lines)
                return {
                    "handled": True,
                    "status": "ambiguous",
                    "type": "faculty_ambiguous",
                    "candidates": match_res["candidates"],
                    "show_phone": False,
                    "message": ambig_msg,
                }
            else:
                has_person_indicator = bool(re.search(r"\b(?:dr\.?|prof\.?|mr\.?|mrs\.?|ms\.?|sri\.?|smt\.?|faculty|teacher|professor|lecturer|sir|madam)\b", query, re.I))
                if not has_person_indicator:
                    # Not an explicit person inquiry, fall through to RAG
                    return {"handled": False}
                clean_target = re.sub(r"^(?:details?\s+about|info\s+about|who\s+is|contact\s+number\s+of)\s+", "", query, flags=re.I).strip(" ?.")
                return {
                    "handled": True,
                    "status": "not_found",
                    "type": "faculty_not_found",
                    "show_phone": False,
                    "message": f"No faculty member with the name '{clean_target}' was found in the college records.",
                }

        # 5. Person Profile Query (Ordinary inquiry - NO phone numbers!)
        if intent == "FACULTY_QUERY" and extracted_name:
            profiles = get_all_profiles()
            match_res = find_person_profile(extracted_name, profiles)

            if match_res.get("status") == "found":
                person = match_res["person"]
                formatted = ui_cards.format_cards_markdown([person], show_phone=False)
                return {
                    "handled": True,
                    "status": "found",
                    "type": "faculty_single",
                    "person": person,
                    "show_phone": False,
                    "photo_path": person.get("photo_path", ""),
                    "message": formatted,
                }
            elif match_res.get("status") == "ambiguous":
                cand_lines = [f"- **{c['name']}** ({c.get('department', 'MCE')})" for c in match_res["candidates"]]
                ambig_msg = f"Multiple faculty members matched '{extracted_name}'. Please specify which one you would like to view:\n" + "\n".join(cand_lines)
                return {
                    "handled": True,
                    "status": "ambiguous",
                    "type": "faculty_ambiguous",
                    "candidates": match_res["candidates"],
                    "show_phone": False,
                    "message": ambig_msg,
                }

            # If no match found, check if it was an explicit person inquiry
            has_honorific = bool(re.search(r"\b(?:dr\.?|prof\.?|mr\.?|mrs\.?|ms\.?|sri\.?|smt\.?)\b", query, re.I))
            is_explicit_person = has_honorific or any(query.lower().startswith(p) for p in ["who is", "who was", "details about dr", "details of dr", "profile of dr", "tell me about"])

            if is_explicit_person:
                clean_display_name = re.sub(r"^(?:details?\s+about|info\s+about|who\s+is|tell\s+me\s+about)\s+", "", query, flags=re.I).strip(" ?.")
                return {
                    "handled": True,
                    "status": "not_found",
                    "type": "faculty_not_found",
                    "show_phone": False,
                    "message": f"No faculty member with the name '{clean_display_name}' was found in the college records.",
                }

        # Fall through to normal RAG
        return {"handled": False}

    except Exception as e:
        print(f"[faculty_lookup] Error during lookup: {e}. Falling back to RAG.")
        return {"handled": False}
