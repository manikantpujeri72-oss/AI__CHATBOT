from pypdf import PdfReader

r = PdfReader(r"D:\MINI Project\Knowledge base\about first year department.pdf")

with open("scratch/first_year_pdf_dump.txt", "w", encoding="utf-8") as out:
    for i, p in enumerate(r.pages):
        out.write(f"\n================ PAGE {i+1} ================\n")
        out.write(p.extract_text() or "")

print("Saved scratch/first_year_pdf_dump.txt")

