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


_NEW_KB_BM25_INDEX: Any = None
_NEW_KB_DOCS: list[str] = []
_NEW_KB_METAS: list[dict] = []
_NEW_KB_DOC_IDS: list[str] = []


def get_new_kb_bm25_index(collection: Any) -> tuple[Any, list[str], list[dict], list[str]]:
    """Build and cache BM25 index over the new knowledge base collection."""
    global _NEW_KB_BM25_INDEX, _NEW_KB_DOCS, _NEW_KB_METAS, _NEW_KB_DOC_IDS
    if _NEW_KB_BM25_INDEX is not None and _NEW_KB_DOCS:
        return _NEW_KB_BM25_INDEX, _NEW_KB_DOCS, _NEW_KB_METAS, _NEW_KB_DOC_IDS

    if collection.count() == 0:
        return None, [], [], []

    data = collection.get(include=["documents", "metadatas"])
    _NEW_KB_DOCS = data.get("documents", [])
    _NEW_KB_METAS = data.get("metadatas", [])
    _NEW_KB_DOC_IDS = data.get("ids", [])

    if not _NEW_KB_DOCS:
        return None, [], [], []

    import rank_bm25
    corpus = [re.findall(r"\w+", doc.lower()) for doc in _NEW_KB_DOCS]
    _NEW_KB_BM25_INDEX = rank_bm25.BM25Okapi(corpus)
    return _NEW_KB_BM25_INDEX, _NEW_KB_DOCS, _NEW_KB_METAS, _NEW_KB_DOC_IDS


def retrieve_new_source(client: Any, query: str, top_k: int = 8) -> list[dict]:
    """Retrieve top chunks from 'kb_new_folder' using hybrid Vector + BM25 retrieval."""
    if not source_config.ENABLE_NEW_KB_SOURCE:
        return []

    client_db = chromadb.PersistentClient(path=str(DB_DIR))
    try:
        col = client_db.get_collection(source_config.NEW_KB_COLLECTION_NAME)
    except Exception:
        return []

    if col.count() == 0:
        return []

    # 1. Dense vector search
    q_clean = query.strip()
    if rag.is_cohere_quota_exhausted():
        q_emb = None
    elif q_clean in rag._QUERY_EMBED_CACHE:
        q_emb = rag._QUERY_EMBED_CACHE[q_clean]
    else:
        model = os.getenv("COHERE_EMBED_MODEL", "embed-english-v3.0")
        try:
            res = client.embed(
                model=model,
                input_type="search_query",
                embedding_types=["float"],
                texts=[q_clean],
            )
            q_emb = res.embeddings.float_[0]
            if len(rag._QUERY_EMBED_CACHE) > 500:
                rag._QUERY_EMBED_CACHE.clear()
            rag._QUERY_EMBED_CACHE[q_clean] = q_emb
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "rate" in err_msg or "quota" in err_msg or "too many requests" in err_msg:
                rag.mark_cohere_quota_exhausted(60.0)
            q_emb = None

    vec_hits: list[dict] = []
    if q_emb is not None:
        try:
            results = col.query(
                query_embeddings=[q_emb],
                n_results=min(top_k * 2, col.count()),
                include=["documents", "metadatas", "distances"],
            )
            if results and results.get("documents"):
                docs = results["documents"][0]
                metas = results["metadatas"][0]
                dists = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
                ids = results["ids"][0] if results.get("ids") else [""] * len(docs)
                for doc, meta, dist, cid in zip(docs, metas, dists, ids):
                    vec_hits.append({
                        "id": cid,
                        "text": doc,
                        "source": meta.get("source", "new_kb_folder"),
                        "page": meta.get("page", 1),
                        "distance": dist,
                        "is_new_source": True,
                    })
        except Exception:
            pass

    # 2. BM25 keyword search
    bm25_hits: list[dict] = []
    bm25, b_docs, b_metas, b_ids = get_new_kb_bm25_index(col)
    if bm25 and b_docs:
        tokens = re.findall(r"\w+", query.lower())
        if tokens:
            scores = bm25.get_scores(tokens)
            top_bm25_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k * 2]
            for idx in top_bm25_indices:
                if scores[idx] > 3.0:
                    meta = b_metas[idx] if idx < len(b_metas) else {}
                    bm25_hits.append({
                        "id": b_ids[idx] if idx < len(b_ids) else f"new-bm25-{idx}",
                        "text": b_docs[idx],
                        "source": meta.get("source", "new_kb_folder"),
                        "page": meta.get("page", 1),
                        "bm25_score": float(scores[idx]),
                        "is_new_source": True,
                    })

    # 3. Reciprocal Rank Fusion (RRF k=60)
    rrf_scores: dict[str, float] = {}
    hits_by_id: dict[str, dict] = {}

    for rank, h in enumerate(vec_hits, start=1):
        cid = h["id"]
        hits_by_id[cid] = h
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (60.0 + rank))

    for rank, h in enumerate(bm25_hits, start=1):
        cid = h["id"]
        if cid not in hits_by_id:
            hits_by_id[cid] = h
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (60.0 + rank))

    # Sort candidates by combined RRF score
    sorted_candidates = sorted(hits_by_id.values(), key=lambda h: rrf_scores.get(h["id"], 0.0), reverse=True)
    selected_hits = sorted_candidates[:top_k]

    # Assign effective distance for downstream sorting
    for h in selected_hits:
        cid = h["id"]
        rrf = rrf_scores.get(cid, 0.0)
        # Scale RRF into effective distance (0.25 - 0.45 range)
        h["distance"] = round(max(0.20, 0.55 - (rrf * 15.0)), 4)

    return selected_hits


def merge_and_rank_hits(hits_orig: list[dict], hits_new: list[dict], max_hits: int = 14) -> list[dict]:
    """Deduplicate and rank hits from baseline and additional knowledge bases by semantic similarity."""
    seen_texts = set()
    combined = []
    for h in hits_new + hits_orig:
        txt = (h.get("text") or "").strip()
        if txt and txt not in seen_texts:
            seen_texts.add(txt)
            combined.append(h)
    # Lower distance = closer semantic match
    combined.sort(key=lambda x: x.get("distance", 1.0))
    return combined[:max_hits]


def sanitize_messages_for_cohere(messages: list[dict]) -> list[dict]:
    """Ensure messages have non-empty content and valid alternating roles for Cohere API."""
    cleaned = []
    for m in messages:
        content = (m.get("content") or "").strip()
        role = m.get("role", "user")
        if not content:
            continue
        if role not in ("system", "user", "assistant"):
            role = "user"
        cleaned.append({"role": role, "content": content})

    if not cleaned:
        return []

    final_messages = []
    idx = 0
    if cleaned[0]["role"] == "system":
        final_messages.append(cleaned[0])
        idx = 1

    for m in cleaned[idx:]:
        if not final_messages or final_messages[-1]["role"] == "system":
            if m["role"] == "user":
                final_messages.append(m)
        else:
            if m["role"] != final_messages[-1]["role"]:
                final_messages.append(m)
            else:
                final_messages[-1]["content"] += "\n\n" + m["content"]

    return final_messages


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
                    top_matches=(fac_res.get("person") or {}).get("name") or fac_res.get("dept_name") or status,
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
                    "heading": fac_res.get("heading"),
                    "overview_markdown": fac_res.get("overview_markdown"),
                    "footer_markdown": fac_res.get("footer_markdown"),
                    "message": msg,
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
    hits_new = retrieve_new_source(client, expanded_question, top_k=8)

    # Merge hits: prioritize most relevant chunks across all sources by semantic distance
    combined_hits = merge_and_rank_hits(hits_orig, hits_new, max_hits=14)

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

    raw_messages = [{"role": "system", "content": rag.SYSTEM_PROMPT}]
    for m in history[-4:]:
        c = (m.get("content") or "").strip()
        if c:
            raw_messages.append({"role": m.get("role", "user"), "content": c})
    raw_messages.append({
        "role": "user",
        "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}",
    })
    messages = sanitize_messages_for_cohere(raw_messages)

    # LLM Chat Synthesis
    raw_answer = rag._chat(client, messages, model=rag.CHAT_MODEL)
    clean_answer = rag.strip_sources(raw_answer) if raw_answer else ""
    if not clean_answer and combined_hits:
        clean_answer = rag.synthesize_from_hits(question, combined_hits)
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
                    top_matches=(fac_res.get("person") or {}).get("name") or fac_res.get("dept_name") or status,
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
                    "heading": fac_res.get("heading"),
                    "overview_markdown": fac_res.get("overview_markdown"),
                    "footer_markdown": fac_res.get("footer_markdown"),
                    "message": msg,
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
    hits_new = retrieve_new_source(client, expanded_question, top_k=8)

    combined_hits = merge_and_rank_hits(hits_orig, hits_new, max_hits=14)

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

    raw_messages = [{"role": "system", "content": rag.SYSTEM_PROMPT}]
    for m in history[-4:]:
        c = (m.get("content") or "").strip()
        if c:
            raw_messages.append({"role": m.get("role", "user"), "content": c})
    raw_messages.append({
        "role": "user",
        "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}",
    })
    messages = sanitize_messages_for_cohere(raw_messages)

    def token_stream():
        accumulated: list[str] = []
        if not messages:
            yield rag.NO_INFO
            return
        if rag.is_cohere_quota_exhausted():
            synth = rag.synthesize_from_hits(question, combined_hits)
            yield synth
            return
        try:
            stream = client.chat_stream(
                model=rag.CHAT_MODEL,
                temperature=0,
                messages=messages,
                request_options={"max_retries": 1, "timeout_in_seconds": 15.0}
            )
            for event in stream:
                if event.type == "content-delta":
                    delta = getattr(event, "delta", None)
                    msg = getattr(delta, "message", None)
                    content = getattr(msg, "content", None)
                    d_text = getattr(content, "text", None)
                    if d_text:
                        accumulated.append(d_text)
                        yield d_text
                elif event.type == "message-end":
                    break
            # If nothing was accumulated (e.g. only thinking tokens or stream closed), fallback to _chat
            if not accumulated:
                direct_ans = rag._chat(client, messages, model=rag.CHAT_MODEL)
                if direct_ans:
                    yield direct_ans
                    return
                elif combined_hits:
                    synth = rag.synthesize_from_hits(question, combined_hits)
                    yield synth
                    return
        except Exception as e:
            err_str = str(e).lower()
            # If rate-limited or quota exceeded, avoid burning time on another failing API call
            if "429" in err_str or "rate" in err_str or "too many requests" in err_str or "quota" in err_str:
                if combined_hits:
                    synth = rag.synthesize_from_hits(question, combined_hits)
                    yield synth
                    return
                else:
                    yield "I couldn't find specific details for that in the college documents. You can ask about: departments, HODs, faculty, placements, admissions, hostels, and facilities."
                    return

            # Try a direct fallback without conversation history for non-429 errors
            try:
                simple_messages = [
                    {"role": "system", "content": rag.SYSTEM_PROMPT},
                    {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"}
                ]
                direct_ans = rag._chat(client, simple_messages, model=rag.CHAT_MODEL)
                if direct_ans:
                    yield direct_ans
                    return
            except Exception:
                pass

            if combined_hits:
                synth = rag.synthesize_from_hits(question, combined_hits)
                yield synth
                return

            fallback = "I couldn't find specific details for that in the college documents. You can ask about: departments, HODs, faculty, placements, admissions, hostels, and facilities."
            yield fallback

    return token_stream(), combined_hits, {
        "type": "hybrid_rag",
        "sources_count": len(combined_hits),
        "answering_source": answering_source_str,
    }
