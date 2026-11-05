from PIL import Image
from pathlib import Path

img_dir = Path("scratch/all_dept_cse_images")
out_dir = Path("scratch/all_dept_cse_crops")
out_dir.mkdir(parents=True, exist_ok=True)

for f in sorted(img_dir.glob("page_26_*.jpg")):
    img = Image.open(f)
    w, h = img.size
    crop = img.crop((int(w * 0.22), 0, w, h))
    crop.save(out_dir / f"{f.stem}_text.jpg", quality=95)

print("Saved page 26 crops")

