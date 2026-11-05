from pathlib import Path
from pypdf import PdfReader

for pdf in sorted(Path("documents").glob("*.pdf")):
    r = PdfReader(str(pdf))
    for i, p in enumerate(r.pages):
        t = p.extract_text() or ""
        if "ezhil" in t.lower() or "vannan" in t.lower():
            print(f"Found Ezhil in {pdf.name} page {i+1}")

for pdf in sorted(Path(r"D:\MINI Project\Knowledge base").glob("*.pdf")):
    r = PdfReader(str(pdf))
    for i, p in enumerate(r.pages):
        t = p.extract_text() or ""
        if "ezhil" in t.lower() or "vannan" in t.lower():
            print(f"Found Ezhil in Knowledge base/{pdf.name} page {i+1}")

