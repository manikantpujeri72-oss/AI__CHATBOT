import pypdf, io, json, subprocess, re
from pathlib import Path
from PIL import Image

fac_dir = Path(r"D:\MINI Project\faculty")
pdfs = sorted(fac_dir.glob("*.pdf"))

print(f"Inspecting {len(pdfs)} PDFs in {fac_dir}...")
results = {}

for p in pdfs:
    reader = pypdf.PdfReader(str(p))
    card_count = 0
    for page in reader.pages:
        res = page.get("/Resources")
        if res and hasattr(res, "get_object"): res = res.get_object()
        xobj = res.get("/XObject") if res else {}
        if xobj and hasattr(xobj, "get_object"): xobj = xobj.get_object()
        if not xobj: continue
        for k in xobj.keys():
            raw = xobj[k].get_object().get_data()
            im = Image.open(io.BytesIO(raw))
            w, h = im.size
            if h > 800 and p.name == "ISE faculty.pdf":
                card_count += 2
            else:
                card_count += 1
    results[p.name] = {"pages": len(reader.pages), "cards": card_count}
    print(f"  {p.name}: {len(reader.pages)} pages -> {card_count} faculty cards")

with open("department_pdf_counts.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
