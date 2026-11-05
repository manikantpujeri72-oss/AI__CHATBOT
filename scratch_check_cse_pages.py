from pypdf import PdfReader

r = PdfReader(r"D:\MINI Project\Knowledge base\all department faculty.pdf")

with open("all_dept_faculty_cse.txt", "w", encoding="utf-8") as out:
    for p in range(25, 35):
        out.write(f"\n--- PAGE {p+1} ---\n")
        out.write(r.pages[p].extract_text() or "")

print("Saved pages 26-35 to all_dept_faculty_cse.txt")

