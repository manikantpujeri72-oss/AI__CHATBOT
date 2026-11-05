"""MCE AI Assistant - Streamlit chat UI.

Run: streamlit run app.py
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

import rag

st.set_page_config(page_title="MCE AI Assistant", page_icon="🎓", layout="wide")

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

        # 5. Reset knowledge base
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

    st.divider()
    if st.button("🧹 Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ------------------------------ Main chat ---------------------------------- #
st.title("🎓 MCE AI Assistant")
st.caption("Ask about Malnad College of Engineering. Answers come only from the college documents.")

if not st.session_state.messages:
    st.write("**Try asking:**")
    cols = st.columns(len(SAMPLE_QUESTIONS))
    for col, q in zip(cols, SAMPLE_QUESTIONS):
        if col.button(q, use_container_width=True):
            st.session_state.pending = q
            st.rerun()


def show_sources(sources_list):
    if sources_list:
        with st.expander("Sources"):
            for s in sources_list:
                st.markdown(f"**{s['source']}** (page {s['page']})")
                preview = s["text"][:400] + ("..." if len(s["text"]) > 400 else "")
                st.caption(preview)


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            show_sources(msg.get("sources"))

question = st.chat_input("Ask a question about MCE...") or st.session_state.pop("pending", None)

if question:
    history = [
        {"role": m["role"], "content": m["content"]} for m in st.session_state.messages
    ]
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching college documents..."):
            try:
                answer, hits = rag.ask(cohere_client, collection, question, history)
            except Exception as exc:
                answer, hits = f"Sorry, something went wrong: {exc}", []
        st.markdown(answer)
        show_sources(hits)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": hits}
    )
