from pypdf import PdfReader

r = PdfReader(r"D:\MINI Project\Knowledge base\about first year department.pdf")
print("Total pages:", len(r.pages))
for i, p in enumerate(r.pages):
    print(f"\n--- Page {i+1} ---")
    print(p.extract_text()[:400])

