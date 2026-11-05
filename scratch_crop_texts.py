from PIL import Image
from pathlib import Path

img_dir = Path("scratch/hod_pdf_images")
out_dir = Path("scratch/hod_text_crops")
out_dir.mkdir(parents=True, exist_ok=True)

for f in sorted(img_dir.glob("*.jpg")):
    img = Image.open(f)
    w, h = img.size
    # Crop right portion containing text
    text_crop = img.crop((int(w * 0.22), 0, w, h))
    text_crop.save(out_dir / f"{f.stem}_text.jpg", quality=95)

print("Saved all text crops to scratch/hod_text_crops/")

