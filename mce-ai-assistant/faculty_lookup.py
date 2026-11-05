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

    # Layered department detection via short_forms.py
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

    # 3. Faculty Person Query or Contact Query
    extracted_name = extract_person_name(q_raw)

    # Exclude broad non-person college topics from being treated as faculty names
    non_person_keywords = {
        "mce", "college", "malnad", "placement", "placements", "plcmt", "tnp", "tap",
        "fee", "fees", "hostel", "admission", "admissions", "admn", "cutoff", "cut off",
        "syllabus", "curriculum", "courses", "library", "scholarship", "exam", "exams",
        "results", "sports", "canteen", "bus", "transport", "facilities", "ranking",
        "vision", "mission", "history", "about", "what", "where", "how", "when",
        "first", "year", "engineering", "department", "program", "branch", "stats"
    }

    words = set(re.findall(r"\b[a-z]+\b", extracted_name.lower()))
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
        hod_person["department"] = v_hod["canonical_name"]
        if v_hod.get("qualification"):
            hod_person["qualification"] = v_hod["qualification"]
        if v_hod.get("photo_path") and Path(v_hod["photo_path"]).exists():
            hod_person["photo_path"] = v_hod["photo_path"]
        if v_hod.get("email"):
            hod_person["email"] = v_hod["email"]
        if v_hod.get("phone"):
            hod_person["phone"] = v_hod["phone"]

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
        matching_faculty = [p for p in profiles if any(md in p.get("department", "") for md in mtech_depts)]
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
    for p in profiles:
        p_dept = p.get("department", "").lower()
        if dept_code.lower() in p_dept or canonical_dept.lower() in p_dept:
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


def lookup_faculty(query: str) -> dict[str, Any]:
    """Main routing and lookup function with try/except fallback."""
    if not source_config.ENABLE_FACULTY_LOOKUP:
        return {"handled": False}

    try:
        intent, dept_code, extracted_name = classify_intent(query)
        is_contact = is_contact_query(query)

        # 1. All Faculty Directory
        if intent == "ALL_FACULTY":
            return get_all_departments_directory()

        # 2. HOD Query
        if intent == "HOD_QUERY" and dept_code:
            return get_department_hod(dept_code)

        # 3. Department Faculty List (or Department Qualifications)
        if intent == "DEPARTMENT_FACULTY_LIST" and dept_code:
            return get_department_faculty_list(dept_code)

        # 4. Explicit Contact Number Query
        if (intent == "FACULTY_CONTACT" or is_contact) and (extracted_name or dept_code):
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
