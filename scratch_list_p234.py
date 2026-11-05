from PIL import Image
from pathlib import Path

img_dir = Path("scratch/cse_text_crops")
for f in sorted(img_dir.glob("page_[234]_*.jpg")):
    # print file name
    print(f.name)

