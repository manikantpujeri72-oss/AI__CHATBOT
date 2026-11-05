from pypdf import PdfReader

r = PdfReader(r"D:\MINI Project\Knowledge base\all department faculty.pdf")
print("Total pages in all department faculty.pdf:", len(r.pages))

for i, page in enumerate(r.pages):
    txt = page.extract_text() or ""
    for line in txt.split("\n"):
        if any(w in line.lower() for w in ["computer", "cse", "head", "hod"]):
            print(f"p.{i+1}: {line[:100]}")

