import os
from pypdf import PdfReader
from pathlib import Path

docs_dir = Path("documents")
for pdf in sorted(docs_dir.glob("*.pdf")):
    r = PdfReader(str(pdf))
    print("=" * 60)
    print(f"FILE: {pdf.name} (pages: {len(r.pages)})")
    text = ""
    for i in range(min(3, len(r.pages))):
        t = r.pages[i].extract_text() or ""
        text += f"\n--- Page {i+1} ---\n" + t
    for line in text.split("\n"):
        line = line.strip()
        if any(k in line.lower() for k in ["head", "hod", "professor", "department", "computer science"]):
            print(" ", line[:100])

