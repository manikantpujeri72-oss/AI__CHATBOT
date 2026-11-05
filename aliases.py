"""Alias expansion, fuzzy matching, and intent detection module for MCE AI Assistant."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

BASE_DIR = Path(__file__).resolve().parent
ALIASES_FILE = BASE_DIR / "aliases.json"

_CACHED_ALIASES: dict[str, Any] | None = None


def load_aliases(reload: bool = False) -> dict[str, Any]:
    global _CACHED_ALIASES
    if _CACHED_ALIASES is not None and not reload:
        return _CACHED_ALIASES
    if ALIASES_FILE.exists():
        try:
            _CACHED_ALIASES = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
            return _CACHED_ALIASES
        except Exception as e:
            print(f"Warning: could not parse aliases.json: {e}")
    _CACHED_ALIASES = {}
    return _CACHED_ALIASES


def normalize_query(query: str) -> dict[str, Any]:
    """Normalize query, expand short forms & synonyms, tolerate typos, detect faculty intent.

    Returns dict with:
      - 'original_query': original user text
      - 'display_query': user query
      - 'retrieval_query': expanded query string with canonical names & synonyms for vector/BM25 search
      - 'glossary_line': line to guide LLM prompt (e.g. 'Glossary: ISE = Information Science & Engineering')
      - 'is_broad': boolean indicating broad/open-ended question
      - 'is_faculty': boolean indicating faculty query
      - 'faculty_dept': dept code if matched (e.g. 'CSE', 'ISE', 'CIVIL')
      - 'faculty_person': person name if matched
      - 'matched_aliases': list of matched alias items
    """
    aliases_data = load_aliases()
    q_raw = query.strip()
    q_lower = q_raw.lower()

    # Clean punctuation for token matching
    q_tokens = re.findall(r"\b[\w&.-]+\b", q_lower)

    matched_items: list[dict[str, Any]] = []
    expanded_terms: list[str] = [q_raw]
    glossary_parts: list[str] = []

    # Check all sections in aliases.json
    for section_name, section_entries in aliases_data.items():
        for key, entry in section_entries.items():
            canonical = entry.get("canonical", "")
            short_forms = entry.get("short_forms", [])
            synonyms = entry.get("synonyms", [])
            typos = entry.get("typos", [])

            is_matched = False
            matched_term = ""

            # 1. Exact word-boundary match for short forms
            for sf in short_forms:
                # Escape for regex
                sf_esc = re.escape(sf)
                # Word-boundary matching
                pattern = rf"(?:\b|^){sf_esc}(?:\b|$)"
                if re.search(pattern, q_lower):
                    is_matched = True
                    matched_term = sf
                    break

            # 2. Typos match
            if not is_matched:
                for typo in typos:
                    if typo in q_lower or (len(typo) > 4 and fuzz.partial_ratio(typo, q_lower) >= 88):
                        is_matched = True
                        matched_term = typo
                        break

            # 3. Fuzzy match for full canonical or department name tokens
            if not is_matched and len(q_raw) >= 4:
                can_lower = canonical.lower()
                # Exclude common single words that span multiple departments
                GENERIC_WORDS = {
                    "college", "department", "engineering", "assistant", "associate", "professor",
                    "science", "computer", "systems", "technology", "studies", "management",
                    "applications", "communication", "design"
                }
                for token in q_tokens:
                    if len(token) >= 5 and token not in GENERIC_WORDS:
                        for ref_word in re.findall(r"\b\w{5,}\b", can_lower):
                            if fuzz.ratio(token, ref_word) >= 85:
                                is_matched = True
                                matched_term = token
                                break
                    if is_matched:
                        break
                
                # Check for multi-word phrase in query
                if not is_matched and len(can_lower) > 5 and can_lower in q_lower:
                    is_matched = True
                    matched_term = can_lower

            if is_matched:
                item_info = {
                    "code": key,
                    "section": section_name,
                    "canonical": canonical,
                    "matched_term": matched_term,
                    "synonyms": synonyms,
                }
                matched_items.append(item_info)
                # Add canonical name and first 2 synonyms to retrieval terms
                if canonical not in expanded_terms:
                    expanded_terms.append(canonical)
                for syn in synonyms[:2]:
                    if syn not in expanded_terms:
                        expanded_terms.append(syn)
                glossary_parts.append(f"{key} = {canonical}")

    # Broad query detection: short query or "tell me about", "explain", "details of", "list all"
    is_broad = False
    broad_indicators = ["tell me about", "explain", "details of", "list all", "information about", "what is", "about"]
    if len(q_tokens) <= 3:
        is_broad = True
    elif any(q_lower.startswith(bi) or bi in q_lower for bi in broad_indicators):
        is_broad = True

    # If 1 or 2 word query like "ise" or "hostel", treat as "Tell me about <canonical name>"
    if len(q_tokens) <= 2 and matched_items:
        primary_can = matched_items[0]["canonical"]
        retrieval_query = f"Tell me about {primary_can}. Detailed information, courses, overview, facilities."
    else:
        retrieval_query = " ".join(expanded_terms)

    # Faculty intent detection
    faculty_keywords = [
        "faculty", "staff", "professor", "professors", "prof", "teachers", "teacher",
        "hod", "head of department", "dean", "principal", "warden", "lecturer", "who is the hod",
        "who teaches", "instructors", "faculty list"
    ]
    is_faculty = any(fk in q_lower for fk in faculty_keywords)

    # If the query is predominantly asking about policy, guidelines, rules, fees or curriculum,
    # let it go through full RAG retrieval so complete context is provided.
    topic_keywords = ["guidelines", "rules", "criteria", "eligibility", "process", "syllabus", "curriculum", "fee", "fees", "scholarship"]
    if any(tk in q_lower for tk in topic_keywords):
        is_faculty = False

    faculty_dept: str | None = None
    faculty_person: str | None = None

    # Check if a department is in matched_items
    for itm in matched_items:
        if itm["section"] == "departments":
            faculty_dept = itm["code"]
            break

    # Check for specific person names (Dr., Prof., Mr., Mrs., Ms. with or without dot)
    person_m = re.search(r"\b(?:dr\.?|prof\.?|mr\.?|mrs\.?|ms\.?)\s+([A-Za-z\s.]+)", q_raw, re.I)
    if person_m:
        is_faculty = True
        faculty_person = person_m.group(0).strip()
    elif "who is" in q_lower and ("hod" not in q_lower and "principal" not in q_lower and "dean" not in q_lower):
        # Potential person query: "who is X"
        cand = re.sub(r"\bwho is\b", "", q_lower, flags=re.I).strip(" ?.")
        if len(cand) >= 3:
            is_faculty = True
            faculty_person = cand

    glossary_line = ""
    if glossary_parts:
        glossary_line = f"Glossary: {'; '.join(glossary_parts)}."

    return {
        "original_query": q_raw,
        "display_query": q_raw,
        "retrieval_query": retrieval_query,
        "glossary_line": glossary_line,
        "is_broad": is_broad,
        "is_faculty": is_faculty,
        "faculty_dept": faculty_dept,
        "faculty_person": faculty_person,
        "matched_aliases": matched_items,
    }
