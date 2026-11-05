from PIL import Image
from pathlib import Path

img_dir = Path("scratch/hod_pdf_images")
for f in sorted(img_dir.glob("*.jpg")):
    img = Image.open(f)
    print(f"{f.name}: size={img.size}, mode={img.mode}")

