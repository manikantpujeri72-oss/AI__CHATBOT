"""MCE AI Assistant - Streamlit chat UI.

Run: streamlit run app.py
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import streamlit as st

import rag
import hybrid_rag
import ui_cards

st.set_page_config(page_title="MCE CHATBOT - Malnad College of Engineering", page_icon="🎓", layout="wide")

def _get_base64_image(image_path: str) -> str:
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return ""

_bg_b64 = _get_base64_image("assets/mce-entrance.png")
_bg_css = f"url('data:image/png;base64,{_bg_b64}')" if _bg_b64 else "none"

_custom_css = """
<style>
/* Full-screen App Background with MCE Entrance & Dark Blue Overlay */
.stApp {
    background-image: linear-gradient(135deg, rgba(10, 25, 47, 0.88) 0%, rgba(15, 23, 42, 0.84) 50%, rgba(2, 6, 23, 0.92) 100%), __BG_CSS__ !important;
    background-size: cover !important;
    background-position: center center !important;
    background-attachment: fixed !important;
    background-repeat: no-repeat !important;
    color: #f1f5f9 !important;
}

/* Sidebar Glassmorphism */
[data-testid="stSidebar"] {
    background: rgba(15, 23, 42, 0.75) !important;
    backdrop-filter: blur(20px) saturate(180%) !important;
    -webkit-backdrop-filter: blur(20px) saturate(180%) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.16) !important;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4) !important;
}

/* Glass Chat Message Bubbles */
[data-testid="stChatMessage"],
.stChatMessage,
[data-testid="stChatMessageContent"] {
    background: rgba(255, 255, 255, 0.12) !important;
    backdrop-filter: blur(18px) saturate(160%) !important;
    -webkit-backdrop-filter: blur(18px) !important;
    border: 1px solid rgba(255, 255, 255, 0.20) !important;
    border-radius: 18px !important;
    padding: 16px 20px !important;
    margin-bottom: 16px !important;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.3) !important;
    color: #F8FAFC !important;
}

[data-testid="stChatMessage"] *,
.stChatMessage *,
[data-testid="stChatMessageContent"] * {
    color: #F1F5F9 !important;
}

[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] div,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] ul,
[data-testid="stChatMessage"] ol,
.stChatMessage p,
.stChatMessage span,
.stChatMessage div,
.stChatMessage li,
.stChatMessage ul,
.stChatMessage ol {
    color: #F1F5F9 !important;
    font-size: 15px !important;
    line-height: 1.6 !important;
}

[data-testid="stChatMessage"] li::marker,
.stChatMessage li::marker {
    color: #38bdf8 !important;
    font-weight: bold !important;
}

[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3,
[data-testid="stChatMessage"] h4,
[data-testid="stChatMessage"] h5,
[data-testid="stChatMessage"] h6,
[data-testid="stChatMessage"] strong,
[data-testid="stChatMessage"] b,
.stChatMessage h1,
.stChatMessage h2,
.stChatMessage h3,
.stChatMessage h4,
.stChatMessage strong,
.stChatMessage b {
    color: #FFFFFF !important;
    font-weight: 700 !important;
}

[data-testid="stChatMessage"] a,
.stChatMessage a {
    color: #60A5FA !important;
    text-decoration: underline !important;
    font-weight: 500 !important;
}

[data-testid="stChatMessage"] code {
    background: rgba(15, 23, 42, 0.75) !important;
    color: #7dd3fc !important;
    border: 1px solid rgba(255, 255, 255, 0.18) !important;
    border-radius: 6px !important;
    padding: 2px 6px !important;
}

[data-testid="stChatMessage"] table,
[data-testid="stChatMessage"] th,
[data-testid="stChatMessage"] td {
    color: #F1F5F9 !important;
    border: 1px solid rgba(255, 255, 255, 0.20) !important;
}

[data-testid="stChatMessage"] th {
    color: #FFFFFF !important;
    font-weight: bold !important;
    background: rgba(15, 23, 42, 0.6) !important;
}

/* Distinguish User messages */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background: rgba(37, 99, 235, 0.28) !important;
    border: 1px solid rgba(255, 255, 255, 0.25) !important;
    box-shadow: 0 6px 24px rgba(37, 99, 235, 0.25), 0 0 16px rgba(6, 182, 212, 0.2) !important;
}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) *,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) p {
    color: #FFFFFF !important;
    font-weight: 500 !important;
}

/* Transparent Streamlit Header & Bottom Wrapper - Eliminate White Box */
[data-testid="stHeader"],
header[data-testid="stHeader"],
div[data-testid="stToolbar"],
div[data-testid="stDecoration"],
div[data-testid="stStatusWidget"],
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottom"] > div > div,
div[data-testid="stBottomBlockContainer"],
div[data-testid="stBottomBlockContainer"] > div,
div[data-testid="stBottomBlockContainer"] > div > div,
div[data-testid="stBottomBlockContainer"] > div > div > div,
div.stChatFloatingInputContainer,
div.stChatFloatingInputContainer > div,
div[data-testid="stChatInputContainer"],
div[data-testid="stChatInputContainer"] > div,
.stBottom,
.stBottom > div,
.stBottom > div > div,
footer,
footer > div {
    background: transparent !important;
    background-color: transparent !important;
    box-shadow: none !important;
    border: none !important;
}

/* Pinned Input Container Dark Glassmorphism */
[data-testid="stChatInput"] {
    background: rgba(15, 23, 42, 0.90) !important;
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border: 1px solid rgba(255, 255, 255, 0.25) !important;
    border-radius: 28px !important;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5) !important;
    color: #FFFFFF !important;
    overflow: hidden !important;
}

[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] div[data-baseweb="textarea"],
[data-testid="stChatInput"] div[data-baseweb="base-input"] {
    background: transparent !important;
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

[data-testid="stChatInput"] textarea {
    background: transparent !important;
    background-color: transparent !important;
    color: #FFFFFF !important;
    caret-color: #FFFFFF !important;
    font-size: 15px !important;
}

[data-testid="stChatInput"] textarea::placeholder {
    color: #CBD5E1 !important;
    opacity: 1 !important;
}

[data-testid="stChatInput"] button {
    background: linear-gradient(135deg, #06b6d4 0%, #2563eb 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 50% !important;
    transition: all 0.2s ease !important;
}

[data-testid="stChatInput"] button:hover {
    transform: scale(1.05) !important;
    box-shadow: 0 0 12px rgba(6, 182, 212, 0.5) !important;
}

[data-testid="stChatInput"]:focus-within {
    border-color: rgba(96, 165, 250, 0.75) !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.25), 0 8px 32px rgba(0, 0, 0, 0.5) !important;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #06b6d4 0%, #2563eb 100%) !important;
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}

.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(6, 182, 212, 0.4) !important;
}

h1, h2, h3, h4 {
    color: #ffffff !important;
}
a {
    color: #38bdf8 !important;
}
</style>
""".replace("__BG_CSS__", _bg_css)

st.markdown(_custom_css, unsafe_allow_html=True)

SAMPLE_QUESTIONS = [
    "Where is Malnad College of Engineering located?",
    "When was MCE established?",
    "Which programmes does MCE offer?",
    "When does placement enrolment begin?",
    "What training is given to students for placements?",
]


@st.cache_resource
def load_clients():
    return rag.get_cohere_client(), rag.get_collection()


try:
    cohere_client, collection = load_clients()
except RuntimeError as err:
    st.error(str(err))
    st.stop()

# Initial sync once per session
if "bootstrapped" not in st.session_state:
    with st.spinner("Preparing knowledge base..."):
        try:
            rag.sync_documents(cohere_client, collection)
        except Exception as exc:
            st.warning(f"Note on initial folder check: {exc}")
    st.session_state.bootstrapped = True

st.session_state.setdefault("messages", [])


def clear_app_cache():
    """Clear cached resources so new chunks are immediately retrievable."""
    load_clients.clear()


# ----------------------------- Sidebar ------------------------------------- #
with st.sidebar:
    st.header("📚 Knowledge Base")

    # Fetch currently indexed sources
    sources = rag.list_sources(collection)
    total_chunks = sum(s["chunks"] for s in sources.values())

    if sources:
        st.caption(f"{len(sources)} documents indexed ({total_chunks} total chunks):")
        for name, info in sources.items():
            dt_str = info.get("indexed_at", "")
            date_display = dt_str[:10] if dt_str and len(dt_str) >= 10 else "N/A"
            st.markdown(
                f"• **{name}** — {info['chunks']} chunks ({info['pages']} p.)  \n"
                f"<span style='font-size:0.8em; color:#888;'>Updated: {date_display}</span>",
                unsafe_allow_html=True,
            )
    else:
        st.info("Knowledge base is currently empty. Add documents to begin.")

    st.divider()

    # Admin protection check
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    is_admin = True

    if admin_password:
        if not st.session_state.get("admin_authenticated", False):
            is_admin = False
            st.subheader("🔒 Admin Access")
            st.caption("Document management is restricted to administrators.")
            pwd_input = st.text_input("Enter Admin Password", type="password", key="pwd_input")
            if st.button("Unlock Management", key="btn_unlock"):
                if pwd_input == admin_password:
                    st.session_state.admin_authenticated = True
                    st.success("Admin mode unlocked.")
                    st.rerun()
                else:
                    st.error("Incorrect password.")
        else:
            st.caption("🔓 Admin mode active")
            if st.button("Lock Admin Controls", key="btn_lock"):
                st.session_state.admin_authenticated = False
                st.rerun()

    # Management controls (shown if admin or if no password configured)
    if is_admin:
        st.subheader("⚙️ Manage Documents")

        # 1. Sync button
        if st.button("🔄 Sync documents folder", use_container_width=True):
            with st.spinner("Syncing documents folder with database..."):
                try:
                    rep = rag.sync_documents(cohere_client, collection)
                    clear_app_cache()
                    added_n = len(rep.get("added", []))
                    upd_n = len(rep.get("updated", []))
                    ren_n = len(rep.get("renamed", []))
                    unch_n = len(rep.get("unchanged", []))
                    rem_n = len(rep.get("removed", []))
                    failed_n = len(rep.get("failed", []))
                    st.success(
                        f"Sync complete: {added_n} added, {upd_n} updated, {ren_n} renamed, "
                        f"{unch_n} unchanged, {rem_n} removed."
                    )
                    if failed_n > 0:
                        for f in rep["failed"]:
                            st.warning(f"⚠️ {f['source']}: {f['reason']}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Sync error: {exc}")

        # 2. Multi-file uploader with collision detection
        st.markdown("##### 📤 Add Documents")
        uploaded_files = st.file_uploader(
            "Upload file(s)",
            type=["pdf", "docx", "txt", "md", "csv", "xlsx", "pptx", "html", "htm"],
            accept_multiple_files=True,
            key="multi_uploader",
        )

        if uploaded_files:
            new_files = [f for f in uploaded_files if f.name not in sources]
            conflicts = [f for f in uploaded_files if f.name in sources]

            if new_files:
                if st.button(f"Add {len(new_files)} new file(s)", key="btn_add_new"):
                    with st.spinner("Indexing new files..."):
                        total_added = 0
                        for f in new_files:
                            status = rag.add_or_replace_document(
                                cohere_client, collection, f.name, f.getvalue()
                            )
                            if status in ("added", "replaced"):
                                total_added += 1
                        clear_app_cache()
                        st.success(f"Successfully added {total_added} document(s).")
                        st.rerun()

            for cf in conflicts:
                st.warning(f"⚠️ This will REPLACE the existing document **'{cf.name}'**")
                if st.button(f"Confirm Replace: {cf.name}", key=f"replace_{cf.name}"):
                    with st.spinner(f"Replacing {cf.name}..."):
                        rag.add_or_replace_document(
                            cohere_client, collection, cf.name, cf.getvalue()
                        )
                        clear_app_cache()
                        st.success(f"Replaced '{cf.name}' successfully.")
                        st.rerun()

        # 3. Replace a document control (dropdown + new file)
        if sources:
            with st.expander("🔁 Replace a document"):
                doc_to_replace = st.selectbox(
                    "Choose document to replace:",
                    options=list(sources.keys()),
                    key="select_doc_to_replace",
                )
                new_replacement_file = st.file_uploader(
                    "Upload new replacement file",
                    type=["pdf", "docx", "txt", "md", "csv", "xlsx", "pptx", "html", "htm"],
                    key="uploader_replace_single",
                )
                confirm_replace_box = st.checkbox(
                    f"Confirm replacing '{doc_to_replace}'", key="chk_confirm_replace"
                )
                if st.button(
                    "Confirm & Replace",
                    disabled=not (new_replacement_file and confirm_replace_box),
                    key="btn_exec_replace",
                ):
                    with st.spinner("Replacing document..."):
                        try:
                            rag.replace_document_with(
                                client=cohere_client,
                                collection=collection,
                                old_source=doc_to_replace,
                                new_filename=new_replacement_file.name,
                                data=new_replacement_file.getvalue(),
                            )
                            clear_app_cache()
                            st.success(
                                f"Successfully replaced '{doc_to_replace}' with '{new_replacement_file.name}'."
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Replacement failed: {e}")

        # 4. Delete document control
        if sources:
            with st.expander("🗑️ Delete a document"):
                doc_to_del = st.selectbox(
                    "Choose document to delete:",
                    options=list(sources.keys()),
                    key="select_doc_to_del",
                )
                confirm_del_box = st.checkbox(
                    f"I confirm deleting '{doc_to_del}' (moves to _deleted/)",
                    key="chk_confirm_del",
                )
                if st.button(
                    "Delete Document",
                    disabled=not confirm_del_box,
                    key="btn_exec_delete",
                ):
                    with st.spinner("Deleting document..."):
                        rag.delete_document(collection=collection, source=doc_to_del)
                        clear_app_cache()
                        st.success(f"'{doc_to_del}' deleted and moved to documents/_deleted/.")
                        st.rerun()

        # 5. Rebuild faculty data
        if st.button("👥 Rebuild faculty data", use_container_width=True):
            with st.spinner("Extracting faculty profiles and photos from knowledge base..."):
                try:
                    import faculty_extractor
                    recs = faculty_extractor.extract_all_faculty()
                    clear_app_cache()
                    st.success(f"Extracted {len(recs)} faculty profiles into faculty.json and assets/faculty/.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error rebuilding faculty: {exc}")

        # 6. Reset knowledge base
        with st.expander("⚠️ Reset Database"):
            confirm_reset = st.checkbox(
                "Wipe database and rebuild from documents/", key="chk_confirm_reset"
            )
            if st.button("Reset & Rebuild", disabled=not confirm_reset, key="btn_exec_reset"):
                with st.spinner("Resetting database..."):
                    rag.reset_collection()
                    clear_app_cache()
                    st.session_state.pop("bootstrapped", None)
                    st.success("Database wiped. Reloading...")
                    st.rerun()

        # Additional Sources (read-only)
        st.divider()
        st.subheader("📚 Additional Sources")
        st.caption("Active Knowledge Base & Directory:")
        st.markdown(
            "- **overview of mce.pdf** (114 chunks)\n"
            "- **about first year department.pdf** (6 chunks)\n"
            "- **all department faculty.pdf** (10 chunks)\n"
            "- **hod s of college.pdf** (1 chunk)\n"
            "- **placements.pdf** (14 chunks)\n"
            "- **Faculty Profiles:** 153 profiles (10 departments)"
        )

    st.divider()
    if st.button("🧹 Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ------------------------------ Main chat ---------------------------------- #
st.title("🎓 MCE AI Assistant")
st.caption("Ask about Malnad College of Engineering. Answers come directly from official college records.")

debug_sources_flag = os.getenv("DEBUG_SOURCES", "0") == "1"


def render_faculty_card(card: dict[str, Any], show_phone: bool = False):
    """Render a faculty card with photo on the left and structured details beside it."""
    col_photo, col_details = st.columns([1, 3])

    with col_photo:
        photo_rel = card.get("photo_path")
        photo_file = Path(photo_rel) if photo_rel else None
        if photo_file and photo_file.exists():
            st.image(str(photo_file), use_container_width=True)
        else:
            placeholder = Path("assets/faculty/avatar_placeholder.png")
            if placeholder.exists():
                st.image(str(placeholder), use_container_width=True)
            else:
                st.markdown("👤")

    with col_details:
        st.markdown(f"#### {card.get('name', 'Faculty Member')}")
        if card.get("designation"):
            st.markdown(f"**Designation:** {card['designation']}")
        if card.get("department"):
            st.markdown(f"**Department:** {card['department']}")
        qual = (card.get("qualification") or "").strip()
        if not qual:
            qual = "Qualification information is not available in the college knowledge base."
        st.markdown(f"**Qualification:** {qual}")
        if card.get("specialization"):
            st.markdown(f"**Specialization:** {card['specialization']}")
        if card.get("experience"):
            st.markdown(f"**Experience:** {card['experience']}")
        if card.get("faculty_id"):
            st.markdown(f"**Faculty ID:** {card['faculty_id']}")
        if show_phone and card.get("phone"):
            st.markdown(f"📞 **Phone:** `{card['phone']}`")
        if card.get("email"):
            st.markdown(f"✉️ **Email:** [{card['email']}](mailto:{card['email']})")
        if card.get("other_details"):
            st.markdown(f"ℹ️ {card['other_details']}")

    st.markdown("---")


if not st.session_state.messages:
    st.write("**Try asking:**")
    cols = st.columns(len(SAMPLE_QUESTIONS))
    for col, q in zip(cols, SAMPLE_QUESTIONS):
        if col.button(q, use_container_width=True):
            st.session_state.pending = q
            st.rerun()

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        rendered = False
        if msg.get("faculty_meta"):
            rendered = ui_cards.render_faculty_response(msg["faculty_meta"], st=st)
        if not rendered:
            if msg.get("faculty_cards"):
                for fcard in msg.get("faculty_cards", []):
                    ui_cards.render_single_card(fcard, st=st)
                rendered = True
        if not rendered and msg.get("content"):
            st.markdown(msg["content"])
        if debug_sources_flag and msg.get("sources"):
            with st.expander("🛠️ Debug Sources (Admin only)"):
                for s in msg["sources"]:
                    st.caption(f"{s.get('source')} (p. {s.get('page')}) - distance: {s.get('distance', s.get('score'))}")

question = st.chat_input("Ask a question about MCE...") or st.session_state.pop("pending", None)

if question:
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
        if m.get("content") and m["content"].strip()
    ]
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        stream_gen, hits, meta = hybrid_rag.ask_stream(cohere_client, question, history)
        rendered = ui_cards.render_faculty_response(meta, st=st)
        if not rendered:
            full_answer = st.write_stream(stream_gen)
        else:
            full_answer = "".join(list(stream_gen))
            if not full_answer and meta.get("message"):
                full_answer = meta.get("message")

        if debug_sources_flag and hits:
            with st.expander("🛠️ Debug Sources (Admin only)"):
                for s in hits:
                    st.caption(f"{s.get('source')} (p. {s.get('page')}) - distance: {s.get('distance', s.get('score'))}")

    # Store message with faculty meta and debug sources
    summary_content = full_answer.strip()
    if not summary_content and rendered and meta:
        person = meta.get("person") or {}
        p_name = person.get("name")
        p_dept = meta.get("dept_name") or person.get("department")
        if p_name and p_dept:
            summary_content = f"{p_name} is the {person.get('designation', 'Faculty')} of {p_dept}."
        else:
            summary_content = meta.get("message", "")

    if not summary_content:
        summary_content = "I couldn't find specific details for that in the college documents. You can ask about: departments, HODs, faculty, placements, admissions, and facilities."
        st.markdown(summary_content)

    st.session_state.messages.append({
        "role": "assistant",
        "content": summary_content,
        "faculty_meta": meta if rendered else None,
        "sources": hits,
        "timing": meta.get("timing", {}),
    })

