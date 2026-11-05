from pathlib import Path

crops = sorted(Path("scratch/cse_text_crops").glob("*.jpg"))
print(f"Total crops: {len(crops)}")
for c in crops:
    print(c.name)

