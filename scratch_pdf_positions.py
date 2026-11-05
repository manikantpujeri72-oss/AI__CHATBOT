from pypdf import PdfReader

reader = PdfReader(r"D:\MINI Project\Knowledge base\hod s of college.pdf")

with open("scratch/page1_text_positions.txt", "w", encoding="utf-8") as out:
    def visitor_body(text, cm, tm, font_dict, font_size):
        if text.strip():
            y = cm[5] if cm else (tm[5] if tm else 0)
            out.write(f"y={y:.1f} | Text: '{text.strip()}'\n")

    reader.pages[0].extract_text(visitor_text=visitor_body)

print("Saved scratch/page1_text_positions.txt")
