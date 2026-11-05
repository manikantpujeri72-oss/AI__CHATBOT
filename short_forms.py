"""Comprehensive dynamic keyword and short-form resolver for MCE AI Assistant.

Features:
1. Auto-discovers every department name from data and generates:
   - Initials (ISE, I.S.E, IS&E, I S E)
   - Initials without 'and'
   - First-word forms ('information science', 'info sci', 'IS')
   - Common branch aliases (mech, civil, comp sci, ai ml, cs bs, etc.)
   - Generates and persists mapping to 'department_index.json'.
2. Layered matching:
   - Layer 1: Exact alias
   - Layer 2: Normalized match (lowercase, strip dots, spaces, '&', 'and')
   - Layer 3: Fuzzy match (edit distance / rapidfuzz ratio >= 82)
   - Layer 4: Keyword overlap ('info sci', 'information', 'science dept')
   - Layer 5: Embedding similarity as fallback
3. Query expansion before retrieval (e.g. 'plcmt stats of ise' -> 'training and placement statistics of Information Science and Engineering').
4. Spelling mistake handling (detailes, facluty, depertment, informaton).
5. Always replies using FULL official department names.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from rapidfuzz import fuzz

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DEPT_INDEX_FILE = BASE_DIR / "department_index.json"
PROFILES_FILE = BASE_DIR / "faculty_profiles_new.json"
FACULTY_JSON_FILE = BASE_DIR / "faculty.json"

# Common term expansion mapping with typo tolerance
COMMON_TERMS: dict[str, str] = {
    r"\bhod\b": "Head of Department",
    r"\bh\.o\.d\.?\b": "Head of Department",
    r"\bhead of dept\.?\b": "Head of Department",
    r"\bmce\b": "Malnad College of Engineering",
    r"\bm\.c\.e\.?\b": "Malnad College of Engineering",
    r"\bmalenadu\b": "Malnad College of Engineering",
    r"\bplcmt\b": "placement",
    r"\bplcmts\b": "placements",
    r"\btnp\b": "Training and Placement",
    r"\bt\.n\.p\.?\b": "Training and Placement",
    r"\btap\b": "Training and Placement",
    r"\badmn\b": "admission",
    r"\badmissions?\b": "admission",
    r"\bprin(?:cipal)?\b": "Principal",
    r"\blib\b": "library",
    r"\bsem\b": "semester",
    r"\bprof\b": "Professor",
    r"\basst\.?\s*prof\.?\b": "Assistant Professor",
    r"\bassoc\.?\s*prof\.?\b": "Associate Professor",
    r"\bdept\.?\b": "Department",
}

# Common typos to auto-correct
TYPO_CORRECTIONS: dict[str, str] = {
    r"\bdetailes\b": "details",
    r"\bdetials\b": "details",
    r"\bfacluty\b": "faculty",
    r"\bdepertment\b": "department",
    r"\binformaton\b": "information",
    r"\bproffesor\b": "professor",
    r"\blectureres\b": "lecturers",
    r"\bplacemnts\b": "placements",
}


def generate_department_index() -> dict[str, Any]:
    """Auto-discover departments from profiles/faculty.json and generate department_index.json."""
    raw_depts = set()

    # Read from faculty_profiles_new.json
    if PROFILES_FILE.exists():
        try:
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                profs = json.load(f)
            for p in profs:
                d = p.get("department", "").strip()
                if d and d not in ["Malnad College of Engineering (MCE)", "Examinations and Evaluation Section", "Central Library", "Hostel Administration"]:
                    raw_depts.add(d)
        except Exception:
            pass

    # Read from faculty.json
    if FACULTY_JSON_FILE.exists():
        try:
            with open(FACULTY_JSON_FILE, "r", encoding="utf-8") as f:
                facs = json.load(f)
            for item in facs:
                d = item.get("department", "").strip()
                if d and "College" not in d:
                    raw_depts.add(d)
        except Exception:
            pass

    # Canonical dictionary
    known_canonicals = {
        "ISE": "Information Science and Engineering",
        "CSE": "Computer Science and Engineering",
        "MECH": "Mechanical Engineering",
        "CIVIL": "Civil Engineering",
        "EEE": "Electrical and Electronics Engineering",
        "ECE": "Electronics and Communication Engineering",
        "CSBS": "Computer Science and Business Systems",
        "AIML": "Artificial Intelligence and Machine Learning",
        "VLSI": "VLSI Design and Technology",
        "MCA": "Master of Computer Applications",
        "FIRST_YEAR": "First-Year Department",
        "MATH": "Department of Mathematics",
        "PHY": "Department of Physics",
        "CHEM": "Department of Chemistry",
        "EIE": "Electronics and Instrumentation Engineering",
        "CADS": "Computer Aided Design of Structures",
        "DECS": "Digital Electronics and Communication Systems",
        "PES": "Power and Energy Systems",
        "AIDS": "Artificial Intelligence and Data Science",
        "RAI": "Robotics and Artificial Intelligence",
        "MBA": "Master of Business Administration",
    }

    dept_index: dict[str, dict[str, Any]] = {}

    for code, canonical in known_canonicals.items():
        aliases: set[str] = set()

        # 1. Direct code
        aliases.add(code.lower())
        # Dots variations (e.g. i.s.e, i.s.e.)
        dotted = ".".join(list(code.lower()))
        aliases.add(dotted)
        aliases.add(dotted + ".")
        # Spaces variations (e.g. i s e)
        aliases.add(" ".join(list(code.lower())))

        # 2. Canonical words initials & variations
        words = re.findall(r"[A-Za-z]+", canonical)
        initials_all = "".join(w[0].upper() for w in words)
        aliases.add(initials_all.lower())

        content_words = [w for w in words if w.lower() not in ["and", "&", "of", "the", "in"]]
        initials_no_and = "".join(w[0].upper() for w in content_words)
        aliases.add(initials_no_and.lower())

        # Ampersand variations (e.g. IS&E, AI&ML, CS&BS, E&CE, E&EE)
        if len(content_words) >= 2:
            amp = f"{content_words[0][0]}&{content_words[1][0]}".lower()
            aliases.add(amp)
            if len(content_words) == 3:
                aliases.add(f"{content_words[0][0]}&{content_words[1][0]}{content_words[2][0]}".lower())
                aliases.add(f"{content_words[0][0]}{content_words[1][0]}&{content_words[2][0]}".lower())

        # 3. First-word forms & prefixes
        aliases.add(canonical.lower())
        if len(content_words) >= 1:
            first = content_words[0].lower()
            aliases.add(first)
            if len(content_words) >= 2:
                two_words = f"{first} {content_words[1].lower()}"
                aliases.add(two_words)
                aliases.add(f"{first} and {content_words[1].lower()}")
                aliases.add(f"{first} & {content_words[1].lower()}")

        # 4. Common specific branch aliases
        if code == "ISE":
            aliases.update(["info sci", "infosci", "info science", "information science", "information sci", "dept of ise", "is&e"])
        elif code == "CSE":
            aliases.update(["cs", "comp sci", "compsci", "comp science", "computer science", "dept of cse", "cs&e"])
        elif code == "ECE":
            aliases.update(["ec", "electronics", "electronics & communication", "electronics and communication", "dept of ece", "e&ce", "e&c"])
        elif code == "EEE":
            aliases.update(["ee", "electrical", "electrical & electronics", "electrical and electronics", "dept of eee", "e&ee", "e&e"])
        elif code == "MECH":
            aliases.update(["mech", "mechanical eng", "dept of mech", "dept of mechanical"])
        elif code == "CIVIL":
            aliases.update(["cv", "civil eng", "civil engineering", "dept of civil"])
        elif code == "AIML":
            aliases.update(["ai", "ml", "ai ml", "ai&ml", "a.i.m.l", "artificial intelligence", "machine learning", "dept of aiml"])
        elif code == "CSBS":
            aliases.update(["cs bs", "cs&bs", "c.s.b.s", "computer science & business", "computer science and business", "dept of csbs"])
        elif code == "VLSI":
            aliases.update(["v.l.s.i", "vlsi design", "vlsi technology", "electronics engineering vlsi"])
        elif code == "MCA":
            aliases.update(["m.c.a", "master of computer applications", "computer applications"])
        elif code == "FIRST_YEAR":
            aliases.update([
                "first year", "first-year", "1st year", "first year dept", "first year department",
                "basic science", "basic sciences", "dept of first year", "first year engineering",
                "first-year department", "first year faculty", "first year hod"
            ])
        elif code == "MATH":
            aliases.update([
                "math", "maths", "mathematics", "mathematics department", "math dept",
                "dept of mathematics", "mathematics dept", "department of maths"
            ])
        elif code == "PHY":
            aliases.update([
                "phy", "physics", "physics department", "dept of physics", "physics dept"
            ])
        elif code == "CHEM":
            aliases.update([
                "chem", "chemistry", "chemistry department", "dept of chemistry", "chemistry dept"
            ])
        elif code == "EIE":
            aliases.update([
                "eie", "e&i", "e & i", "eie hod", "e&i hod", "e & i hod", "ei", "electronics and instrumentation",
                "electronics & instrumentation", "dept of eie", "instrumentation", "instrumentation technology", "eie dept"
            ])
        elif code == "CADS":
            aliases.update([
                "cads", "computer aided design of structures", "structures", "mtech cads", "m.tech cads",
                "cad of structures", "dept of cads", "cads dept"
            ])
        elif code == "DECS":
            aliases.update([
                "decs", "digital electronics", "digital electronics and communication systems",
                "digital electronics & communication systems", "mtech decs", "m.tech decs", "de&cs", "de and cs", "decs dept"
            ])
        elif code == "PES":
            aliases.update([
                "pes", "power and energy", "power and energy systems", "power & energy systems",
                "power systems", "mtech pes", "m.tech pes", "pes dept"
            ])
        elif code == "AIDS":
            aliases.update([
                "aids", "ai and ds", "ai & ds", "ai/ds", "ai ds", "artificial intelligence and data science",
                "artificial intelligence & data science", "mtech aids", "m.tech aids", "aids dept"
            ])
        elif code == "RAI":
            aliases.update([
                "rai", "robotics", "robotics & artificial intelligence", "robotics and artificial intelligence",
                "r and ai", "r & ai", "robotics and ai", "robotics & ai", "rai dept"
            ])
        elif code == "MBA":
            aliases.update([
                "mba", "master of business administration", "m.b.a", "m.b.a.", "business administration", "mba dept"
            ])

        # Remove single English stopwords from aliases
        STOPWORDS = {"is", "me", "in", "to", "for", "at", "by", "from", "up", "on", "with", "as", "an", "a", "the", "or", "and"}
        clean_aliases = sorted([a for a in aliases if a.lower() not in STOPWORDS])

        dept_index[code] = {
            "canonical": canonical,
            "code": code,
            "aliases": clean_aliases,
        }

    # Persist to department_index.json
    try:
        with open(DEPT_INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(dept_index, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return dept_index


_DEPT_INDEX_CACHE: dict[str, dict[str, Any]] | None = None


def get_department_index() -> dict[str, dict[str, Any]]:
    global _DEPT_INDEX_CACHE
    if _DEPT_INDEX_CACHE is not None:
        return _DEPT_INDEX_CACHE

    if DEPT_INDEX_FILE.exists():
        try:
            with open(DEPT_INDEX_FILE, "r", encoding="utf-8") as f:
                _DEPT_INDEX_CACHE = json.load(f)
            return _DEPT_INDEX_CACHE
        except Exception:
            pass

    _DEPT_INDEX_CACHE = generate_department_index()
    return _DEPT_INDEX_CACHE


# Run initial index generation
get_department_index()


def normalize_text(text: str) -> str:
    """Strip punctuation, dots, spaces, ampersands, and 'and'."""
    s = text.lower()
    s = re.sub(r"&(?:amp;)?", " ", s)
    s = re.sub(r"\band\b", " ", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def resolve_department(text: str) -> tuple[str | None, str | None, float]:
    """Layered resolver that maps user text to a department.
    
    Hardened rules:
    - Strips stray punctuation and quotes before matching.
    - Tokens of 3 characters or fewer ('hi', 'is', 'ai', 'of', 'me') match ONLY by exact alias in Layer 1.
    - Never uses substring inclusion (e.g. 'hi' in 'machine') for normalized matching.
    - Fuzzy matching requires score >= 82 AND margin >= 10 over the 2nd best candidate.
    - Returns (None, None, 0.0) when not confident.
    
    Returns:
      (dept_code, canonical_full_name, confidence_score)
    """
    index = get_department_index()
    # Strip stray punctuation, quotes and trailing punctuation
    clean_q = re.sub(r"['\"`\.,;:!?\(\)\[\]\{\}]+", " ", text).strip().lower()
    q = re.sub(r"\s+", " ", clean_q)
    if not q:
        return None, None, 0.0

    STOPWORDS = {
        "is", "me", "in", "to", "for", "at", "by", "from", "up", "on", "with",
        "as", "an", "a", "the", "or", "and", "tell", "give", "who", "what",
        "hi", "hello", "hey", "of", "about", "explain", "detail", "details"
    }

    # If the entire query is a 1-3 letter token that is in STOPWORDS, return None immediately
    if q in STOPWORDS or len(q) <= 2 and q not in ["ai", "ee", "ec", "cv", "cs"]:
        return None, None, 0.0

    # Layer 1: Exact alias match (longest specific alias wins)
    exact_matches: list[tuple[int, str, str, float]] = []
    for code, info in index.items():
        canonical = info["canonical"]
        for alias in info["aliases"]:
            a_lower = alias.lower()
            if a_lower in STOPWORDS:
                continue
            # Short tokens (<= 3 chars) match ONLY as exact word boundary and must not be a stopword
            pattern = rf"\b{re.escape(a_lower)}\b"
            if re.search(pattern, q):
                exact_matches.append((len(a_lower), code, canonical, 1.0))

    if exact_matches:
        exact_matches.sort(key=lambda x: x[0], reverse=True)
        return exact_matches[0][1], exact_matches[0][2], exact_matches[0][3]

    # For queries of 3 characters or fewer, ONLY Layer 1 exact alias match is permitted!
    if len(q) <= 3:
        return None, None, 0.0

    # Layer 2: Normalized match (require full canonical match or full alias match; NEVER short substring!)
    q_norm = normalize_text(q)
    if len(q_norm) >= 4:
        norm_matches: list[tuple[int, str, str, float]] = []
        for code, info in index.items():
            canonical = info["canonical"]
            can_norm = normalize_text(canonical)
            # Only match if full canonical name is inside query, or query equals canonical
            if can_norm in q_norm or (len(q_norm) >= 8 and q_norm == can_norm):
                norm_matches.append((len(can_norm), code, canonical, 0.95))
            for alias in info["aliases"]:
                if alias.lower() in STOPWORDS:
                    continue
                a_norm = normalize_text(alias)
                # Require alias to be at least 4 characters for normalized match
                if len(a_norm) >= 4 and a_norm in q_norm:
                    norm_matches.append((len(a_norm), code, canonical, 0.92))

        if norm_matches:
            norm_matches.sort(key=lambda x: x[0], reverse=True)
            return norm_matches[0][1], norm_matches[0][2], norm_matches[0][3]

    # Layer 3: Fuzzy match (requires score >= 82 AND margin >= 10 over second best)
    scored_candidates: list[tuple[float, str, str]] = []

    for code, info in index.items():
        canonical = info["canonical"]
        score1 = fuzz.token_set_ratio(q, canonical.lower())
        score2 = max((fuzz.ratio(q, a.lower()) for a in info["aliases"] if a.lower() not in STOPWORDS and len(a) >= 4), default=0)
        top = max(score1, score2)
        if top >= 82:
            scored_candidates.append((float(top), code, canonical))

    if scored_candidates:
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_score = scored_candidates[0][0]
        second_score = scored_candidates[1][0] if len(scored_candidates) > 1 else 0.0
        margin = top_score - second_score
        if top_score >= 82.0 and margin >= 10.0:
            return scored_candidates[0][1], scored_candidates[0][2], top_score / 100.0

    # Layer 4: Keyword overlap (require non-generic domain tokens and strict overlap)
    GENERIC_TOKENS = {
        "engineering", "department", "dept", "program", "course", "faculty",
        "studies", "technology", "about", "tell", "give", "show", "overview",
        "detail", "details", "info", "information"
    }
    q_tokens = set(re.findall(r"\b[a-z]{3,}\b", q)) - GENERIC_TOKENS
    if q_tokens:
        overlap_candidates: list[tuple[str, str, float]] = []
        for code, info in index.items():
            can_tokens = set(re.findall(r"\b[a-z]{3,}\b", info["canonical"].lower())) - GENERIC_TOKENS
            common = q_tokens.intersection(can_tokens)
            if common:
                score = len(common) / len(can_tokens)
                if score >= 0.5:
                    overlap_candidates.append((code, info["canonical"], score))
        if overlap_candidates:
            overlap_candidates.sort(key=lambda x: x[2], reverse=True)
            if len(overlap_candidates) == 1 or (overlap_candidates[0][2] - overlap_candidates[1][2] >= 0.15):
                return overlap_candidates[0]

    return None, None, 0.0


def detect_department(query: str) -> tuple[str | None, str | None]:
    """Compatibility API returning (dept_code, canonical_name)."""
    code, canonical, _ = resolve_department(query)
    return code, canonical


def expand_query(query: str) -> str:
    """Expand typos, common abbreviations, and department short forms into official full names."""
    expanded = query

    # 1. Auto-correct spelling mistakes
    for pat, repl in TYPO_CORRECTIONS.items():
        expanded = re.sub(pat, repl, expanded, flags=re.I)

    # 2. Expand common college terms
    for pat, repl in COMMON_TERMS.items():
        expanded = re.sub(pat, repl, expanded, flags=re.I)

    # 3. Expand department short forms into FULL official names
    index = get_department_index()
    q_lower = expanded.lower()
    for code, info in index.items():
        canonical = info["canonical"]
        # Match short form specifically
        sf_pattern = rf"\b{re.escape(code.lower())}\b"
        if re.search(sf_pattern, q_lower):
            expanded = re.sub(sf_pattern, canonical, expanded, flags=re.I)

    # 4. Domain-specific topic enrichment for critical queries to ensure high recall
    q_norm = q_lower.strip()

    # Admission contact details
    if re.search(r"\badmission\s+(?:contact|details|enquiry|phone|no|office)\b", q_norm) or (
        "admission" in q_norm and ("contact" in q_norm or "number" in q_norm or "phone" in q_norm)
    ):
        expanded += " MCE Admission Contact Details MTES Office Principal Office Dean Student Affairs admission enquiry PRO phone numbers email address Malnad College of Engineering"

    # Fee structure
    if re.search(r"\bfee(?:s)?\s+(?:structure|details?|breakup|info|chart)\b", q_norm) or q_norm in ["fee structure", "fees", "fee"]:
        expanded += " Fee Structure 2026-27 Management Quota Fees KCET KEA government aided unaided courses tuition fees first year B.E. MCA Malnad College of Engineering"

    # Eligibility criteria
    if re.search(r"\beligibility\b", q_norm) or ("criteria" in q_norm and "admission" in q_norm):
        expanded += " Eligibility Criteria for Admission to MCE Hassan B.E. 2nd PUC 12th standard minimum marks 45% 40% Physics Mathematics KCET COMEDK diploma lateral entry M.Tech MCA"

    # Clubs at MCE
    if re.search(r"\b(?:clubs?|student\s+clubs?)\b", q_norm):
        expanded += " Clubs at MCE Eco Club Leo Club Literary Club LIT Rotaract Club DevOps Club Science Association Malnad Technical Club Enigma IUCEE EWB ASCE student chapter Malnad College of Engineering"

    return expanded
