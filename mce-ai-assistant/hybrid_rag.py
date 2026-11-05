"""Non-invasive hybrid RAG adapter for MCE AI Assistant.

Integrates:
1. Strict Faculty Lookup & Directory (via faculty_lookup.py and ui_cards.py)
2. Additional Knowledge Base Folder (via 'kb_new_folder' collection with 5 PDFs)
3. Existing Baseline Knowledge Base ('mce_docs' collection, strictly untouched at 83 chunks)

Features:
- Query expansion via short_forms.py before retrieval.
- Comprehensive intent-based routing with try/except fallbacks.
- DEBUG_ROUTING logging when enabled in source_config.py.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Generator

import chromadb
from dotenv import load_dotenv

import faculty_lookup
import rag
import short_forms
import source_config
import ui_cards

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "chroma_db"


def log_debug_routing(
    original_query: str,
    expanded_query: str,
    intent: str,
    extracted_entity: str | None,
    top_matches: Any,
    answering_source: str,
) -> None:
    """Print debug routing info when DEBUG_ROUTING is enabled."""
    if not getattr(source_config, "DEBUG_ROUTING", False):
        return
    print("\n" + "=" * 70)
    print(" [DEBUG ROUTING LOG]")
    print(f"  - Original Query:      {original_query}")
    print(f"  - Expanded Query:      {expanded_query}")
    print(f"  - Detected Intent:     {intent}")
    print(f"  - Extracted Entity:    {extracted_entity}")
    print(f"  - Top Matches:         {top_matches}")
    print(f"  - Answering Source:    {answering_source}")
    print("=" * 70 + "\n")


def retrieve_new_source(client: Any, query: str, top_k: int = 6) -> list[dict]:
    """Retrieve top chunks from the new collection 'kb_new_folder'."""
    if not source_config.ENABLE_NEW_KB_SOURCE:
        return []

    client_db = chromadb.PersistentClient(path=str(DB_DIR))
    try:
        col = client_db.get_collection(source_config.NEW_KB_COLLECTION_NAME)
    except Exception:
        return []

    if col.count() == 0:
        return []

    # Dense embedding query
    model = os.getenv("COHERE_EMBED_MODEL", "embed-v4.0")
    try:
        res = client.embed(
            model=model,
            input_type="search_query",
            embedding_types=["float"],
            texts=[query],
        )
        q_emb = res.embeddings.float_[0]
    except Exception:
        return []

    results = col.query(
        query_embeddings=[q_emb],
        n_results=min(top_k, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    hits: list[dict] = []
    if results and results.get("documents"):
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
        ids = results["ids"][0] if results.get("ids") else [""] * len(docs)
        for doc, meta, dist, cid in zip(docs, metas, dists, ids):
            hits.append({
                "id": cid,
                "text": doc,
                "source": meta.get("source", "new_kb_folder"),
                "page": meta.get("page", 1),
                "distance": dist,
                "is_new_source": True,
            })
    return hits


def ask(
    client: Any,
    question: str,
    history: list[dict] | None = None,
) -> tuple[str, list[dict], dict[str, Any]]:
    """Unified entry point for answering questions with faculty lookup and multi-source RAG."""
    history = history or []
    expanded_question = short_forms.expand_query(question)

    try:
        intent, dept_code, person_name = faculty_lookup.classify_intent(question)
    except Exception as e:
        print(f"[hybrid_rag] Warning during intent classification: {e}")
        intent, dept_code, person_name = "GENERAL", None, None

    extracted_entity = dept_code or person_name or "None"

    # 1. Faculty Lookup (if enabled)
    if source_config.ENABLE_FACULTY_LOOKUP:
        try:
            fac_res = faculty_lookup.lookup_faculty(question)
            if fac_res.get("handled"):
                status = fac_res.get("status")
                log_debug_routing(
                    original_query=question,
                    expanded_query=expanded_question,
                    intent=intent,
                    extracted_entity=extracted_entity,
                    top_matches=fac_res.get("person", {}).get("name") or fac_res.get("dept_name") or status,
                    answering_source=source_config.FACULTY_PROFILES_COLLECTION_NAME,
                )
                meta = {
                    "type": fac_res.get("type", f"faculty_{status}"),
                    "status": status,
                    "show_phone": fac_res.get("show_phone", False),
                    "photo_path": fac_res.get("photo_path"),
                    "person": fac_res.get("person"),
                    "faculty_list": fac_res.get("faculty_list"),
                    "grouped_faculty": fac_res.get("grouped_faculty"),
                    "dept_name": fac_res.get("dept_name"),
                    "answering_source": source_config.FACULTY_PROFILES_COLLECTION_NAME,
                }
                return fac_res.get("message", ""), [], meta
        except Exception as e:
            print(f"[hybrid_rag] Error in faculty lookup: {e}. Falling through to RAG.")

    # 2. Base Knowledge Base Retrieval ('mce_docs')
    col_orig = rag.get_collection(DB_DIR, source_config.ORIGINAL_COLLECTION_NAME)

    # If new source is disabled, delegate directly to rag.ask
    if not source_config.ENABLE_NEW_KB_SOURCE:
        resp = rag.ask(client, col_orig, expanded_question, history)
        log_debug_routing(
            original_query=question,
            expanded_query=expanded_question,
            intent=intent,
            extracted_entity=extracted_entity,
            top_matches="mce_docs chunks",
            answering_source=source_config.ORIGINAL_COLLECTION_NAME,
        )
        return resp[0], resp[1], getattr(resp, "timing", {})

    # 3. Multi-Source Hybrid RAG Retrieval using expanded query
    hits_orig = rag.retrieve(client, col_orig, expanded_question, top_k=rag.TOP_K)
    hits_new = retrieve_new_source(client, expanded_question, top_k=6)

    # Merge hits: prioritize most relevant chunks
    combined_hits = list(hits_orig)
    seen_texts = {h["text"] for h in hits_orig}
    for h in hits_new:
        if h["text"] not in seen_texts:
            seen_texts.add(h["text"])
            combined_hits.append(h)
    combined_hits = combined_hits[:10]
    combined_hits = combined_hits[:10]

    sources_used = sorted(set(h.get("source", "unknown") for h in combined_hits))
    answering_source_str = ", ".join(sources_used) if sources_used else "None"

    log_debug_routing(
        original_query=question,
        expanded_query=expanded_question,
        intent=intent,
        extracted_entity=extracted_entity,
        top_matches=f"{len(combined_hits)} chunks from {answering_source_str}",
        answering_source=answering_source_str,
    )

    if not combined_hits:
        return rag.NO_INFO, [], {"retrieval": "empty"}

    # Format context for LLM
    context_blocks = []
    for h in combined_hits:
        context_blocks.append(f"[{h['source']}, page {h['page']}]\n{h['text']}")
    context = "\n\n".join(context_blocks)

    clean_history = [
        {"role": m["role"], "content": m["content"].strip()}
        for m in history
        if m.get("content") and m["content"].strip()
    ]
    messages = [{"role": "system", "content": rag.SYSTEM_PROMPT}]
    messages += clean_history[-4:]
    messages.append({
        "role": "user",
        "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}",
    })

    # LLM Chat Synthesis
    raw_answer = rag._chat(client, messages, model=rag.CHAT_MODEL)
    clean_answer = rag.strip_sources(raw_answer)
    clean_answer = rag.strip_unrequested_phone_numbers(clean_answer, question)

    return clean_answer, combined_hits, {
        "type": "hybrid_rag",
        "sources_count": len(combined_hits),
        "answering_source": answering_source_str,
    }


def ask_stream(
    client: Any,
    question: str,
    history: list[dict] | None = None,
) -> tuple[Generator[str, None, None], list[dict], dict[str, Any]]:
    """Streaming entry point for Streamlit chat."""
    history = history or []
    expanded_question = short_forms.expand_query(question)

    try:
        intent, dept_code, person_name = faculty_lookup.classify_intent(question)
    except Exception as e:
        print(f"[hybrid_rag] Warning during intent classification: {e}")
        intent, dept_code, person_name = "GENERAL", None, None

    extracted_entity = dept_code or person_name or "None"

    # 1. Faculty Lookup Check
    if source_config.ENABLE_FACULTY_LOOKUP:
        try:
            fac_res = faculty_lookup.lookup_faculty(question)
            if fac_res.get("handled"):
                msg = fac_res.get("message", "")
                status = fac_res.get("status")

                log_debug_routing(
                    original_query=question,
                    expanded_query=expanded_question,
                    intent=intent,
                    extracted_entity=extracted_entity,
                    top_matches=fac_res.get("person", {}).get("name") or fac_res.get("dept_name") or status,
                    answering_source=source_config.FACULTY_PROFILES_COLLECTION_NAME,
                )

                def single_stream():
                    yield msg

                meta = {
                    "type": fac_res.get("type", f"faculty_{status}"),
                    "status": status,
                    "show_phone": fac_res.get("show_phone", False),
                    "photo_path": fac_res.get("photo_path"),
                    "person": fac_res.get("person"),
                    "faculty_list": fac_res.get("faculty_list"),
                    "grouped_faculty": fac_res.get("grouped_faculty"),
                    "dept_name": fac_res.get("dept_name"),
                    "answering_source": source_config.FACULTY_PROFILES_COLLECTION_NAME,
                }
                return single_stream(), [], meta
        except Exception as e:
            print(f"[hybrid_rag] Error in faculty streaming: {e}. Falling through to RAG.")

    # 2. Base Stream if new KB disabled
    col_orig = rag.get_collection(DB_DIR, source_config.ORIGINAL_COLLECTION_NAME)
    if not source_config.ENABLE_NEW_KB_SOURCE:
        gen, hits, cards, timing = rag.ask_stream(client, col_orig, expanded_question, history)
        log_debug_routing(
            original_query=question,
            expanded_query=expanded_question,
            intent=intent,
            extracted_entity=extracted_entity,
            top_matches="mce_docs chunks",
            answering_source=source_config.ORIGINAL_COLLECTION_NAME,
        )
        return gen, hits, timing

    # 3. Hybrid Multi-Source Stream using expanded query
    hits_orig = rag.retrieve(client, col_orig, expanded_question, top_k=rag.TOP_K)
    hits_new = retrieve_new_source(client, expanded_question, top_k=6)

    combined_hits = list(hits_orig)
    seen_texts = {h["text"] for h in hits_orig}
    for h in hits_new:
        if h["text"] not in seen_texts:
            seen_texts.add(h["text"])
            combined_hits.append(h)
    combined_hits = combined_hits[:10]

    sources_used = sorted(set(h.get("source", "unknown") for h in combined_hits))
    answering_source_str = ", ".join(sources_used) if sources_used else "None"

    log_debug_routing(
        original_query=question,
        expanded_query=expanded_question,
        intent=intent,
        extracted_entity=extracted_entity,
        top_matches=f"{len(combined_hits)} chunks from {answering_source_str}",
        answering_source=answering_source_str,
    )

    if not combined_hits:
        def no_info_stream():
            yield rag.NO_INFO

        return no_info_stream(), [], {"retrieval": "empty"}

    context_blocks = []
    for h in combined_hits:
        context_blocks.append(f"[{h['source']}, page {h['page']}]\n{h['text']}")
    context = "\n\n".join(context_blocks)

    clean_history = [
        {"role": m["role"], "content": m["content"].strip()}
        for m in history
        if m.get("content") and m["content"].strip()
    ]
    messages = [{"role": "system", "content": rag.SYSTEM_PROMPT}]
    messages += clean_history[-4:]
    messages.append({
        "role": "user",
        "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}",
    })

    def token_stream():
        accumulated: list[str] = []
        clean_messages = []
        for m in messages:
            c = (m.get("content") or "").strip()
            if c:
                clean_messages.append({"role": m["role"], "content": c})
        if not clean_messages:
            yield rag.NO_INFO
            return
        try:
            stream = client.chat_stream(model=rag.CHAT_MODEL, temperature=0, messages=clean_messages)
            for event in stream:
                if event.type == "content-delta" and event.delta and event.delta.message and event.delta.message.content:
                    d_text = event.delta.message.content.text
                    if d_text:
                        accumulated.append(d_text)
                        yield d_text
        except Exception as e:
            fallback = f"Error during streaming: {e}"
            yield fallback

    return token_stream(), combined_hits, {
        "type": "hybrid_rag",
        "sources_count": len(combined_hits),
        "answering_source": answering_source_str,
    }
