from pypdf import PdfReader

r = PdfReader(r"D:\MINI Project\Knowledge base\overview of mce.pdf")

print(f"Total pages: {len(r.pages)}")
with open("scratch/all_headings_overview_mce.txt", "w", encoding="utf-8") as out:
    for i, p in enumerate(r.pages):
        t = p.extract_text() or ""
        lines = [line.strip() for line in t.split("\n") if line.strip()]
        for l in lines[:5]:
            if any(k in l.lower() for k in ["about", "department", "vision", "mission", "programme", "facility", "club", "fee"]):
                out.write(f"Page {i+1}: {l}\n")

print("Saved scratch/all_headings_overview_mce.txt")

