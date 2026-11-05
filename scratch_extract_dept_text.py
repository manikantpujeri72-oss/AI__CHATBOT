import json
from pathlib import Path
from pypdf import PdfReader

mce_pdf = Path(r"D:\MINI Project\Knowledge base\overview of mce.pdf")
fy_pdf = Path(r"D:\MINI Project\Knowledge base\about first year department.pdf")

r_mce = PdfReader(str(mce_pdf))
r_fy = PdfReader(str(fy_pdf))

def get_mce_pages(start_page, end_page):
    """Extract text from 1-indexed page range in overview of mce.pdf."""
    return "\n\n".join(r_mce.pages[p - 1].extract_text() or "" for p in range(start_page, end_page + 1))

def get_fy_pages(start_page, end_page):
    """Extract text from 1-indexed page range in about first year department.pdf."""
    return "\n\n".join(r_fy.pages[p - 1].extract_text() or "" for p in range(start_page, end_page + 1))

print("Extracting department text from PDFs...")

# Let's inspect pages 27 to 40 of overview of mce.pdf
with open("scratch/dept_pages_27_40.txt", "w", encoding="utf-8") as out:
    for p in range(27, 41):
        out.write(f"\n================ PAGE {p} ================\n")
        out.write(r_mce.pages[p - 1].extract_text() or "")

print("Saved scratch/dept_pages_27_40.txt")

