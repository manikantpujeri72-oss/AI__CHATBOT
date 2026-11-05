from pypdf import PdfReader
from pathlib import Path

r = PdfReader(r"D:\MINI Project\Knowledge base\all department faculty.pdf")
out_dir = Path("scratch/all_dept_cse_images")
out_dir.mkdir(parents=True, exist_ok=True)

for p in range(25, 32):
    page = r.pages[p]
    print(f"Page {p+1} has {len(page.images)} images")
    for j, img in enumerate(page.images):
        name = f"page_{p+1}_img_{j+1}_{img.name}"
        with open(out_dir / name, "wb") as f:
            f.write(img.data)
        print(f"  Saved {name} ({len(img.data)} bytes)")

