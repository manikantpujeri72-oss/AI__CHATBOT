"""Rich UI Card rendering for faculty members and departmental directories.

Features:
- Photo on LEFT, structured details on RIGHT (st.columns([1, 3])).
- Seniority sorting: HOD -> Professor -> Associate Professor -> Assistant Professor -> others.
- Fast cached photo loading with generic placeholder fallback.
- Support for Single Card, Department List, and All Departments (with expanders).
- Fallback markdown generator for CLI testing and non-Streamlit contexts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import source_config

PHOTOS_DIR = source_config.FACULTY_PHOTOS_NEW_DIR
PLACEHOLDER_PATH = PHOTOS_DIR / "placeholder_avatar.jpg"


def get_seniority_weight(designation: str) -> int:
    d = (designation or "").lower()
    if "principal" in d:
        return 1
    if "hod" in d or "head of department" in d:
        return 2
    if "dean" in d:
        return 3
    if "professor" in d and "associate" not in d and "assistant" not in d:
        return 4
    if "associate professor" in d:
        return 5
    if "assistant professor" in d:
        return 6
    return 7


def sort_faculty_list(faculty: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort faculty by seniority weight, then alphabetically by name."""
    return sorted(faculty, key=lambda p: (get_seniority_weight(p.get("designation", "")), p.get("name", "")))


_PHOTO_BYTES_CACHE: dict[str, bytes] = {}


def get_cached_photo_bytes(photo_path: Path) -> bytes | None:
    """In-memory cache for photo bytes to eliminate disk I/O on Streamlit reruns."""
    p_str = str(photo_path.resolve())
    if p_str in _PHOTO_BYTES_CACHE:
        return _PHOTO_BYTES_CACHE[p_str]
    try:
        data = photo_path.read_bytes()
        _PHOTO_BYTES_CACHE[p_str] = data
        return data
    except Exception:
        return None


def resolve_photo_path(photo_path_str: str | None) -> Path:
    """Return valid photo Path or fallback placeholder."""
    if photo_path_str:
        p = Path(photo_path_str)
        if p.exists():
            return p
        p_assets = Path("assets/faculty") / p.name
        if p_assets.exists():
            return p_assets
        p_new = Path(r"D:\MINI Project\faculty_photos_new") / p.name
        if p_new.exists():
            return p_new
    if PLACEHOLDER_PATH.exists():
        return PLACEHOLDER_PATH
    return Path("assets/faculty/avatar_placeholder.png")


def render_single_card(person: dict[str, Any], show_phone: bool = False, title: str = "", st=None) -> None:
    """Render a single faculty member: Photo on LEFT, details on RIGHT."""
    if st is None:
        try:
            import streamlit as st
        except ImportError:
            return

    if title:
        st.markdown(f"### {title}")

    col_photo, col_details = st.columns([1, 3])

    with col_photo:
        photo_path = resolve_photo_path(person.get("photo_path"))
        photo_bytes = get_cached_photo_bytes(photo_path) if photo_path.exists() else None
        if photo_bytes:
            st.image(photo_bytes, width=150)
        else:
            placeholder = resolve_photo_path(None)
            p_bytes = get_cached_photo_bytes(placeholder) if placeholder.exists() else None
            if p_bytes:
                st.image(p_bytes, width=150)
            else:
                st.markdown("👤")

    with col_details:
        name = person.get("name", "Faculty Member")
        st.markdown(f"#### {name}")

        desig = person.get("designation")
        if desig:
            st.markdown(f"**Designation:** {desig}")

        dept = person.get("department")
        if dept:
            st.markdown(f"**Department:** {dept}")

        qual = (person.get("qualification") or "").strip()
        if not qual:
            qual = "Qualification information is not available in the college knowledge base."
        st.markdown(f"**Qualification:** {qual}")

        exp = person.get("experience")
        if exp:
            st.markdown(f"**Experience:** {exp}")

        spec = person.get("specialization")
        if spec:
            st.markdown(f"**Specialization:** {spec}")

        other = person.get("other_details")
        if other:
            st.markdown(f"**Affiliation / Details:** {other}")

        email = person.get("email")
        if email:
            st.markdown(f"✉️ **Email:** [{email}](mailto:{email})")

        phone = person.get("phone")
        if show_phone and phone:
            st.markdown(f"📞 **Phone:** `{phone}`")

    st.markdown("---")


def render_department_faculty(dept_name: str, faculty_list: list[dict[str, Any]], st=None) -> None:
    """Render department heading and all faculty cards sorted by seniority."""
    if st is None:
        try:
            import streamlit as st
        except ImportError:
            return

    sorted_fac = sort_faculty_list(faculty_list)
    st.markdown(f"### {dept_name}: {len(sorted_fac)} faculty")

    for person in sorted_fac:
        render_single_card(person, show_phone=False, st=st)


def render_all_departments(grouped_faculty: dict[str, list[dict[str, Any]]], st=None) -> None:
    """Render all departments with an expander for each department containing cards."""
    if st is None:
        try:
            import streamlit as st
        except ImportError:
            return

    st.markdown(f"### Malnad College of Engineering - All Departments Directory")

    # Order departments logically
    dept_order = [
        "First-Year Department",
        "Department of Mathematics",
        "Department of Physics",
        "Department of Chemistry",
        "Information Science and Engineering",
        "Computer Science and Engineering",
        "Mechanical Engineering",
        "Civil Engineering",
        "Electrical and Electronics Engineering",
        "Electronics and Communication Engineering",
        "Artificial Intelligence and Machine Learning",
        "Computer Science and Business Systems",
        "VLSI Design and Technology",
        "Master of Computer Applications",
    ]

    all_keys = list(grouped_faculty.keys())
    ordered_depts = [d for d in dept_order if d in grouped_faculty] + [d for d in all_keys if d not in dept_order]

    for dept in ordered_depts:
        fac = grouped_faculty[dept]
        with st.expander(f"{dept} ({len(fac)} faculty)", expanded=(dept == "Information Science and Engineering")):
            render_department_faculty(dept, fac, st=st)


def render_faculty_response(meta: dict[str, Any], st=None) -> bool:
    """Universal dispatcher for faculty responses in Streamlit.
    
    Returns True if rendered, False otherwise.
    """
    if not meta or not meta.get("type", "").startswith("faculty_"):
        return False

    if st is None:
        try:
            import streamlit as st
        except ImportError:
            return False

    m_type = meta.get("type")
    show_phone = meta.get("show_phone", False)

    if m_type == "faculty_department_overview":
        if meta.get("overview_markdown"):
            st.markdown(meta["overview_markdown"])
        elif meta.get("message"):
            st.markdown(meta["message"])
            return True

        if meta.get("person"):
            heading = meta.get("heading", meta.get("dept_name", "Department"))
            render_single_card(meta["person"], show_phone=False, title=f"Head of Department ({heading})", st=st)

        if meta.get("footer_markdown"):
            st.markdown(meta["footer_markdown"])
        return True

    if m_type in ["faculty_clubs", "faculty_fee_structure", "faculty_admission_contact", "faculty_eligibility", "faculty_smalltalk"]:
        if meta.get("message"):
            st.markdown(meta["message"])
            return True

    if m_type in ["faculty_not_offered", "faculty_not_listed"]:
        st.warning(meta.get("message", "Faculty details are not available in college records."))
        return True

    if m_type in ["faculty_found", "faculty_single", "faculty_contact"] and meta.get("person"):
        title = meta.get("title", "")
        render_single_card(meta["person"], show_phone=show_phone, title=title, st=st)
        if meta.get("explanation"):
            st.markdown(meta["explanation"])
        return True

    if m_type == "faculty_list" and meta.get("faculty_list"):
        dept_name = meta.get("dept_name", "Department")
        title = meta.get("title", "")
        render_department_faculty(dept_name, meta["faculty_list"], st=st)
        if meta.get("explanation"):
            st.markdown(meta["explanation"])
        return True

    if m_type == "faculty_all" and meta.get("grouped_faculty"):
        render_all_departments(meta["grouped_faculty"], st=st)
        return True

    if meta.get("message"):
        st.markdown(meta["message"])
        return True

    return False


def format_cards_markdown(faculty_list: list[dict[str, Any]], title: str = "", show_phone: bool = False) -> str:
    """Generate Markdown representation of cards for non-GUI / CLI testing."""
    sorted_fac = sort_faculty_list(faculty_list)
    lines: list[str] = []

    if title:
        lines.append(f"### {title}\n")

    for p in sorted_fac:
        photo = p.get("photo_path", "")
        name = p.get("name", "Faculty Member")
        if photo and Path(photo).exists():
            lines.append(f"![{name}]({Path(photo).as_posix()})")
        lines.append(f"#### {name}")
        if p.get("designation"):
            lines.append(f"- **Designation:** {p['designation']}")
        if p.get("department"):
            lines.append(f"- **Department:** {p['department']}")
        qual = (p.get("qualification") or "").strip()
        if not qual:
            qual = "Qualification information is not available in the college knowledge base."
        lines.append(f"- **Qualification:** {qual}")
        if p.get("experience"):
            lines.append(f"- **Experience:** {p['experience']}")
        if p.get("specialization"):
            lines.append(f"- **Specialization:** {p['specialization']}")
        if p.get("other_details"):
            lines.append(f"- **Affiliation / Details:** {p['other_details']}")
        if p.get("email"):
            lines.append(f"- **Email:** {p['email']}")
        if show_phone and p.get("phone"):
            lines.append(f"- **Phone:** {p['phone']}")
        lines.append("")

    return "\n".join(lines)
