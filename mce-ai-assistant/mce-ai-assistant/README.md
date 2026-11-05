# 🎓 MCE AI Assistant

A robust, enterprise-grade RAG (Retrieval-Augmented Generation) chatbot for **Malnad College of Engineering (MCE), Hassan, Karnataka**.

The assistant answers questions strictly and only from verified college documents, providing exact citations (file name and page number) for every answer without hallucination or guesswork.

**Stack:** Python · Streamlit · Cohere (`command-a-plus-05-2026` + `embed-v4.0`) · ChromaDB

---

## 🚀 Quick Start (Windows)

```powershell
# 1. Activate the virtual environment
.\myenv\Scripts\activate

# 2. Install dependencies (if not already installed)
pip install -r requirements.txt

# 3. Configure environment variables
# Copy .env.example to .env and configure your COHERE_API_KEY
copy .env.example .env

# 4. Sync / index the knowledge base
python ingest.py --sync

# 5. Launch the Streamlit application
streamlit run app.py
```

---

## 📁 Supported File Formats

The ingestion engine automatically parses and chunks the following file types:

| Format | Extension | Processing Details |
|---|---|---|
| **PDF** | `.pdf` | Multi-page text extraction with unicode normalization. (Text-based PDFs only). |
| **Word** | `.docx` | Paragraphs and structured tables formatted into searchable row representations. |
| **Text** | `.txt`, `.md` | Plain text and Markdown documents. |
| **Excel** | `.xlsx`, `.xlsm` | One "page" per worksheet with column headers mapped to each row. |
| **CSV** | `.csv` | Tabular row-by-row lines formatted with column headers. |
| **PowerPoint** | `.pptx`, `.ppt` | One "page" per slide, including slide text, tables, and presenter notes. |
| **HTML** | `.html`, `.htm` | Clean visible text stripped of scripts, styles, and SVG markup. |

---

## 🔄 Maintaining the Knowledge Base

The knowledge base database (`chroma_db/`) automatically mirrors the exact content of `documents/`.

### 1. Adding New Documents
- **Via CLI:**
  ```powershell
  python ingest.py --add "C:\path\to\syllabus-2026.pdf"
  python ingest.py --add "fees.xlsx" --as "admissions/fees-2026.xlsx"
  ```
- **Via Web UI:** Drop files into the sidebar uploader. Files with new names are indexed directly.
- **Via Folder Copy:** Simply copy any supported file into `documents/` (or subfolders) and run:
  ```powershell
  python ingest.py --sync
  ```

### 2. Updating / Replacing with the Same Name
When a document is edited or replaced under the same filename:
- The system computes the SHA-1 hash of the file bytes.
- The new version is **embedded first**. Only after embedding succeeds are old chunks deleted and new chunks written. A network interruption or failed embedding will never leave your document missing or corrupted.
- **CLI Example:**
  ```powershell
  python ingest.py --sync
  ```

### 3. Replacing with a Different Name
To replace an obsolete document with an updated file that has a different filename:
- **Via CLI:**
  ```powershell
  python ingest.py --replace "placement-2024.pdf" "placement-2026.pdf"
  ```
- **Via Web UI:** Expand **"🔁 Replace a document"** in the sidebar, select the old document from the dropdown, upload the new file, check the confirmation box, and click **Confirm & Replace**.
- The old document's chunks are deleted from ChromaDB, its file is safely moved to `documents/_deleted/`, and the new document is indexed in a single atomic step.

### 4. Deleting Documents (Non-Destructive)
- **Via CLI:**
  ```powershell
  python ingest.py --delete "fees-2023.pdf"
  ```
- **Via Web UI:** Expand **"🗑️ Delete a document"** in the sidebar, choose the file, check confirmation, and click **Delete Document**.
- **Safe Recovery:** Chunks are removed from ChromaDB, and the file is moved to `documents/_deleted/` (timestamped if name conflicts exist). Files are **never permanently deleted**.

### 5. Rename Detection
If you rename a file inside `documents/`, running `python ingest.py --sync` detects that the file hash matches a removed document. It seamlessly re-indexes the document under the new name and purges the old name without leaving duplicate chunks.

### 6. Synchronisation Rules & Filtering
When running `sync_documents`:
- Recursively inspects all subfolders (`rglob`).
- Ignores hidden files (`.*`), temporary lock files (`~$*.docx`), `Thumbs.db`, and everything inside `documents/_deleted/`.
- Overwrites deterministic chunk IDs (`sha1(source)[:12]-index`) ensuring zero duplicate chunk IDs exist.
- Automatically migrates legacy collections lacking `file_hash` metadata on first sync.

---

## 🛠️ CLI Reference (`ingest.py`)

| Command | Description |
|---|---|
| `python ingest.py --sync` | Synchronise `documents/` with ChromaDB (default action). |
| `python ingest.py --dry-run` | Preview additions, updates, renames, and deletions without changing anything. |
| `python ingest.py --list` | List all indexed documents with chunk count, page count, file hash, and last indexed time. |
| `python ingest.py --add <file> [--as <path>]` | Add or update a file in the knowledge base. |
| `python ingest.py --replace <old-source> <new-file>` | Replace an existing document with a new file. |
| `python ingest.py --delete <source>` | Delete document chunks and move file to `_deleted/`. |
| `python ingest.py --reset` | Wipe ChromaDB and rebuild collection from scratch from `documents/`. |

---

## 🔐 Admin Password Protection

To restrict document upload, replacement, deletion, and database reset controls so that students see only the chat interface:

1. Open `.env` and set:
   ```bash
   ADMIN_PASSWORD=your_secret_admin_password
   ```
2. When `ADMIN_PASSWORD` is set, management tools are hidden until the administrator enters the password in the sidebar.
3. If `ADMIN_PASSWORD` is left unset or commented out, management controls remain open.

---

## 🧪 Automated Test Suites

### A. Lifecycle & Sync Tests (`test_sync.py`)
Runs 8 isolated unit tests against a temporary directory and mock Cohere client (zero API credits consumed):
```powershell
python test_sync.py -v
```
Verifies:
- **a.** New document becomes retrievable
- **b.** Re-running sync changes nothing (idempotence)
- **c.** Editing document removes old chunks and makes new text retrievable
- **d.** Replacing document with differently named file removes the old version completely
- **e.** Deleting a file from the folder and syncing removes its chunks
- **f.** Renaming a file leaves no duplicates
- **g.** Failed embedding during update preserves the old version in the database
- **h.** No duplicate chunk IDs ever exist across adds, updates, and renames

### B. Real-World Retrieval Tests (`test_queries.py`)
Tests 15 realistic questions (12 in-scope and 3 out-of-scope) against your actual knowledge base:
```powershell
python test_queries.py
```
- In-scope questions confirm facts about departments, programmes, intakes, placements, and campus facilities with citations.
- Out-of-scope questions confirm the bot gracefully returns the standard fallback message without inventing facts.

---

## 📂 Project Directory Structure

```
mce-ai-assistant/
├── app.py                # Streamlit chat interface with admin controls
├── rag.py                # Core RAG logic, parsing, chunking, embeddings & sync
├── ingest.py             # CLI tool for knowledge base management
├── test_sync.py          # Unit test suite for sync lifecycle (mocked embeddings)
├── test_queries.py       # Live accuracy and boundary query verification suite
├── requirements.txt      # Project dependencies
├── .env.example          # Template for environment configuration
├── .gitignore            # Git exclusion rules (.env, chroma_db/, etc.)
├── README.md             # Project documentation
├── documents/            # College knowledge base files
│   ├── _deleted/         # Safe recovery archive for deleted documents
│   ├── knowledge_base.pdf
│   ├── malnad.pdf
│   └── placement.pdf
└── chroma_db/            # Persistent vector database directory
```

---

## ⚠️ Documents Needing Attention

When inspecting the initial files from `mini_project_KB`:
- `knowledge_base.pdf`, `malnad.pdf`, and `placement.pdf` contain rich, searchable digital text and are indexed into 83 high-quality chunks.
- The 10 department faculty files (`AIML faculty.pdf`, `civil faculty.pdf`, `CSBS Faculty.pdf`, `CSE department.pdf`, `electrical and electronics faculty.pdf`, `electronics and communication Department.pdf`, `ISE faculty.pdf`, `mca and ece.pdf`, `mechanical faculty.pdf`, `VLSI faculty.pdf`) are **scanned/image-only PDFs** containing embedded raster images without an extractable text layer (yielding 0 text characters).
- **Recommendation:** Run OCR (Optical Character Recognition) on those scanned PDFs (e.g. using Adobe Acrobat, Tesseract, or online OCR) or convert the faculty rosters to text, Excel (`.xlsx`), Word (`.docx`), or CSV formats, place them in `documents/`, and run `python ingest.py --sync`.
