from PIL import Image
from pathlib import Path

img_dir = Path("scratch/cse_pdf_images")
out_dir = Path("scratch/cse_text_crops")
out_dir.mkdir(parents=True, exist_ok=True)

for f in sorted(img_dir.glob("*.jpg")):
    img = Image.open(f)
    w, h = img.size
    # crop text area
    crop = img.crop((int(w * 0.22), 0, w, h))
    crop.save(out_dir / f"{f.stem}_text.jpg", quality=95)

print("Saved all CSE text crops to scratch/cse_text_crops/")

