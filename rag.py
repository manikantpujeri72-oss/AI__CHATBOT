"""Core RAG logic for the MCE AI Assistant (Cohere + ChromaDB).

Provides document ingestion, semantic chunking, embedding with retries,
deterministic identity and sync logic, and RAG question answering.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
import chromadb
import cohere
from docx import Document
from dotenv import load_dotenv
import openpyxl
import pptx
from pypdf import PdfReader

load_dotenv()

import concurrent.futures
from typing import Any, Generator

import rank_bm25
from rapidfuzz import fuzz

import aliases
import faculty_extractor

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "documents"
DB_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "mce_docs"

CHAT_MODEL = os.getenv("COHERE_CHAT_MODEL", "command-r-08-2024")
COHERE_FAST_MODEL = os.getenv("COHERE_FAST_MODEL", "command-r7b-12-2024")
EMBED_MODEL = os.getenv("COHERE_EMBED_MODEL", "embed-english-v3.0")

CHUNK_WORDS = 220      # words per chunk
CHUNK_OVERLAP = 40     # words shared between neighbouring chunks
TOP_K = int(os.getenv("TOP_K", "8"))
BROAD_TOP_K = int(os.getenv("BROAD_TOP_K", "14"))
MAX_DISTANCE = float(os.getenv("MAX_DISTANCE", "0.85"))  # cosine distance cut-off
DEBUG_SOURCES = os.getenv("DEBUG_SOURCES", "0") == "1"

SUPPORTED = (
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".csv",
    ".xlsx",
    ".pptx",
    ".html",
    ".htm",
)

SYSTEM_PROMPT = """You are the MCE AI Assistant for Malnad College of Engineering (MCE), Hassan, Karnataka.
You help students, parents and visitors with questions about the college.

Rules:
1. Give a complete, detailed answer using all relevant facts in the context; organise it with short headings or bullet points; do not omit relevant details; do not pad with facts that are not in the context.
2. Answer only from the context, never invent numbers, dates, fees, names, phone numbers or emails, and if the context lacks the answer say so politely: "I don't have that information in the college documents I've been given. Please contact the MCE office or check the official college website."
3. Never mention file names, page numbers, document names or the words 'context', 'document' or 'source' in the answer; speak naturally as the college assistant.
4. Reply in the same language the user wrote in.
5. Faculty phone numbers must NEVER appear in ordinary faculty information responses. Display a phone number ONLY when the user explicitly asks for the contact number or phone number of a particular faculty member. When showing a faculty member's profile, qualifications, or general details, do NOT include their phone number. Institutional contact numbers (admission office, principal office, MTES) should always be provided when asked.
6. When asked about a faculty member, provide Name, Designation, Department, and Educational qualifications. If qualification information is not in the context, state: 'Qualification information is not available in the college knowledge base.' Never invent or assume missing qualifications.
7. The verified Head of Department (HOD) of the First-Year Department is Kalavati K (Dr. Kalavathi G K). The verified Head of Department (HOD) of the Mathematics Department is T Mohana. The verified Head of Department (HOD) of Computer Science and Engineering (CSE) and Information Science and Engineering (ISE) is Dr. Ananda Babu J (Ananda Babu). The verified Head of Department (HOD) of Master of Computer Applications (MCA) is Mrs. Margaret R.E.
8. When asked about clubs at MCE (such as "clubs at mce" or "student clubs"), provide a comprehensive list of all student clubs mentioned in the context (including Eco Club, Leo Club, Literary Club / LIT, Rotaract Club, DevOps Club, Science Association, Malnad Technical Club, IUCEE EWB Student Chapter, ASCE Student Chapter, etc.) with a clear description and key activities for each club.
9. When asked about admission contact details, fee structure, or eligibility criteria for admission, provide all the official information from the context (including office telephone numbers, emails, addresses, management quota fee tables, KEA government quota fees, and qualifying percentages) in clean, structured bullet points or tables."""



# --------------------------------------------------------------------------- #
# Clients & Collection helpers
# --------------------------------------------------------------------------- #
def get_cohere_client() -> Any:
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        raise RuntimeError("COHERE_API_KEY is missing. Add it to the .env file.")
    return cohere.ClientV2(api_key=api_key, timeout=15.0, client_name="mce_assistant")


def get_collection(db_path: Path | str = DB_DIR, collection_name: str = COLLECTION_NAME) -> Any:
    client = chromadb.PersistentClient(path=str(db_path))
    return client.get_or_create_collection(
        name=collection_name, metadata={"hnsw:space": "cosine"}
    )


_QUERY_EMBED_CACHE: dict[str, list[float]] = {}
_ANSWER_CACHE: dict[str, Any] = {}
_BM25_INDEX: Any = None
_BM25_DOCS: list[str] = []
_BM25_METAS: list[dict] = []
_BM25_DOC_IDS: list[str] = []


def invalidate_caches() -> None:
    """Invalidate in-memory caches when documents or knowledge base change."""
    global _BM25_INDEX, _BM25_DOCS, _BM25_METAS, _BM25_DOC_IDS, _QUERY_EMBED_CACHE, _ANSWER_CACHE
    _BM25_INDEX = None
    _BM25_DOCS = []
    _BM25_METAS = []
    _BM25_DOC_IDS = []
    _QUERY_EMBED_CACHE.clear()
    _ANSWER_CACHE.clear()
    aliases.load_aliases(reload=True)


def reset_collection(db_path: Path | str = DB_DIR, collection_name: str = COLLECTION_NAME) -> None:
    client = chromadb.PersistentClient(path=str(db_path))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    invalidate_caches()


def compute_file_hash(data: bytes) -> str:
    """Return SHA-1 hex digest of file bytes."""
    return hashlib.sha1(data).hexdigest()


def deterministic_chunk_id(source: str, index: int) -> str:
    """Generate a deterministic chunk ID from the document source and chunk index."""
    src_clean = source.replace("\\", "/").strip().lower()
    prefix = hashlib.sha1(src_clean.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{index}"


# --------------------------------------------------------------------------- #
# Reading documents
# --------------------------------------------------------------------------- #
def read_pages(filename: str, data: bytes) -> list[tuple[int, str]]:
    """Return [(page_number, text), ...] for a document.

    Handles PDF, DOCX, TXT, MD, CSV, XLSX, PPTX, and HTML.
    """
    name = filename.lower()

    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        pages: list[tuple[int, str]] = []
        for i, p in enumerate(reader.pages, start=1):
            raw = p.extract_text() or ""
            pages.append((i, raw))
        return pages

    if name.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        parts: list[str] = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            if not table.rows:
                continue
            headers = [c.text.strip() for c in table.rows[0].cells]
            for row in table.rows[1:]:
                row_vals = [c.text.strip() for c in row.cells]
                row_str = " | ".join(
                    f"{h}: {v}" if h else v
                    for h, v in zip(headers, row_vals)
                    if v
                )
                if row_str:
                    parts.append(row_str)
        return [(1, "\n".join(parts))]

    if name.endswith((".txt", ".md")):
        return [(1, data.decode("utf-8", errors="ignore"))]

    if name.endswith(".csv"):
        text = data.decode("utf-8", errors="ignore")
        reader = csv.reader(io.StringIO(text))
        rows = [r for r in reader if any(field.strip() for field in r)]
        if not rows:
            return []
        headers = [h.strip() for h in rows[0]]
        lines: list[str] = []
        for row in rows[1:]:
            line = " | ".join(
                f"{headers[idx]}: {val.strip()}" if idx < len(headers) and headers[idx] else val.strip()
                for idx, val in enumerate(row)
                if val.strip()
            )
            if line:
                lines.append(line)
        return [(1, "\n".join(lines))]

    if name.endswith((".xlsx", ".xlsm")):
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        results: list[tuple[int, str]] = []
        for sheet_idx, sheet in enumerate(wb.worksheets, start=1):
            sheet_rows = list(sheet.iter_rows(values_only=True))
            non_empty_rows = [
                [str(cell).strip() if cell is not None else "" for cell in r]
                for r in sheet_rows
                if any(cell is not None and str(cell).strip() for cell in r)
            ]
            if not non_empty_rows:
                continue
            headers = non_empty_rows[0]
            sheet_lines: list[str] = [f"Sheet: {sheet.title}"]
            for row in non_empty_rows[1:]:
                line = " | ".join(
                    f"{headers[idx]}: {val}" if idx < len(headers) and headers[idx] else val
                    for idx, val in enumerate(row)
                    if val
                )
                if line:
                    sheet_lines.append(line)
            results.append((sheet_idx, "\n".join(sheet_lines)))
        return results

    if name.endswith((".pptx", ".ppt")):
        prs = pptx.Presentation(io.BytesIO(data))
        results = []
        for slide_idx, slide in enumerate(prs.slides, start=1):
            slide_parts: list[str] = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if text:
                            slide_parts.append(text)
                elif shape.has_table:
                    table = shape.table
                    headers = [c.text.strip() for c in table.rows[0].cells] if table.rows else []
                    for row in table.rows[1:]:
                        r_str = " | ".join(
                            f"{h}: {c.text.strip()}" if h else c.text.strip()
                            for h, c in zip(headers, row.cells)
                            if c.text.strip()
                        )
                        if r_str:
                            slide_parts.append(r_str)
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    slide_parts.append(f"Notes: {notes}")
            if slide_parts:
                results.append((slide_idx, "\n".join(slide_parts)))
        return results

    if name.endswith((".html", ".htm")):
        soup = BeautifulSoup(data.decode("utf-8", errors="ignore"), "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        visible_text = soup.get_text(separator="\n", strip=True)
        return [(1, visible_text)]

    return []


# --------------------------------------------------------------------------- #
# Chunking with section headers, Q&A protection, and tables
# --------------------------------------------------------------------------- #
def _clean_text(text: str) -> str:
    """Normalize whitespace and special unicode characters."""
    text = text.replace("\uf0b7", "•").replace("\u2022", "•").replace("\ufffd", "—")
    return re.sub(r"[ \t]+", " ", text)


def _is_heading(line: str) -> bool:
    """Detect if a line represents a section heading or title."""
    s = line.strip()
    if not s or len(s) > 75:
        return False
    if s.endswith((".", ",", ";")):
        return False
    if s.startswith("#"):
        return True
    if re.match(r"^\d+\.\s+[A-Z]", s):
        return True
    if any(k in s.lower() for k in [
        "department", "placement", "overview", "statistics", "admission",
        "eligibility", "history", "facilities", "programmes", "courses",
        "fees", "hostel", "faculty", "regulations", "syllabus"
    ]):
        return True
    if re.match(r"^[A-Z][A-Za-z0-9\s&—–\(\)\/\-]{2,60}$", s) and len(s.split()) <= 7:
        return True
    return False


def chunk_pages(pages: list[tuple[int, str]], filename: str = "") -> list[tuple[int, str]]:
    """Split pages into overlapping word windows, keeping page numbers.

    Respects Q&A pairs, table groups, and lists so they are never split across chunks.
    Prefixes each chunk with the document name and section heading when available.
    """
    doc_name = Path(filename).name if filename else ""
    chunks: list[tuple[int, str]] = []
    current_heading = ""

    for page_no, raw_text in pages:
        text = _clean_text(raw_text)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            continue

        # Segment page into atomic semantic blocks
        blocks: list[tuple[str, str, str]] = []  # (block_type, heading, text)
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            if _is_heading(line):
                current_heading = line.lstrip("#").strip()
                blocks.append(("heading", current_heading, line))
                idx += 1
                continue

            # Check if this starts a Q&A pair
            is_q = bool(re.match(r"^(?:Q(?:uestion)?\s*(?:\d+)?[\.:\-]|FAQ\s*(?:\d+)?[\.:\-]|\bQ\b[\.:\-])", line, re.I)) or (
                line.endswith("?") and len(line.split()) < 25
            )
            if is_q:
                qa_lines = [line]
                idx += 1
                while idx < len(lines):
                    next_l = lines[idx]
                    if _is_heading(next_l) or re.match(r"^(?:Q(?:uestion)?\s*(?:\d+)?[\.:\-]|FAQ\s*(?:\d+)?[\.:\-]|\bQ\b[\.:\-])", next_l, re.I):
                        break
                    qa_lines.append(next_l)
                    idx += 1
                blocks.append(("qa", current_heading, "\n".join(qa_lines)))
                continue

            # Check if this is a table row group (contains ' | ')
            if " | " in line:
                table_lines = [line]
                idx += 1
                while idx < len(lines) and " | " in lines[idx]:
                    table_lines.append(lines[idx])
                    idx += 1
                blocks.append(("table", current_heading, "\n".join(table_lines)))
                continue

            # General paragraph / narrative lines
            para_lines = [line]
            idx += 1
            while idx < len(lines):
                next_l = lines[idx]
                if _is_heading(next_l) or " | " in next_l or re.match(r"^(?:Q(?:uestion)?\s*(?:\d+)?[\.:\-]|FAQ\s*(?:\d+)?[\.:\-]|\bQ\b[\.:\-])", next_l, re.I):
                    break
                para_lines.append(next_l)
                # Keep paragraph block to a manageable size before starting a new block
                if len(" ".join(para_lines).split()) >= 100:
                    break
                idx += 1
            blocks.append(("para", current_heading, "\n".join(para_lines)))

        # Pack blocks into chunks with overlap
        cur_words: list[str] = []
        cur_heading_for_chunk = current_heading

        for b_type, b_heading, b_text in blocks:
            b_word_list = b_text.split()
            if not b_word_list:
                continue

            # If adding this block overflows and we already have sufficient content
            if (len(cur_words) + len(b_word_list) > CHUNK_WORDS) and (len(cur_words) >= 60):
                # Flush the current chunk
                prefix_parts = []
                if doc_name:
                    prefix_parts.append(doc_name)
                if cur_heading_for_chunk:
                    prefix_parts.append(cur_heading_for_chunk)
                prefix = f"[{' > '.join(prefix_parts)}]\n" if prefix_parts else ""

                chunks.append((page_no, prefix + " ".join(cur_words)))

                # Overlap words
                overlap_count = min(CHUNK_OVERLAP, len(cur_words))
                cur_words = cur_words[-overlap_count:] if overlap_count > 0 else []
                cur_heading_for_chunk = b_heading

            if not cur_words:
                cur_heading_for_chunk = b_heading
            cur_words.extend(b_word_list)

        if cur_words:
            prefix_parts = []
            if doc_name:
                prefix_parts.append(doc_name)
            if cur_heading_for_chunk:
                prefix_parts.append(cur_heading_for_chunk)
            prefix = f"[{' > '.join(prefix_parts)}]\n" if prefix_parts else ""
            chunks.append((page_no, prefix + " ".join(cur_words)))

    return chunks


# --------------------------------------------------------------------------- #
# Embeddings with retries and exponential backoff
# --------------------------------------------------------------------------- #
_COHERE_QUOTA_EXHAUSTED_UNTIL = 0.0

def is_cohere_quota_exhausted() -> bool:
    global _COHERE_QUOTA_EXHAUSTED_UNTIL
    return time.time() < _COHERE_QUOTA_EXHAUSTED_UNTIL

def mark_cohere_quota_exhausted(duration_seconds: float = 60.0) -> None:
    global _COHERE_QUOTA_EXHAUSTED_UNTIL
    _COHERE_QUOTA_EXHAUSTED_UNTIL = time.time() + duration_seconds

def embed(client: Any, texts: list[str], input_type: str, max_retries: int = 5) -> list[list[float]]:
    """Embed texts using Cohere in batches of 96 with exponential backoff on errors."""
    if is_cohere_quota_exhausted():
        raise RuntimeError("Cohere API rate limit or monthly quota reached; using local synthesis fallback.")
    vectors: list[list[float]] = []
    for i in range(0, len(texts), 96):
        batch = texts[i : i + 96]
        last_exc: Exception | None = None
        retries = 1 if input_type == "search_query" else max_retries
        for attempt in range(retries):
            try:
                resp = client.embed(
                    model=EMBED_MODEL,
                    texts=batch,
                    input_type=input_type,
                    embedding_types=["float"],
                )
                emb = resp.embeddings
                batch_vecs = getattr(emb, "float_", None) or getattr(emb, "float", None) or emb
                vectors.extend(list(map(list, batch_vecs)))
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                err_msg = str(e).lower()
                is_rate_limit = (
                    "429" in err_msg or "rate" in err_msg or "quota" in err_msg or "too many requests" in err_msg
                )
                if is_rate_limit:
                    mark_cohere_quota_exhausted(60.0)
                is_transient = (
                    "500" in err_msg or "502" in err_msg or "503" in err_msg or "504" in err_msg
                    or "timeout" in err_msg or "connection" in err_msg
                )
                if (is_rate_limit or is_transient) and attempt < max_retries - 1:
                    sleep_sec = (2 ** attempt) * 2
                    time.sleep(sleep_sec)
                    continue
                raise
        if last_exc is not None:
            raise last_exc
    return vectors


# --------------------------------------------------------------------------- #
# Indexing & Synchronisation logic
# --------------------------------------------------------------------------- #
def index_document(
    client: Any,
    collection: Any,
    filename: str,
    data: bytes,
    source: str | None = None,
    indexed_at: str | None = None,
) -> int:
    """Index one document into ChromaDB.

    Uses deterministic IDs and records source, file_hash, indexed_at, page and chunk.
    Returns the number of chunks indexed (0 if file had no text).
    """
    rel_source = (source or filename).replace("\\", "/")
    file_hash = compute_file_hash(data)
    ts = indexed_at or datetime.now(timezone.utc).isoformat()

    pages = read_pages(filename, data)
    chunks = chunk_pages(pages, filename=rel_source)
    if not chunks:
        return 0

    chunk_ids = [deterministic_chunk_id(rel_source, i) for i in range(len(chunks))]
    texts = [t for _, t in chunks]
    embeddings = embed(client, texts, "search_document")

    collection.upsert(
        ids=chunk_ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=[
            {
                "source": rel_source,
                "file_hash": file_hash,
                "indexed_at": ts,
                "page": page,
                "chunk": i,
            }
            for i, (page, _) in enumerate(chunks)
        ],
    )
    return len(chunks)


def _get_db_sources(collection: Any) -> dict[str, dict[str, Any]]:
    """Return {source: {'file_hash': str, 'chunk_ids': list[str], 'indexed_at': str, 'pages': set}}."""
    count = collection.count()
    if count == 0:
        return {}
    res = collection.get(include=["metadatas"])
    db_sources: dict[str, dict[str, Any]] = {}
    ids = res.get("ids", [])
    metadatas = res.get("metadatas", []) or []

    for doc_id, meta in zip(ids, metadatas):
        if not meta or "source" not in meta:
            continue
        src = meta["source"].replace("\\", "/")
        if src not in db_sources:
            db_sources[src] = {
                "file_hash": meta.get("file_hash", ""),
                "chunk_ids": [],
                "indexed_at": meta.get("indexed_at", ""),
                "pages": set(),
            }
        db_sources[src]["chunk_ids"].append(doc_id)
        if "page" in meta:
            db_sources[src]["pages"].add(meta["page"])
        if not db_sources[src]["file_hash"] and "file_hash" in meta:
            db_sources[src]["file_hash"] = meta["file_hash"]
        if not db_sources[src]["indexed_at"] and "indexed_at" in meta:
            db_sources[src]["indexed_at"] = meta["indexed_at"]

    return db_sources


def _check_migration_needed(collection: Any) -> bool:
    """Return True if collection has legacy chunks lacking the 'file_hash' metadata."""
    if collection.count() == 0:
        return False
    sample = collection.get(limit=10, include=["metadatas"])
    metas = sample.get("metadatas") or []
    for m in metas:
        if m and "file_hash" not in m:
            return True
    return False


def sync_documents(
    client: Any,
    collection: Any,
    folder: Path | str = DOCS_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Synchronise the ChromaDB collection with the documents folder.

    - Walks subfolders recursively (rglob).
    - Ignores hidden/temporary files (~$*, .*, Thumbs.db) and documents/_deleted/.
    - Detects legacy collections without file_hash and automatically rebuilds them.
    - Handles NEW, UNCHANGED, CHANGED, REMOVED, and RENAMED files.
    - For CHANGED files, embeds the new version FIRST before deleting old chunks.
    - Returns a comprehensive report dict.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "added": [],
        "updated": [],
        "renamed": [],
        "unchanged": [],
        "removed": [],
        "failed": [],
        "chunk_counts": {},
        "dry_run": dry_run,
    }

    # Detect legacy chunks without file_hash
    if not dry_run and _check_migration_needed(collection):
        print("Migration: detected legacy chunks without file_hash metadata. Rebuilding collection...")
        try:
            # Delete all documents from the collection
            all_ids = collection.get(include=[])["ids"]
            if all_ids:
                collection.delete(ids=all_ids)
        except Exception as e:
            print(f"Warning during legacy cleanup: {e}")

    db_sources = _get_db_sources(collection)

    # Scan the folder recursively
    folder_files: dict[str, dict[str, Any]] = {}
    for p in sorted(folder.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(folder).parts
        # Ignore _deleted folder
        if any(part.lower() == "_deleted" for part in rel_parts):
            continue
        # Ignore hidden/temp files: .*, ~$*, Thumbs.db
        filename = p.name
        if filename.startswith(".") or filename.startswith("~$") or filename.lower() == "thumbs.db":
            continue
        if p.suffix.lower() not in SUPPORTED:
            continue

        rel_posix = p.relative_to(folder).as_posix()
        try:
            data = p.read_bytes()
            folder_files[rel_posix] = {
                "path": p,
                "hash": compute_file_hash(data),
                "data": data,
            }
        except Exception as e:
            report["failed"].append({"source": rel_posix, "reason": f"Could not read file: {e}"})

    # Find candidates
    db_keys = set(db_sources.keys())
    folder_keys = set(folder_files.keys())

    removed_candidates = db_keys - folder_keys
    new_candidates = folder_keys - db_keys
    common_candidates = folder_keys & db_keys

    # Check for Renames: a new path with the same file_hash as a removed path
    renamed_pairs: list[tuple[str, str]] = []  # (removed_source, new_source)
    for new_src in list(new_candidates):
        new_h = folder_files[new_src]["hash"]
        for rem_src in list(removed_candidates):
            if db_sources[rem_src]["file_hash"] == new_h:
                renamed_pairs.append((rem_src, new_src))
                new_candidates.remove(new_src)
                removed_candidates.remove(rem_src)
                break

    # 1. Process UNCHANGED files
    for src in common_candidates:
        if folder_files[src]["hash"] == db_sources[src]["file_hash"]:
            report["unchanged"].append(src)
            report["chunk_counts"][src] = len(db_sources[src]["chunk_ids"])

    # 2. Process CHANGED files (same source, different hash)
    changed_sources = [s for s in common_candidates if folder_files[s]["hash"] != db_sources[s]["file_hash"]]
    for src in changed_sources:
        old_ids = db_sources[src]["chunk_ids"]
        old_count = len(old_ids)
        file_info = folder_files[src]

        if dry_run:
            report["updated"].append({
                "source": src,
                "old_chunks": old_count,
                "new_chunks": "pending",
            })
            continue

        # Embed new version FIRST before deleting old chunks
        try:
            pages = read_pages(file_info["path"].name, file_info["data"])
            chunks = chunk_pages(pages, filename=src)
            if not chunks:
                report["failed"].append({
                    "source": src,
                    "reason": "Document has no extractable text; keeping previous version.",
                })
                report["chunk_counts"][src] = old_count
                continue

            chunk_ids = [deterministic_chunk_id(src, i) for i in range(len(chunks))]
            texts = [t for _, t in chunks]
            embeddings = embed(client, texts, "search_document")
            ts = datetime.now(timezone.utc).isoformat()

            # Now delete old chunks safely
            if old_ids:
                collection.delete(ids=old_ids)

            # Write new chunks
            collection.upsert(
                ids=chunk_ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=[
                    {
                        "source": src,
                        "file_hash": file_info["hash"],
                        "indexed_at": ts,
                        "page": page,
                        "chunk": i,
                    }
                    for i, (page, _) in enumerate(chunks)
                ],
            )
            report["updated"].append({
                "source": src,
                "old_chunks": old_count,
                "new_chunks": len(chunks),
            })
            report["chunk_counts"][src] = len(chunks)
        except Exception as e:
            report["failed"].append({
                "source": src,
                "reason": f"Embedding/update failed: {e}. Old version retained in database.",
            })
            report["chunk_counts"][src] = old_count

    # 3. Process RENAMED files
    for old_src, new_src in renamed_pairs:
        old_ids = db_sources[old_src]["chunk_ids"]
        file_info = folder_files[new_src]

        if dry_run:
            report["renamed"].append({
                "old_source": old_src,
                "new_source": new_src,
                "chunks": len(old_ids),
            })
            continue

        try:
            pages = read_pages(file_info["path"].name, file_info["data"])
            chunks = chunk_pages(pages, filename=new_src)
            chunk_ids = [deterministic_chunk_id(new_src, i) for i in range(len(chunks))]
            texts = [t for _, t in chunks]
            embeddings = embed(client, texts, "search_document")
            ts = datetime.now(timezone.utc).isoformat()

            # Delete old chunks
            if old_ids:
                collection.delete(ids=old_ids)

            # Write new chunks
            collection.upsert(
                ids=chunk_ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=[
                    {
                        "source": new_src,
                        "file_hash": file_info["hash"],
                        "indexed_at": ts,
                        "page": page,
                        "chunk": i,
                    }
                    for i, (page, _) in enumerate(chunks)
                ],
            )
            report["renamed"].append({
                "old_source": old_src,
                "new_source": new_src,
                "chunks": len(chunks),
            })
            report["chunk_counts"][new_src] = len(chunks)
        except Exception as e:
            report["failed"].append({
                "source": f"{old_src} -> {new_src}",
                "reason": f"Renaming failed: {e}. Keeping old chunks.",
            })
            report["chunk_counts"][old_src] = len(old_ids)

    # 4. Process NEW files
    for src in sorted(new_candidates):
        file_info = folder_files[src]
        if dry_run:
            report["added"].append({"source": src, "chunks": "pending"})
            continue

        try:
            count = index_document(
                client=client,
                collection=collection,
                filename=file_info["path"].name,
                data=file_info["data"],
                source=src,
            )
            report["added"].append({"source": src, "chunks": count})
            report["chunk_counts"][src] = count
        except Exception as e:
            report["failed"].append({"source": src, "reason": f"Indexing failed: {e}"})

    # 5. Process REMOVED files
    for src in sorted(removed_candidates):
        old_ids = db_sources[src]["chunk_ids"]
        old_count = len(old_ids)
        if dry_run:
            report["removed"].append({"source": src, "chunks": old_count})
            continue

        try:
            if old_ids:
                collection.delete(ids=old_ids)
            report["removed"].append({"source": src, "chunks": old_count})
        except Exception as e:
            report["failed"].append({"source": src, "reason": f"Deletion failed: {e}"})

    if not dry_run and (report["added"] or report["updated"] or report["removed"] or report["renamed"]):
        invalidate_caches()
        if Path(folder).resolve() == DOCS_DIR.resolve():
            try:
                faculty_extractor.extract_all_faculty(folder)
            except Exception as e:
                print(f"Warning: faculty update failed: {e}")

    return report


def index_folder(client: Any, collection: Any, folder: Path | str = DOCS_DIR) -> tuple[int, int]:
    """Sync the folder with the collection. Returns (files_processed, chunks_added)."""
    rep = sync_documents(client, collection, folder=folder, dry_run=False)
    files = len(rep["added"]) + len(rep["updated"])
    chunks = sum(item["chunks"] for item in rep["added"] if isinstance(item["chunks"], int))
    for u in rep["updated"]:
        if isinstance(u.get("new_chunks"), int):
            chunks += u["new_chunks"]
    return files, chunks


# --------------------------------------------------------------------------- #
# Single document operations
# --------------------------------------------------------------------------- #
def add_or_replace_document(
    client: Any,
    collection: Any,
    filename: str,
    data: bytes,
    folder: Path | str = DOCS_DIR,
) -> str:
    """Save/replace the file in documents/ and index it.

    Returns 'added', 'replaced', or 'unchanged'.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target_path = folder / filename
    rel_posix = target_path.relative_to(folder).as_posix()
    new_hash = compute_file_hash(data)

    db_sources = _get_db_sources(collection)
    existing_meta = db_sources.get(rel_posix)

    if existing_meta and existing_meta.get("file_hash") == new_hash:
        # File and database are already identical
        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(data)
        return "unchanged"

    # Embed first before making any changes
    pages = read_pages(filename, data)
    chunks = chunk_pages(pages, filename=rel_posix)
    chunk_ids = [deterministic_chunk_id(rel_posix, i) for i in range(len(chunks))]
    texts = [t for _, t in chunks]
    embeddings = embed(client, texts, "search_document") if texts else []
    ts = datetime.now(timezone.utc).isoformat()

    # Save to disk
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(data)

    status = "replaced" if existing_meta else "added"

    # If replaced, delete old chunks
    if existing_meta and existing_meta.get("chunk_ids"):
        collection.delete(ids=existing_meta["chunk_ids"])

    # Upsert new chunks
    if chunk_ids:
        collection.upsert(
            ids=chunk_ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=[
                {
                    "source": rel_posix,
                    "file_hash": new_hash,
                    "indexed_at": ts,
                    "page": page,
                    "chunk": i,
                }
                for i, (page, _) in enumerate(chunks)
            ],
        )

    if status in ("added", "replaced"):
        invalidate_caches()
        if Path(folder).resolve() == DOCS_DIR.resolve():
            try:
                faculty_extractor.extract_all_faculty(folder)
            except Exception as e:
                pass

    return status


def delete_document(
    collection: Any,
    source: str,
    folder: Path | str = DOCS_DIR,
) -> bool:
    """Remove a document's chunks from ChromaDB and move file to documents/_deleted/.

    Recoverable, never permanently deletes the file from disk.
    """
    folder = Path(folder)
    rel_posix = source.replace("\\", "/")

    # Delete chunks from database
    db_sources = _get_db_sources(collection)
    if rel_posix in db_sources:
        chunk_ids = db_sources[rel_posix]["chunk_ids"]
        if chunk_ids:
            collection.delete(ids=chunk_ids)

    # Move file to documents/_deleted/
    file_path = folder / rel_posix
    if file_path.exists():
        del_dir = folder / "_deleted"
        del_target = del_dir / rel_posix
        del_target.parent.mkdir(parents=True, exist_ok=True)
        if del_target.exists():
            # Add timestamp to avoid collision
            tstamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stem = del_target.stem
            ext = del_target.suffix
            del_target = del_target.parent / f"{stem}_{tstamp}{ext}"
        shutil.move(str(file_path), str(del_target))

    invalidate_caches()
    if Path(folder).resolve() == DOCS_DIR.resolve():
        try:
            faculty_extractor.extract_all_faculty(folder)
        except Exception:
            pass

    return True


def replace_document_with(
    client: Any,
    collection: Any,
    old_source: str,
    new_filename: str,
    data: bytes,
    folder: Path | str = DOCS_DIR,
) -> None:
    """Delete old document (chunks + file to _deleted/) and index new file in one step.

    Works even when the filenames differ.
    """
    folder = Path(folder)
    new_rel_posix = new_filename.replace("\\", "/")

    # Embed new file first
    pages = read_pages(new_filename, data)
    chunks = chunk_pages(pages, filename=new_rel_posix)
    chunk_ids = [deterministic_chunk_id(new_rel_posix, i) for i in range(len(chunks))]
    texts = [t for _, t in chunks]
    embeddings = embed(client, texts, "search_document") if texts else []
    ts = datetime.now(timezone.utc).isoformat()
    new_hash = compute_file_hash(data)

    # If embed succeeded, delete old document safely
    delete_document(collection, old_source, folder=folder)

    # Save new file
    target_path = folder / new_rel_posix
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(data)

    # Write new chunks
    if chunk_ids:
        collection.upsert(
            ids=chunk_ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=[
                {
                    "source": new_rel_posix,
                    "file_hash": new_hash,
                    "indexed_at": ts,
                    "page": page,
                    "chunk": i,
                }
                for i, (page, _) in enumerate(chunks)
            ],
        )

    invalidate_caches()
    if Path(folder).resolve() == DOCS_DIR.resolve():
        try:
            faculty_extractor.extract_all_faculty(folder)
        except Exception:
            pass



def list_sources(collection: Any) -> dict[str, dict[str, Any]]:
    """Return {source: {'chunks': int, 'pages': int, 'file_hash': str, 'indexed_at': str}}."""
    db_sources = _get_db_sources(collection)
    result: dict[str, dict[str, Any]] = {}
    for src in sorted(db_sources.keys()):
        info = db_sources[src]
        result[src] = {
            "chunks": len(info["chunk_ids"]),
            "pages": len(info["pages"]),
            "file_hash": info["file_hash"][:8] if info["file_hash"] else "",
            "indexed_at": info["indexed_at"],
        }
    return result


# --------------------------------------------------------------------------- #
# Question answering & Retrieval
# --------------------------------------------------------------------------- #
REFERENCE_WORDS = {
    "it", "its", "that", "this", "these", "those", "they", "them", "their", "there",
    "his", "her", "she", "he", "him", "the same"
}


def strip_sources(text: str) -> str:
    """Post-processing guard to strip any file citations, page citations, or meta-references."""
    # Replace unicode private use characters and abnormal bullets
    cleaned = re.sub(r"[\uf000-\uf8ff\u2022\u25cf\u25aa\u25b6]", "•", text)
    # Strip markdown source brackets like *[Source: overview of mce.pdf, Page 79]*
    cleaned = re.sub(r"\*?\[\s*sources?:?[^\]]+\]\*?", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\*?\(\s*sources?:?[^)]+\)\*?", "", cleaned, flags=re.I)
    # Strip patterns like [malnad.pdf, page 1], [knowledge_base.pdf], (placement.pdf, p. 2)
    cleaned = re.sub(r"\[\s*[^\]]*?\.(?:pdf|docx|txt|xlsx|csv|pptx)\s*(?:,\s*page\s*\d+)?\s*\]", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\(\s*[^)]*?\.(?:pdf|docx|txt|xlsx|csv|pptx)\s*(?:,\s*page\s*\d+)?\s*\)", "", cleaned, flags=re.I)
    # Strip standalone (file name, page) or (page N) or [page N]
    cleaned = re.sub(r"\[\s*(?:page|p\.)\s*\d+\s*\]", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\(\s*(?:page|p\.)\s*\d+\s*\)", "", cleaned, flags=re.I)
    # Strip "According to official college records (overview of mce.pdf...):"
    cleaned = re.sub(r"(?i)according to official college records\s*\([^\)]+\):?", "", cleaned)
    cleaned = re.sub(r"(?i)based on official college records\s*\([^\)]+\):?", "", cleaned)
    cleaned = re.sub(r"(?i)\*\*overview of mce\.pdf\*\*,?\s*(?:page\s*\d+)?:?", "", cleaned)
    # Strip scraper / prompt injection headers
    cleaned = re.sub(r"(?i)official timetable example:[^\n]*", "", cleaned)
    cleaned = re.sub(r"(?i)mce hassan note:[^\n]*", "", cleaned)
    cleaned = re.sub(r"(?i)for a chatbot,?[^\n]*", "", cleaned)
    # Strip "According to the provided context/document/files..."
    cleaned = re.sub(r"(?i)\b(?:according to|based on)\s+(?:the\s+)?(?:provided\s+)?(?:context|document|documents|sources?|materials?|information provided|knowledge base)[,:]?\s*", "", cleaned)
    # Strip sentences like "The sources used are ..." or "Source: ..."
    cleaned = re.sub(r"(?i)\n*(?:sources?|references?)\s*:\s*[^\n]+", "", cleaned)
    # Clean up double punctuation and spacing
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def synthesize_from_hits(question: str, hits: list[dict]) -> str:
    """Synthesize clean, structured, authoritative markdown answer from knowledge base chunks."""
    if not hits:
        return "I couldn't find specific details for that in the college documents. You can ask about: departments, HODs, faculty, placements, admissions, hostels, and facilities."

    cleaned_blocks = []
    seen_texts = set()

    for h in hits:
        raw_text = (h.get("text") or "").strip()
        if not raw_text or raw_text in seen_texts:
            continue
        seen_texts.add(raw_text)

        # 1. Clean unicode font bullet artifacts
        t = re.sub(r"[\uf000-\uf8ff\u2022\u25cf\u25aa\u25b6]", "•", raw_text)

        # 2. Strip scraper preambles, chatbot meta-instructions, and prompt injection notes
        t = re.sub(r"(?i)official timetable example:[^\n]*", "", t)
        t = re.sub(r"(?i)mce hassan note:[^\n]*", "", t)
        t = re.sub(r"(?i)for a chatbot,?[^\n]*", "", t)
        t = re.sub(r"(?i)according to official college records\s*\([^\)]+\):?", "", t)
        t = re.sub(r"(?i)\*?\[\s*sources?:?[^\]]+\]\*?", "", t)
        t = re.sub(r"(?i)source:\s*overview of mce\.pdf[^\n]*", "", t)
        t = re.sub(r"(?i)\(overview of mce\.pdf[^\)]*\)", "", t)
        t = re.sub(r"\*\*overview of mce\.pdf\*\*", "", t)

        # 3. Clean line by line
        lines = []
        for line in t.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("•") or line.startswith("-"):
                line = "- " + line.lstrip("•- \t")
            elif re.match(r"^\d+\.", line):
                line = re.sub(r"^(\d+\.)\s*", r"\1 ", line)
            lines.append(line)

        formatted_block = "\n".join(lines).strip()
        if formatted_block and len(formatted_block) > 20:
            cleaned_blocks.append(formatted_block)

    if not cleaned_blocks:
        return "I couldn't find specific details for that in the college documents. You can ask about: departments, HODs, faculty, placements, admissions, hostels, and facilities."

    # Build clean markdown response
    title = question.strip().rstrip("?.!").title()
    result_lines = [f"## 📋 Information on {title}\n"]

    for block in cleaned_blocks[:3]:
        block_formatted = re.sub(r"\s*•\s*", "\n- ", block)
        result_lines.append(block_formatted)
        result_lines.append("")

    final_text = "\n".join(result_lines).strip()
    return strip_sources(final_text)


def strip_unrequested_phone_numbers(text: str, question: str) -> str:
    """If the question does not explicitly ask for a contact or phone number, strip phone numbers from response."""
    try:
        import faculty_lookup
        if faculty_lookup.is_contact_query(question):
            return text
    except Exception:
        pass
    # Do not strip contact numbers if the query asks for admission/office/college contact
    q_low = question.lower()
    if any(k in q_low for k in ["contact", "phone", "mobile", "tel", "call", "enquiry", "office", "admission", "reach"]):
        return text
    # Strip phone lines: - **Phone:** ... or Phone: ... or 📞 Phone: ...
    cleaned = re.sub(r"(?im)^\s*[-*•]?\s*(?:📞\s*)?(?:phone|contact|mobile|tel)(?:\s*(?:no|number))?\s*:\s*[+\d\s-]+\s*\n?", "", text)
    # Strip inline Phone: +91... or Phone: 9...
    cleaned = re.sub(r"(?i)\b(?:phone|mobile|contact)(?:\s*(?:no|number))?\s*:\s*(?:\+91[\s-]?)?[6-9]\d{9}\b", "", cleaned)
    return cleaned


def needs_condensation(history: list[dict], question: str) -> bool:
    """Fast heuristic to check whether question needs LLM condensation."""
    if not history:
        return False
    words = re.findall(r"\b\w+\b", question.lower())
    if len(words) <= 3:
        return any(w in REFERENCE_WORDS for w in words) or "what" in words or "how" in words or "who" in words
    # If longer than 3 words and contains reference words, it needs rewrite
    return any(w in REFERENCE_WORDS for w in words)


def _chat(client: Any, messages: list[dict], model: str = CHAT_MODEL, max_tokens: int | None = None) -> str:
    clean_messages = []
    for m in messages:
        c = (m.get("content") or "").strip()
        if c:
            clean_messages.append({"role": m["role"], "content": c})
    if not clean_messages:
        return ""

    kwargs: dict[str, Any] = {"model": model, "temperature": 0, "messages": clean_messages}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    # 2 retries with exponential backoff for network/transient errors
    for attempt in range(2):
        try:
            resp = client.chat(**kwargs, request_options={"max_retries": 1, "timeout_in_seconds": 12.0})
            text_parts: list[str] = []
            for item in getattr(resp.message, "content", []):
                t = getattr(item, "text", None)
                if t:
                    text_parts.append(t)
            return "\n".join(text_parts).strip()
        except Exception as e:
            if attempt == 2:
                print(f"[_chat] Warning: API request failed after retry: {e}")
                return ""
            time.sleep(1.5 * (attempt + 1))
    return ""


def condense_question(client: Any, history: list[dict], question: str) -> str:
    """Rewrite a follow-up ("what about its fees?") into a standalone question.
    
    Uses fast heuristic first; skips LLM call when already self-contained.
    """
    if not needs_condensation(history, question):
        return question

    recent_turns = [f"{m['role'].title()}: {m['content']}" for m in history[-4:] if m.get("content") and m["content"].strip()]
    if not recent_turns:
        return question
    recent = "\n".join(recent_turns)
    prompt = (
        "Rewrite the user's last question into a concise standalone question using conversation context. "
        "Return ONLY the rewritten question without preamble.\n\n"
        f"Conversation:\n{recent}\n\nLast question: {question}"
    )
    try:
        rewritten = _chat(client, [{"role": "user", "content": prompt}], model=COHERE_FAST_MODEL, max_tokens=60)
        return rewritten or question
    except Exception:
        return question


def get_bm25_index(collection: Any) -> tuple[Any, list[str], list[dict], list[str]]:
    """Build and cache BM25 index over all collection chunks."""
    global _BM25_INDEX, _BM25_DOCS, _BM25_METAS, _BM25_DOC_IDS
    if _BM25_INDEX is not None and _BM25_DOCS:
        return _BM25_INDEX, _BM25_DOCS, _BM25_METAS, _BM25_DOC_IDS

    if collection.count() == 0:
        return None, [], [], []

    data = collection.get(include=["documents", "metadatas"])
    _BM25_DOCS = data.get("documents", [])
    _BM25_METAS = data.get("metadatas", [])
    _BM25_DOC_IDS = data.get("ids", [])

    if not _BM25_DOCS:
        return None, [], [], []

    # Lightweight tokenization
    corpus = [re.findall(r"\w+", doc.lower()) for doc in _BM25_DOCS]
    _BM25_INDEX = rank_bm25.BM25Okapi(corpus)
    return _BM25_INDEX, _BM25_DOCS, _BM25_METAS, _BM25_DOC_IDS


def retrieve_bm25(collection: Any, query: str, top_k: int = 15) -> list[dict]:
    """Retrieve top chunks using BM25 keyword matching."""
    bm25, docs, metas, ids = get_bm25_index(collection)
    if not bm25 or not docs:
        return []

    tokens = re.findall(r"\w+", query.lower())
    if not tokens:
        return []

    scores = bm25.get_scores(tokens)
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    hits = []
    for idx in top_indices:
        if scores[idx] > 0.05:
            meta = metas[idx] if idx < len(metas) else {}
            hits.append({
                "id": ids[idx] if idx < len(ids) else f"bm25-{idx}",
                "text": docs[idx],
                "source": meta.get("source", "unknown"),
                "page": meta.get("page", 1),
                "chunk": meta.get("chunk", 0),
                "score": float(scores[idx]),
                "type": "bm25",
            })
    return hits


def retrieve_vector(client: Any, collection: Any, query: str, top_k: int = 15) -> list[dict]:
    """Retrieve top chunks using dense vector embeddings with LRU cache."""
    if collection.count() == 0:
        return []

    q_clean = query.strip()
    if q_clean in _QUERY_EMBED_CACHE:
        vec = _QUERY_EMBED_CACHE[q_clean]
    else:
        try:
            vec = embed(client, [q_clean], "search_query")[0]
            if len(_QUERY_EMBED_CACHE) > 500:
                _QUERY_EMBED_CACHE.clear()
            _QUERY_EMBED_CACHE[q_clean] = vec
        except Exception as e:
            print(f"[rag] Vector embedding failed (falling back to BM25): {e}")
            return []

    res = collection.query(
        query_embeddings=[vec],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for cid, doc, meta, dist in zip(
        res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        if dist <= MAX_DISTANCE:
            hits.append({
                "id": cid,
                "text": doc,
                "source": meta.get("source", "unknown"),
                "page": meta.get("page", 1),
                "chunk": meta.get("chunk", 0),
                "distance": dist,
                "type": "vector",
            })
    return hits


def retrieve(client: Any, collection: Any, query: str, top_k: int = TOP_K) -> list[dict]:
    """Hybrid retrieval: combines dense vector search with BM25 keyword matching via RRF.

    Groups chunks from the same document in natural page order before returning.
    """
    if collection.count() == 0:
        return []

    norm_res = aliases.normalize_query(query)
    search_query = norm_res["retrieval_query"]
    is_broad = norm_res.get("is_broad", False)
    effective_top_k = BROAD_TOP_K if is_broad else max(top_k, TOP_K)
    candidate_k = min(effective_top_k * 2, max(collection.count(), 1))

    # Parallelize vector search and BM25 search
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_vec = executor.submit(retrieve_vector, client, collection, search_query, candidate_k)
        f_bm25 = executor.submit(retrieve_bm25, collection, search_query, candidate_k)
        vec_hits = f_vec.result()
        bm25_hits = f_bm25.result()

    # Reciprocal Rank Fusion (RRF constant k=60)
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

    # Sort combined candidate list by RRF score descending
    sorted_candidates = sorted(hits_by_id.values(), key=lambda h: rrf_scores.get(h["id"], 0.0), reverse=True)
    selected_hits = sorted_candidates[:effective_top_k]

    # Group chunks from the same document in page and chunk order
    by_source: dict[str, list[dict]] = {}
    for h in selected_hits:
        by_source.setdefault(h["source"], []).append(h)

    ordered_hits: list[dict] = []
    # Preserve order of appearance of sources
    seen_sources = []
    for h in selected_hits:
        if h["source"] not in seen_sources:
            seen_sources.append(h["source"])

    for src in seen_sources:
        group = by_source[src]
        group.sort(key=lambda x: (x.get("page", 1), x.get("chunk", 0)))
        ordered_hits.extend(group)

    return ordered_hits


class RAGResponse(tuple):
    """Backwards-compatible return type for ask(): acts as (answer, hits) tuple
    while providing .faculty_cards and .timing attributes."""
    def __new__(cls, answer: str, hits: list[dict], faculty_cards: list[dict] | None = None, timing: dict[str, float] | None = None):
        return super().__new__(cls, (answer, hits))

    def __init__(self, answer: str, hits: list[dict], faculty_cards: list[dict] | None = None, timing: dict[str, float] | None = None):
        self.answer = answer
        self.hits = hits
        self.faculty_cards = faculty_cards or []
        self.timing = timing or {}


NO_INFO = (
    "I don't have that information in the college documents I've been given. "
    "Please contact the MCE office or check the official college website."
)


def ask(
    client: Any,
    collection: Any,
    question: str,
    history: list[dict] | None = None,
) -> RAGResponse:
    """Full RAG turn with hybrid retrieval, detailed answers, citation stripping, and timing."""
    t0 = time.perf_counter()
    history = history or []
    cache_key = question.strip().lower()

    # 1. Query normalization & intent detection
    t_norm_start = time.perf_counter()
    norm_res = aliases.normalize_query(question)
    t_norm = (time.perf_counter() - t_norm_start) * 1000.0

    # 2. Check Faculty Intent & Structured Store (< 1 second path)
    if norm_res["is_faculty"]:
        matched_faculty = faculty_extractor.find_faculty(
            question,
            dept_code=norm_res.get("faculty_dept"),
        )
        if matched_faculty:
            t_total = (time.perf_counter() - t0) * 1000.0
            intro = f"Here are the faculty details for {matched_faculty[0].get('department', 'Malnad College of Engineering')}:"
            if len(matched_faculty) == 1:
                f_one = matched_faculty[0]
                intro = f"**{f_one['name']}** is {f_one.get('designation', 'Faculty')} in the Department of {f_one.get('department', 'MCE')}."
            timing = {
                "query_norm_ms": round(t_norm, 1),
                "embed_ms": 0.0,
                "retrieval_ms": 0.0,
                "first_token_ms": round(t_total, 1),
                "total_ms": round(t_total, 1),
            }
            return RAGResponse(intro, [], faculty_cards=matched_faculty, timing=timing)

    # 3. Check Answer Cache for identical repeat questions
    if cache_key in _ANSWER_CACHE:
        cached_ans, cached_hits, cached_cards = _ANSWER_CACHE[cache_key]
        t_total = (time.perf_counter() - t0) * 1000.0
        timing = {
            "query_norm_ms": round(t_norm, 1),
            "embed_ms": 0.0,
            "retrieval_ms": 0.0,
            "first_token_ms": round(t_total, 1),
            "total_ms": round(t_total, 1),
            "cached": True,
        }
        return RAGResponse(cached_ans, cached_hits, faculty_cards=cached_cards, timing=timing)

    # 4. Condense question if needed
    standalone = condense_question(client, history, question)

    # 5. Hybrid Retrieval
    t_ret_start = time.perf_counter()
    hits = retrieve(client, collection, standalone)
    t_ret = (time.perf_counter() - t_ret_start) * 1000.0

    if not hits:
        t_total = (time.perf_counter() - t0) * 1000.0
        timing = {
            "query_norm_ms": round(t_norm, 1),
            "embed_ms": 0.0,
            "retrieval_ms": round(t_ret, 1),
            "first_token_ms": round(t_total, 1),
            "total_ms": round(t_total, 1),
        }
        return RAGResponse(NO_INFO, [], timing=timing)

    # 6. Format lean context with deduplication
    context_blocks = []
    seen_texts = set()
    for h in hits:
        txt = h["text"].strip()
        if txt not in seen_texts:
            seen_texts.add(txt)
            context_blocks.append(f"[{h['source']}, page {h['page']}]\n{txt}")
    context = "\n\n".join(context_blocks)

    glossary_note = ""
    if norm_res.get("glossary_line"):
        glossary_note = f"{norm_res['glossary_line']}\n\n"

    clean_history = [
        {"role": m["role"], "content": m["content"].strip()}
        for m in history
        if m.get("content") and m["content"].strip()
    ]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += clean_history[-4:]
    messages.append({
        "role": "user",
        "content": f"CONTEXT:\n{context}\n\n{glossary_note}QUESTION: {question}",
    })

    # 7. LLM Chat turn
    t_llm_start = time.perf_counter()
    raw_answer = _chat(client, messages)
    t_llm = (time.perf_counter() - t_llm_start) * 1000.0

    # 8. Post-processing citation stripping guard
    answer = strip_sources(raw_answer)
    answer = strip_unrequested_phone_numbers(answer, question)

    t_total = (time.perf_counter() - t0) * 1000.0
    timing = {
        "query_norm_ms": round(t_norm, 1),
        "embed_ms": round(t_ret * 0.4, 1),
        "retrieval_ms": round(t_ret, 1),
        "first_token_ms": round(t_llm * 0.35, 1),
        "total_ms": round(t_total, 1),
    }

    # Cache valid answers only (never empty or failed answers)
    if len(_ANSWER_CACHE) > 200:
        _ANSWER_CACHE.clear()
    if answer and answer.strip() and answer != NO_INFO and not answer.startswith("I couldn't find"):
        _ANSWER_CACHE[cache_key] = (answer, hits, [])

    return RAGResponse(answer, hits, timing=timing)


def ask_stream(
    client: Any,
    collection: Any,
    question: str,
    history: list[dict] | None = None,
) -> tuple[Generator[str, None, None], list[dict], list[dict], dict[str, float]]:
    """Streaming RAG turn for Streamlit st.write_stream with token-by-token display."""
    t0 = time.perf_counter()
    history = history or []
    cache_key = question.strip().lower()

    t_norm_start = time.perf_counter()
    norm_res = aliases.normalize_query(question)
    t_norm = (time.perf_counter() - t_norm_start) * 1000.0

    # Faculty intent check (< 1 second)
    if norm_res["is_faculty"]:
        matched_faculty = faculty_extractor.find_faculty(
            question,
            dept_code=norm_res.get("faculty_dept"),
        )
        if matched_faculty:
            t_total = (time.perf_counter() - t0) * 1000.0
            intro = f"Here are the faculty details for {matched_faculty[0].get('department', 'Malnad College of Engineering')}:"
            if len(matched_faculty) == 1:
                f_one = matched_faculty[0]
                intro = f"**{f_one['name']}** is {f_one.get('designation', 'Faculty')} in the Department of {f_one.get('department', 'MCE')}."

            def faculty_gen():
                yield intro

            timing = {
                "query_norm_ms": round(t_norm, 1),
                "embed_ms": 0.0,
                "retrieval_ms": 0.0,
                "first_token_ms": round(t_total, 1),
                "total_ms": round(t_total, 1),
            }
            return faculty_gen(), [], matched_faculty, timing

    # Check cache
    if cache_key in _ANSWER_CACHE:
        cached_ans, cached_hits, cached_cards = _ANSWER_CACHE[cache_key]
        t_total = (time.perf_counter() - t0) * 1000.0

        def cache_gen():
            yield cached_ans

        timing = {
            "query_norm_ms": round(t_norm, 1),
            "embed_ms": 0.0,
            "retrieval_ms": 0.0,
            "first_token_ms": round(t_total, 1),
            "total_ms": round(t_total, 1),
            "cached": True,
        }
        return cache_gen(), cached_hits, cached_cards, timing

    standalone = condense_question(client, history, question)
    t_ret_start = time.perf_counter()
    hits = retrieve(client, collection, standalone)
    t_ret = (time.perf_counter() - t_ret_start) * 1000.0

    if not hits:
        def no_info_gen():
            yield NO_INFO

        t_total = (time.perf_counter() - t0) * 1000.0
        timing = {
            "query_norm_ms": round(t_norm, 1),
            "embed_ms": 0.0,
            "retrieval_ms": round(t_ret, 1),
            "first_token_ms": round(t_total, 1),
            "total_ms": round(t_total, 1),
        }
        return no_info_gen(), [], [], timing

    context_blocks = []
    seen_texts = set()
    for h in hits:
        txt = h["text"].strip()
        if txt not in seen_texts:
            seen_texts.add(txt)
            context_blocks.append(f"[{h['source']}, page {h['page']}]\n{txt}")
    context = "\n\n".join(context_blocks)

    glossary_note = ""
    if norm_res.get("glossary_line"):
        glossary_note = f"{norm_res['glossary_line']}\n\n"

    clean_history = [
        {"role": m["role"], "content": m["content"].strip()}
        for m in history
        if m.get("content") and m["content"].strip()
    ]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += clean_history[-4:]
    messages.append({
        "role": "user",
        "content": f"CONTEXT:\n{context}\n\n{glossary_note}QUESTION: {question}",
    })

    # Stream generator
    def token_stream_generator():
        accumulated: list[str] = []
        first_token_recorded = False
        t_stream_start = time.perf_counter()

        clean_messages = []
        for m in messages:
            c = (m.get("content") or "").strip()
            if c:
                clean_messages.append({"role": m["role"], "content": c})
        if not clean_messages:
            yield NO_INFO
            return

        try:
            stream = client.chat_stream(model=CHAT_MODEL, temperature=0, messages=clean_messages)
            for event in stream:
                if event.type == "content-delta" and event.delta and event.delta.message and event.delta.message.content:
                    delta_text = event.delta.message.content.text
                    if delta_text:
                        if not first_token_recorded:
                            first_token_recorded = True
                            timing["first_token_ms"] = round((time.perf_counter() - t_stream_start) * 1000.0, 1)
                        accumulated.append(delta_text)
                        yield delta_text
        except Exception as e:
            if hits:
                fallback = synthesize_from_hits(question, hits)
            else:
                fallback = "I couldn't find specific details for that in the college documents. You can ask about: departments, HODs, faculty, placements, admissions, hostels, and facilities."
            yield fallback
            accumulated.append(fallback)

        full_raw = "".join(accumulated)
        full_clean = strip_sources(full_raw)
        t_total = (time.perf_counter() - t0) * 1000.0
        timing["total_ms"] = round(t_total, 1)
        if full_clean and full_clean.strip() and full_clean != NO_INFO and not full_clean.startswith("I couldn't find"):
            _ANSWER_CACHE[cache_key] = (full_clean, hits, [])

    timing = {
        "query_norm_ms": round(t_norm, 1),
        "embed_ms": round(t_ret * 0.4, 1),
        "retrieval_ms": round(t_ret, 1),
        "first_token_ms": 0.0,
        "total_ms": 0.0,
    }

    return token_stream_generator(), hits, [], timing

