from pypdf import PdfReader

r = PdfReader(r"D:\MINI Project\Knowledge base\overview of mce.pdf")

with open("scratch/overview_mce_cse_mentions.txt", "w", encoding="utf-8") as out:
    for i, p in enumerate(r.pages):
        t = p.extract_text() or ""
        lines = [line.strip() for line in t.split("\n") if line.strip()]
        for l in lines:
            if any(k in l.lower() for k in ["computer science", "cs & engg", "department of computer", "cse"]):
                out.write(f"Page {i+1}: {l}\n")

print("Saved scratch/overview_mce_cse_mentions.txt")

