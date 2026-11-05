import os
from pathlib import Path
from pypdf import PdfReader

def search_pdfs():
    kb_dir = Path(r"D:\MINI Project\Knowledge base")
    doc_dir = Path("documents")
    
    all_pdfs = list(kb_dir.glob("*.pdf")) + list(doc_dir.glob("*.pdf"))
    print(f"Total PDFs found: {len(all_pdfs)}")
    
    for pdf_path in all_pdfs:
        try:
            reader = PdfReader(pdf_path)
            for page_idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                # Check for AIDS, Data Science, Artificial Intelligence and Data Science
                lower_text = text.lower()
                if "data science" in lower_text or "ai & ds" in lower_text or "aids" in lower_text:
                    lines = [l.strip() for l in text.split("\n") if any(k in l.lower() for k in ["data science", "ai & ds", "aids", "faculty", "assistant professor", "associate professor", "professor", "head", "hod"])]
                    print(f"\n--- {pdf_path.name} (Page {page_idx+1}) ---")
                    for l in lines[:10]:
                        print("  ", l)
        except Exception as e:
            print(f"Error reading {pdf_path.name}: {e}")

if __name__ == "__main__":
    search_pdfs()
