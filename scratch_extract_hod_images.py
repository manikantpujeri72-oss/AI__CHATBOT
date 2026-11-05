import os
from pypdf import PdfReader
from pathlib import Path

pdf_path = r"D:\MINI Project\Knowledge base\hod s of college.pdf"
reader = PdfReader(pdf_path)

out_dir = Path("scratch/hod_pdf_images")
out_dir.mkdir(parents=True, exist_ok=True)

for i, page in enumerate(reader.pages):
    print(f"Page {i+1} has {len(page.images)} images")
    for j, img in enumerate(page.images):
        name = f"page_{i+1}_img_{j+1}_{img.name}"
        with open(out_dir / name, "wb") as f:
            f.write(img.data)
        print(f"  Saved {name} ({len(img.data)} bytes)")

