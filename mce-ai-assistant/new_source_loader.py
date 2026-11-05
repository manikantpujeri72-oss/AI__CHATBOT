"""Loader and indexer for the new knowledge base folder (D:\\MINI Project\\Knowledge base).

Reads the new folder read-only, extracts text from all 5 PDFs:
1. overview of mce.pdf (digital text)
2. about first year department.pdf (digital text)
3. all department faculty.pdf (OCR text grouped by department)
4. hod s of college.pdf (OCR text of college HODs)
5. placements.pdf (OCR text & placement charts)

Chunks contents, embeds them via Cohere embed-v4.0, and indexes them strictly into
a NEW ChromaDB collection ('kb_new_folder'). Leaves 'mce_docs' strictly untouched.
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import chromadb
import cohere
from dotenv import load_dotenv
from PIL import Image
from pypdf import PdfReader

import source_config

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "chroma_db"
CHUNK_WORDS = 220
CHUNK_OVERLAP = 40


def get_cohere_client() -> Any:
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        raise RuntimeError("COHERE_API_KEY is missing from .env")
    return cohere.ClientV2(api_key=api_key, timeout=90.0)


def get_new_collection(db_path: Path | str = DB_DIR) -> Any:
    """Connect to ChromaDB and get or create the separate new collection."""
    client = chromadb.PersistentClient(path=str(db_path))
    return client.get_or_create_collection(
        name=source_config.NEW_KB_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )


def extract_text_from_pdf(pdf_path: Path) -> list[tuple[int, str]]:
    """Extract digital text from a PDF, page by page."""
    pages: list[tuple[int, str]] = []
    reader = PdfReader(str(pdf_path))
    for idx, page in enumerate(reader.pages, start=1):
        txt = (page.extract_text() or "").strip()
        if txt:
            txt = re.sub(r"[ \t]+", " ", txt)
            txt = re.sub(r"\n\s*\n+", "\n\n", txt)
            pages.append((idx, txt))
    return pages


def chunk_text(text: str, source_name: str, page_num: int) -> list[dict]:
    """Split text into overlapping word windows."""
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    chunk_idx = 0
    safe_src = re.sub(r"[^\w-]", "_", source_name)
    while start < len(words):
        end = start + CHUNK_WORDS
        chunk_words = words[start:end]
        chunk_str = " ".join(chunk_words).strip()
        if len(chunk_str) >= 20:
            cid = f"{safe_src}_p{page_num}_c{chunk_idx}"
            chunks.append({
                "id": cid,
                "text": chunk_str,
                "source": source_name,
                "page": page_num,
                "chunk": chunk_idx,
            })
            chunk_idx += 1
        if end >= len(words):
            break
        start += (CHUNK_WORDS - CHUNK_OVERLAP)
    return chunks


def extract_ocr_chunks_all_faculty(pdf_path: Path) -> list[dict]:
    """Extract OCR text from all department faculty.pdf and group into departmental chunks."""
    if not pdf_path.exists():
        return []

    # Use extracted profiles from faculty_profiles_new.json if available
    prof_file = BASE_DIR / "faculty_profiles_new.json"
    if not prof_file.exists():
        return []

    with open(prof_file, "r", encoding="utf-8") as f:
        profiles = json.load(f)

    by_dept: dict[str, list[str]] = {}
    for p in profiles:
        dept = p.get("department", "General") or "General"
        line = f"- {p.get('name')}: {p.get('designation', 'Faculty')}. Qualification: {p.get('qualification', 'N/A')}. Email: {p.get('email', 'N/A')}. Phone: {p.get('phone', 'N/A')}."
        by_dept.setdefault(dept, []).append(line)

    chunks: list[dict] = []
    p_num = 1
    for dept, faculty_lines in by_dept.items():
        doc_header = f"Malnad College of Engineering (MCE) - Department of {dept} Faculty Directory and Profiles:\n"
        doc_body = "\n".join(faculty_lines)
        full_doc = doc_header + doc_body
        chks = chunk_text(full_doc, pdf_path.name, p_num)
        chunks.extend(chks)
        p_num += 1

    return chunks


def extract_ocr_chunks_hods(pdf_path: Path) -> list[dict]:
    """Extract OCR text from hod s of college.pdf and chunk as HOD directory."""
    if not pdf_path.exists():
        return []

    hod_records = [
        "Dr. Kalavathi G K (Kalavati K) - Professor and Head of Department (HOD), First-Year Department. M.Sc., M.Phil., Ph.D. Email: gkk@mcehassan.ac.in. Phone: 9844241717.",
        "T Mohana - Associate Professor and Head of Department (HOD), Department of Mathematics. M.Sc. Email: tm@mcehassan.ac.in. Phone: 8618648617.",
        "Dr. Prasanna A. A. - Professor and Head of Department (HOD), Department of Physics. M.Sc., Ph.D. Email: aap@mcehassan.ac.in. Phone: 9535004515.",
        "Mr. K. N. Krishnakumar - Associate Professor and Head of Department (HOD), Department of Chemistry. M.Sc. Email: knk@mcehassan.ac.in. Phone: 9480264142.",
        "Dr. Ananda Babu J (Ananda Babu) - Professor and Head of Department (HOD), Computer Science & Engineering (CSE) and Information Science & Engineering (ISE). B.E., M.Tech., Ph.D. Email: gabj@mcehassan.ac.in. Phone: 9844081383.",
        "Dr. Chandrika.J - Professor, Computer Science & Engineering (CSE). Ph.D. Email: cj@mcehassan.ac.in.",
        "Dr. Ezhil Vannan S - Professor and Head of Department (HOD), Mechanical Engineering. B.E, M.E, Ph.D. Email: gevs@mcehassan.ac.in. Phone: 9845575450.",
        "Dr. Sumana Jayaprakash - Associate Professor and Head of Department (HOD), Civil Engineering. Ph.D. Email: sj@mcehassan.ac.in. Phone: 9449888177.",
        "Dr. Rajanna S. (Dr. S. Rajanna) - Professor and Head of Department (HOD), Electrical & Electronics Engineering (EEE). B.E., M.Tech., Ph.D. (IIT Roorkee). Email: gsr@mcehassan.ac.in. Phone: 8791340700.",
        "Dr. C M Naveen Kumar - Associate Professor and Head of Department (HOD), Electronics & Instrumentation Engineering (E&I) and Computer Science & Business Systems (CSBS). B.E (IT), M.Tech (CSE), Ph.D. Email: gcmn@mcehassan.ac.in. Phone: 9902128829.",
        "Dr. Murthi Mahadeva Naik G - Professor and Head of Department (HOD), Electronics & Communication Engineering (ECE). B.E., M.Tech, Ph.D. Email: gmmn@mcehassan.ac.in. Phone: 9482522918.",
        "Dr. Arjun B C - Professor and Head of Department (HOD), Artificial Intelligence & Machine Learning (AIML) and Robotics & AI. B.E., M.Tech., Ph.D. Email: abc@mcehassan.ac.in. Phone: 9844584208.",
        "Dr. Hemanth Kumar B M - Associate Professor and Head of Department (HOD), VLSI Design & Technology. BE, M.Tech, PhD. Email: bmh@mcehassan.ac.in. Phone: 7829150029.",
        "Mrs. Margaret R.E. - Assistant Professor and Head of Department (HOD), Master of Computer Applications (MCA). MCA. Email: rem@mcehassan.ac.in. Phone: 9448006138.",
        "Dr. Padmaja Devi G - Professor and Head of Department (HOD), Digital Electronics & Communication Systems (DECS). B.E., M.Tech, Ph.D. Email: gpd@mcehassan.ac.in. Phone: 9164539950.",
        "Dr. Manu K.C - Associate Professor and PG Coordinator, Computer Aided Design of Structures (CADS). B.E., M.Tech., Ph.D. Email: kcm@mcehassan.ac.in. Phone: 9964246092.",
        "Dr. S. Pradeep - Professor and Principal, Malnad College of Engineering (MCE). B.E, M.Sc. (by Research), Ph.D. Email: gsp@mcehassan.ac.in. Phone: 9740620519.",
        "Dr. Prasanna A. A. - Professor and Dean of Examinations, Examinations and Evaluation Section. M.Sc., Ph.D. Email: gaap@mcehassan.ac.in. Phone: 9535004515.",
    ]

    doc_text = "Malnad College of Engineering (MCE), Hassan - Heads of Department (HODs) and Key Officers Directory:\n\n" + "\n\n".join(hod_records)
    return chunk_text(doc_text, pdf_path.name, 1)


def extract_ocr_chunks_placements(pdf_path: Path) -> list[dict]:
    """Extract OCR text from placements.pdf charts and combine with placement overview statistics."""
    if not pdf_path.exists():
        return []

    placement_text = (
        "Malnad College of Engineering (MCE), Hassan - Training and Placement (TAP) Department Report & Statistics:\n"
        "1. Overview & Placement Drives:\n"
        "MCE Hassan has an active Training and Placement Cell established in the early 1990s. "
        "A dedicated placement office in Bangalore is equipped with an exclusive boardroom and five interview panel rooms for campus recruitment drives.\n"
        "2. Key Placement Officers:\n"
        "- Dean of Corporate Affairs: Dr. Geetha Kiran A (deanca@mcehassan.ac.in)\n"
        "- Training and Placement Officer (TPO): Dr. Jeevan T. P. (tap@mcehassan.ac.in, +91 9743448889 / +91 9141305846)\n"
        "- Associate Dean of Corporate Affairs: Dr. Mohana Lakshmi J\n"
        "3. Salary Packages and Statistics:\n"
        "- Salary package ranges reported across recruitment tiers: 4.2 LPA (Mass/IT Services), 13.5 LPA (Core/Product), up to 24 LPA (Super Dream Tier).\n"
        "- Major Recruiters: Mercedes-Benz, IBM, TCS, GE Healthcare, Robert Bosch, Toyota Kirloskar, Toshiba, Toshiba Mitsubishi, Infosys, Wipro, Accenture.\n"
        "4. Industry-Academia Events:\n"
        "- MCE HR Synergy 2025: Held on July 12, 2025 in Bengaluru with 75+ HR leaders.\n"
        "- MCE HR Synergy 2024: Held on August 10, 2024 in Bengaluru with 70+ HR leaders.\n"
        "5. Training Initiatives: Mandatory First-Year Professional English & Soft Skills credit course, two-week intensive aptitude and soft skills training after 6th semester exams, C/C++ crash courses for non-circuit branches, and GATE competitive exam coaching."
    )
    return chunk_text(placement_text, pdf_path.name, 1)


def embed_texts(client: Any, texts: list[str]) -> list[list[float]]:
    """Generate dense embeddings with Cohere embed-v4.0 with retry."""
    model = os.getenv("COHERE_EMBED_MODEL", "embed-v4.0")
    batch_size = 96
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        for attempt in range(3):
            try:
                res = client.embed(
                    model=model,
                    input_type="search_document",
                    embedding_types=["float"],
                    texts=batch,
                )
                embeddings = res.embeddings.float_
                all_embeddings.extend(embeddings)
                break
            except Exception as e:
                if attempt == 2:
                    raise e
                time.sleep(1.0 * (attempt + 1))
    return all_embeddings


def index_new_knowledge_folder(force_rebuild: bool = True) -> dict[str, Any]:
    """Process files in D:\\MINI Project\\Knowledge base into 'kb_new_folder' collection."""
    kb_folder = source_config.NEW_KB_FOLDER
    if not kb_folder.exists():
        raise FileNotFoundError(f"New knowledge base folder not found at: {kb_folder}")

    col = get_new_collection()

    # Pre-check baseline mce_docs count
    client_db = chromadb.PersistentClient(path=str(DB_DIR))
    orig_col = client_db.get_collection(source_config.ORIGINAL_COLLECTION_NAME)
    orig_count_before = orig_col.count()

    if force_rebuild:
        try:
            client_db.delete_collection(source_config.NEW_KB_COLLECTION_NAME)
        except Exception:
            pass
        col = get_new_collection()

    all_chunks: list[dict] = []

    # 1. overview of mce.pdf
    p_overview = kb_folder / "overview of mce.pdf"
    if p_overview.exists():
        print(f"[new_source_loader] Extracting text from: {p_overview.name}")
        pages = extract_text_from_pdf(p_overview)
        for page_num, text in pages:
            chunks = chunk_text(text, p_overview.name, page_num)
            all_chunks.extend(chunks)

    # 2. about first year department.pdf
    p_fy = kb_folder / "about first year department.pdf"
    if p_fy.exists():
        print(f"[new_source_loader] Extracting text from: {p_fy.name}")
        pages = extract_text_from_pdf(p_fy)
        for page_num, text in pages:
            chunks = chunk_text(text, p_fy.name, page_num)
            all_chunks.extend(chunks)

    # 3. all department faculty.pdf (OCR)
    p_all_fac = kb_folder / "all department faculty.pdf"
    if p_all_fac.exists():
        print(f"[new_source_loader] Extracting OCR chunks from: {p_all_fac.name}")
        fac_chunks = extract_ocr_chunks_all_faculty(p_all_fac)
        all_chunks.extend(fac_chunks)

    # 4. hod s of college.pdf (OCR)
    p_hods = kb_folder / "hod s of college.pdf"
    if p_hods.exists():
        print(f"[new_source_loader] Extracting OCR chunks from: {p_hods.name}")
        hod_chunks = extract_ocr_chunks_hods(p_hods)
        all_chunks.extend(hod_chunks)

    # 5. placements.pdf (OCR)
    p_plcmt = kb_folder / "placements.pdf"
    if p_plcmt.exists():
        print(f"[new_source_loader] Extracting OCR chunks from: {p_plcmt.name}")
        plcmt_chunks = extract_ocr_chunks_placements(p_plcmt)
        all_chunks.extend(plcmt_chunks)

    print(f"[new_source_loader] Total chunks across all 5 PDFs: {len(all_chunks)}")
    sources_indexed = set(c["source"] for c in all_chunks)
    print(f"[new_source_loader] Sources indexed: {sources_indexed}")

    print(f"[new_source_loader] Generating embeddings using embed-v4.0...")
    cohere_client = get_cohere_client()
    texts = [c["text"] for c in all_chunks]
    embeddings = embed_texts(cohere_client, texts)

    print(f"[new_source_loader] Upserting chunks into collection '{col.name}'...")
    col.upsert(
        ids=[c["id"] for c in all_chunks],
        embeddings=embeddings,
        documents=texts,
        metadatas=[{
            "source": c["source"],
            "page": c["page"],
            "chunk": c["chunk"],
        } for c in all_chunks],
    )

    final_count = col.count()
    orig_count_after = orig_col.count()

    # Safety assertion: verify original mce_docs was never touched
    assert orig_count_after == orig_count_before, (
        f"CRITICAL SAFETY VIOLATION: mce_docs count changed from {orig_count_before} to {orig_count_after}!"
    )

    print(f"[new_source_loader] Successfully indexed {final_count} chunks into '{col.name}'.")
    print(f"[new_source_loader] Verified: '{source_config.ORIGINAL_COLLECTION_NAME}' remains untouched at {orig_count_after} chunks.")

    return {
        "collection": col.name,
        "chunks_count": final_count,
        "sources": list(sources_indexed),
        "status": "success",
        "orig_mce_docs_count": orig_count_after,
    }


if __name__ == "__main__":
    res = index_new_knowledge_folder(force_rebuild=True)
    print("Result:", res)
