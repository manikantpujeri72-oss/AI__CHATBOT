from pypdf import PdfReader

r = PdfReader(r"D:\MINI Project\Knowledge base\overview of mce.pdf")
print("Total pages in overview of mce.pdf:", len(r.pages))
p8 = r.pages[7].extract_text() or ""
print("--- PAGE 8 OF overview of mce.pdf ---")
print(p8)

