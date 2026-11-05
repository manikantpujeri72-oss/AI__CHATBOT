from pypdf import PdfReader
from pathlib import Path

pdf_path = Path("documents/CSE department.pdf")
reader = PdfReader(str(pdf_path))
print(f"Total pages in CSE department.pdf: {len(reader.pages)}")

out_dir = Path("scratch/cse_pdf_images")
out_dir.mkdir(parents=True, exist_ok=True)

for i, page in enumerate(reader.pages):
    print(f"Page {i+1}: text len = {len(page.extract_text() or '')}, images count = {len(page.images)}")
    for j, img in enumerate(page.images):
        name = f"page_{i+1}_img_{j+1}_{img.name}"
        with open(out_dir / name, "wb") as f:
            f.write(img.data)
        print(f"  Saved {name} ({len(img.data)} bytes)")
