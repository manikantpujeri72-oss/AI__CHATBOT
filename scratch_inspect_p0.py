from pypdf import PdfReader
import sys

r = PdfReader(r"D:\MINI Project\Knowledge base\hod s of college.pdf")
p = r.pages[0]

with open("scratch/page0_raw.txt", "w", encoding="utf-8") as f:
    f.write(p.extract_text() or "")

print("Saved scratch/page0_raw.txt")
