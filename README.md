# 🎓 MCE AI Assistant v2.0

An enterprise-grade, ultra-detailed RAG (Retrieval-Augmented Generation) assistant for **Malnad College of Engineering (MCE), Hassan, Karnataka**.

Designed for students, prospective parents, and visitors, the assistant provides exhaustive, beautifully structured answers with faculty portrait cards, instant alias expansion, token streaming, sub-second queries, and complete citation privacy.

**Stack:** Python · Streamlit · Cohere (`command-r-plus-08-2024` / `command-a-plus-05-2026` + `embed-v4.0`) · ChromaDB · BM25 (`rank_bm25`) · RapidFuzz · Pillow · Windows Media OCR

---

## ⚡ Key Upgrades & Architectural Features

### 1. Detailed & Structured Answers
- **Hybrid Retrieval:** Dense cosine semantic search (ChromaDB + Cohere `embed-v4.0`) combined in parallel with sparse lexical keyword matching (`BM25Okapi`), merged using **Reciprocal Rank Fusion (RRF)** (`score = 1 / (60 + rank)`).
- **Expanded Top-K:** Dynamic retrieval retrieving 8 chunks for specific questions and up to 14 chunks for broad overviews (e.g., "tell me about CSE", "explain admission").
- **Document Chunk Grouping:** Chunks from the same document are assembled in true logical page and chunk order so the LLM reads complete multi-page sections coherently.
- **Exhaustive Synthesis:** System prompts instruct the model to produce thorough answers with clear headings, bullet points, statistics, dates, and requirements without omitting facts or hallucinating.

### 2. Instant Short Forms, Synonyms & Typo Normalization
- **Centralized Dictionary (`aliases.json`):** Editable JSON mapping covering all MCE departments (`ISE`, `CSE`, `ECE`, `MECH`, `CIVIL`, `CSBS`, `AIDS`, `VLSI`), postgraduate programmes (`MCA`, `MTECH`), administrative designations (`HOD`, `Principal`, `Dean`), facilities (`hostel`, `canteen`, `sports`), regulatory bodies (`VTU`, `AICTE`, `NBA`, `NAAC`), and Kannada transliterations (`Malenadu`).
- **Word-Boundary Regex & Conservative Fuzzy Matching:** Detects abbreviations at word boundaries without false positives on English stopwords. Conservative fuzzy token matching handles common typos (e.g., `informaton science` -> `Information Science & Engineering`).
- **Glossary Injection & Broad Intent Handling:** Injects an LLM-friendly glossary note into context while displaying clean user text in the chat bubble. 1-2 word queries (e.g. `ise`) expand to comprehensive overview prompts.

### 3. Complete Source Privacy (Zero Leaks)
- **Citations Hidden by Default:** Assistant speaks naturally as an official college representative. System prompt explicitly forbids mentioning `.pdf`, page numbers, or phrases like "according to the document".
- **Deterministic Post-Processing Guard:** `rag.strip_sources()` strips any accidental citations, brackets (`[knowledge_base.pdf, page 12]`), or meta-preambles before reaching the user.
- **Clean UI:** All "Sources" expanders are removed from user chat.
- **Admin Debugging Toggle:** When `DEBUG_SOURCES=1` in `.env`, a dedicated debugging expander appears in the sidebar for administrator inspection only.

### 4. Rich Faculty Cards with Photos
- **Structured Faculty Store (`faculty.json`):** 157 extracted faculty and officer profiles indexed by department, designation rank, and name.
- **Deterministic OCR Pipeline:** Windows native OCR (`Windows.Media.Ocr`) automatically parses scanned department PDFs during ingest (`python ingest.py --faculty`), cropping 300px portrait photos to `assets/faculty/{id}.jpg`.
- **HOD & Designation Sorting:** Department queries automatically sort the Head of Department (HOD) first, followed by Professors, Associate Professors, and Assistant Professors.
- **Drop-In Photo Folder:** Drop any named JPEG/PNG into `documents/faculty_photos/` (e.g., `chandrika_j.jpg`) to override or supplement extracted photos without rebuilding.
- **Streamlit Card Layout:** Renders responsive cards (`st.columns([1, 3])`) with cropped portrait on the left and designation, department, email, and qualifications on the right. Persisted in chat history for zero-latency reruns.

### 5. High Performance & Low Latency
- **Sub-Second Fast-Path Routing:** Queries asking for faculty, HODs, principals, or staff hit the structured store directly, rendering full cards and bio intros in **~12 milliseconds** without waiting for vector search or LLM generation.
- **Token Streaming:** `rag.ask_stream()` yields tokens via Cohere's streaming API, displayed in real-time with `st.write_stream` (first token in < 500ms).
- **Two-Tier Model Routing:** Uses fast models (`command-r7b-12-2024` or `command-r-08-2024`) for condensation and primary models (`command-r-plus-08-2024`) for final synthesis.
- **Intelligent Condensation Skip:** Heuristic regex checks whether follow-up queries are already self-contained, skipping unnecessary rewrite calls.
- **Multi-Level In-Memory Caching:** LRU cache for query embeddings (`_QUERY_EMBED_CACHE`) and whole-answer caching (`_ANSWER_CACHE`) for instant repeat queries.

---

## 🚀 Quick Start (Windows)

```powershell
# 1. Activate virtual environment
.\myenv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
# Ensure .env has your COHERE_API_KEY
copy .env.example .env

# 4. Ingest knowledge base and extract faculty cards
python ingest.py --sync
python ingest.py --faculty

# 5. Launch Streamlit Web UI
streamlit run app.py
```

The application runs on `http://localhost:8501`.

---

## 🛠️ CLI Reference (`ingest.py`)

| Command | Description |
|---|---|
| `python ingest.py --sync` | Synchronise `documents/` with ChromaDB (indexes new/modified files, deletes removed ones). |
| `python ingest.py --faculty` | Run OCR pipeline on faculty PDFs, extract structured data to `faculty.json`, and crop photos to `assets/faculty/`. |
| `python ingest.py --dry-run` | Preview additions, updates, renames, and deletions without modifying ChromaDB. |
| `python ingest.py --list` | List all indexed documents with chunk count, page count, file hash, and last indexed time. |
| `python ingest.py --add <file> [--as <path>]` | Add or update a file in the knowledge base. |
| `python ingest.py --replace <old-file> <new-file>` | Replace an existing document with a new file atomically. |
| `python ingest.py --delete <source>` | Delete document chunks and move file to `_deleted/` archive. |
| `python ingest.py --reset` | Wipe ChromaDB and rebuild collection from scratch from `documents/`. |

---

## ⚙️ Configuration & Environment Variables (`.env`)

```ini
# Required
COHERE_API_KEY=your_cohere_api_key_here

# Optional model selection
COHERE_CHAT_MODEL=command-r-plus-08-2024
COHERE_FAST_MODEL=command-r-08-2024
COHERE_EMBED_MODEL=embed-v4.0

# Retrieval settings
TOP_K=8
BROAD_TOP_K=14
MAX_DISTANCE=0.85

# Admin & Debugging
ADMIN_PASSWORD=your_secret_admin_password
DEBUG_SOURCES=0
```

- **`ADMIN_PASSWORD`**: When set, hides document upload, replacement, deletion, and faculty rebuild buttons behind a password lock in the sidebar.
- **`DEBUG_SOURCES`**: Set to `1` to display an administrative debug expander showing retrieved chunks and hybrid scores. Defaults to `0` (hidden).

---

## 📝 Customization Guides

### 1. Editing Short Forms & Synonyms (`aliases.json`)
You can add or update short forms, typos, and Kannada transliterations anytime by editing `aliases.json`. Changes take effect instantly without restarting Streamlit.

```json
{
  "departments": {
    "AIML": {
      "canonical": "Artificial Intelligence & Machine Learning",
      "short_forms": ["aiml", "ai ml", "ai & ml"],
      "synonyms": ["Department of AIML", "Artificial Intelligence and Machine Learning"],
      "typos": ["aimel", "artifical intelligence"]
    }
  }
}
```

### 2. Adding Faculty Photos (`documents/faculty_photos/`)
To add a photo for any faculty member (such as the ISE department staff or newly joined faculty):
1. Save the photo as a JPEG or PNG (e.g. `chandrika_j.jpg` or `sheetal_d_n.png`).
2. Place the file inside `documents/faculty_photos/`.
3. In the Streamlit sidebar, click **"👥 Rebuild faculty data"** (or run `python ingest.py --faculty`).
The system automatically matches the filename to the faculty member and updates the card.

---

## 🧪 Comprehensive Verification Suite

Run the full end-to-end test suite covering all 5 core problems and sync regressions:

```powershell
python run_all_tests.py
```

### Test Results Breakdown:
- **Test 1: Aliases & Intent Normalization:** 11/11 Passed (100%)
- **Test 2: Detailed Structured Answers (10 real questions):** 10/10 Passed (100%)
- **Test 3: No Source Leakage & Clean UI:** 6/6 Passed (100%)
- **Test 4: Structured Faculty Store & Photo Cards:** 6/6 Passed (100%)
- **Test 5: Out-of-Scope & Hallucination Resistance:** 3/3 Passed (100%)
- **Test 6: Latency & Speed Benchmarks:** 4/4 Passed (100%)
- **Test 7: Document Sync & Regression Lifecycle:** 8/8 Passed (100%)
- **Total:** **48/48 PASSED (100.0%)**

---

## 📂 Project Directory Structure

```
mce-ai-assistant/
├── app.py                     # Streamlit chat interface with faculty cards & streaming
├── rag.py                     # Core RAG engine: hybrid BM25+dense retrieval, streaming, caching
├── aliases.py                 # Query normalizer, typo tolerance, intent router
├── aliases.json               # Configurable dictionary of short forms, synonyms, typos
├── faculty_extractor.py       # OCR extraction pipeline, photo cropping & matching
├── faculty.json               # 157 structured faculty profiles
├── ingest.py                  # Knowledge base CLI management
├── ocr_helper.ps1             # Windows Media OCR PowerShell runner
├── run_all_tests.py           # 48-point automated test suite
├── test_sync.py               # Document lifecycle & regression tests
├── requirements.txt           # Python dependencies
├── .env.example               # Environment template
├── .gitignore                 # Git ignore rules
├── README.md                  # Documentation
├── assets/                    # Static assets
│   └── faculty/               # 157 cropped portrait photos + avatar placeholder
└── documents/                 # College documents & faculty PDFs
    ├── _deleted/              # Non-destructive recovery archive
    ├── faculty_photos/        # Drop-in folder for manual portrait photos
    ├── knowledge_base.pdf
    ├── malnad.pdf
    ├── placement.pdf
    └── *.pdf (10 faculty PDFs)
```
