import sys
from pypdf import PdfReader

pdf_path = r"D:\MINI Project\Knowledge base\hod s of college.pdf"
reader = PdfReader(pdf_path)

with open("hod_pdf_dump.txt", "w", encoding="utf-8") as out:
    out.write(f"Total pages in 'hod s of college.pdf': {len(reader.pages)}\n")
    for i, page in enumerate(reader.pages):
        txt = page.extract_text() or ""
        out.write(f"\n================ PAGE {i+1} ================\n")
        out.write(txt + "\n")

print("Dumped to hod_pdf_dump.txt successfully")
