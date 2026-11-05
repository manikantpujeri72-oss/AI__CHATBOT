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

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "documents"
DB_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "mce_docs"

CHAT_MODEL = os.getenv("COHERE_CHAT_MODEL", "command-a-plus-05-2026")
EMBED_MODEL = os.getenv("COHERE_EMBED_MODEL", "embed-v4.0")

CHUNK_WORDS = 220      # words per chunk
CHUNK_OVERLAP = 40     # words shared between neighbouring chunks
TOP_K = int(os.getenv("TOP_K", "5"))
MAX_DISTANCE = float(os.getenv("MAX_DISTANCE", "0.8"))  # cosine distance cut-off

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
1. Answer ONLY from the CONTEXT given with the question. Never use outside knowledge.
2. If the context does not contain the answer, say: "I don't have that information in the college documents I've been given." Then suggest contacting the MCE office or checking the official college website. Do not guess.
3. Never invent numbers, dates, fees, names, cut-offs or company names. Quote figures exactly as they appear in the context.
4. Be clear, friendly and concise. Use short bullet points for lists.
5. Reply in the same language the user wrote in.
6. At the end of the answer, mention the sources you used in the form (file name, page)."""


# --------------------------------------------------------------------------- #
# Clients & Collection helpers
# --------------------------------------------------------------------------- #
def get_cohere_client() -> Any:
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        raise RuntimeError("COHERE_API_KEY is missing. Add it to the .env file.")
    return cohere.ClientV2(api_key=api_key)


def get_collection(db_path: Path | str = DB_DIR, collection_name: str = COLLECTION_NAME) -> Any:
    client = chromadb.PersistentClient(path=str(db_path))
    return client.get_or_create_collection(
        name=collection_name, metadata={"hnsw:space": "cosine"}
    )


def reset_collection(db_path: Path | str = DB_DIR, collection_name: str = COLLECTION_NAME) -> None:
    client = chromadb.PersistentClient(path=str(db_path))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass


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
def embed(client: Any, texts: list[str], input_type: str, max_retries: int = 5) -> list[list[float]]:
    """Embed texts using Cohere in batches of 96 with exponential backoff on errors."""
    vectors: list[list[float]] = []
    for i in range(0, len(texts), 96):
        batch = texts[i : i + 96]
        last_exc: Exception | None = None
        for attempt in range(max_retries):
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
def _chat(client: Any, messages: list[dict]) -> str:
    resp = client.chat(model=CHAT_MODEL, temperature=0, messages=messages)
    text_parts: list[str] = []
    for item in resp.message.content:
        if hasattr(item, "text") and item.text:
            text_parts.append(item.text)
    return "\n".join(text_parts).strip()


def condense_question(client: Any, history: list[dict], question: str) -> str:
    """Rewrite a follow-up ("what about its fees?") into a standalone question."""
    if not history:
        return question
    recent = "\n".join(f"{m['role'].title()}: {m['content']}" for m in history[-6:])
    prompt = (
        "Rewrite the user's last question so it is fully self-contained, using the "
        "conversation for context. Return ONLY the rewritten question.\n\n"
        f"Conversation:\n{recent}\n\nLast question: {question}"
    )
    try:
        return _chat(client, [{"role": "user", "content": prompt}]) or question
    except Exception:
        return question


def retrieve(client: Any, collection: Any, query: str, top_k: int = TOP_K) -> list[dict]:
    if collection.count() == 0:
        return []
    vec = embed(client, [query], "search_query")[0]
    res = collection.query(
        query_embeddings=[vec],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        if dist <= MAX_DISTANCE:
            hits.append(
                {
                    "text": doc,
                    "source": meta["source"],
                    "page": meta.get("page", 1),
                    "distance": dist,
                }
            )
    return hits


NO_INFO = (
    "I don't have that information in the college documents I've been given. "
    "Please contact the MCE office or check the official college website."
)


def ask(client: Any, collection: Any, question: str, history: list[dict]) -> tuple[str, list[dict]]:
    """Full RAG turn. Returns (answer, source_chunks)."""
    standalone = condense_question(client, history, question)
    hits = retrieve(client, collection, standalone)
    if not hits:
        return NO_INFO, []

    context = "\n\n".join(
        f"[{h['source']}, page {h['page']}]\n{h['text']}" for h in hits
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
    messages.append(
        {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"}
    )
    return _chat(client, messages), hits
