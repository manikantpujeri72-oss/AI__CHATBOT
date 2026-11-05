import pypdf, io, json, subprocess, re
from pathlib import Path
from PIL import Image

pdf_path = Path(r"D:\MINI Project\faculty\ISE faculty.pdf")
out_dir = Path(r"D:\MINI Project\faculty_photos_new")
out_dir.mkdir(parents=True, exist_ok=True)

reader = pypdf.PdfReader(str(pdf_path))
all_ise = []

for p_idx, page in enumerate(reader.pages):
    res = page.get("/Resources").get_object()
    xobj = res.get("/XObject").get_object()
    for k in sorted(xobj.keys()):
        raw = xobj[k].get_object().get_data()
        im = Image.open(io.BytesIO(raw))
        w, h = im.size
        
        # Check if stacked (height > 800)
        cards = []
        if h > 800:
            half = h // 2
            cards.append(("top", im.crop((0, 0, w, half))))
            cards.append(("bottom", im.crop((0, half, w, h))))
        else:
            cards.append(("single", im))
            
        for c_pos, card_im in cards:
            cw, ch = card_im.size
            # Photo is left ~22%
            pw = int(cw * 0.23)
            photo = card_im.crop((0, 0, pw, ch))
            
            # Text is right part
            txt_im = card_im.crop((pw, 0, cw, ch))
            txt_im.save("temp_crop_txt.jpg", "JPEG")
            
            r = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", "ocr_helper.ps1", "-ImagePath", "temp_crop_txt.jpg"], capture_output=True)
            txt = json.loads(r.stdout.decode("utf-8", errors="replace")).get("Text", "").strip()
            
            # Parse name from first line or before Assistant/Associate/Professor/Dean/Faculty
            name_m = re.search(r"\b(?:dr\.?|prof\.?|mr\.?|mrs\.?|ms\.?)\s+[A-Za-z\s.]+(?=\s+(?:Assistant|Associate|Professor|Dean|Faculty|B\.E|M\.Tech|Ph\.D|$))", txt, re.I)
            raw_name = name_m.group(0).strip() if name_m else txt.split("\n")[0][:30]
            clean_name = re.sub(r"^(?:11\s+|\d+\s+)", "", raw_name).strip()
            clean_name = re.sub(r"\s+(?:Assistant|Associate|Professor|Dean|Faculty|ID|IO).*$", "", clean_name, flags=re.I).strip()
            clean_name = re.sub(r"\s+", " ", clean_name)
            
            # Designation
            desig = "Assistant Professor"
            if "HOD" in txt or "Head of Department" in txt:
                desig = "Professor and Head of Department (HOD)"
            elif "Dean" in txt and "Professor" in txt:
                desig = "Professor & Dean (AA)"
            elif "Associate Professor" in txt:
                desig = "Associate Professor"
            elif "Professor" in txt and "Assistant" not in txt:
                desig = "Professor"
                
            email_m = re.search(r"[\w.-]+@mcehassan\.ac\.in", txt)
            email = email_m.group(0) if email_m else ""
            
            phone_m = re.search(r"\b(?:9\d{9}|8\d{9}|7\d{9}|6\d{9})\b", txt)
            phone = phone_m.group(0) if phone_m else ""
            
            qual_m = re.search(r"(?:B\.?E\.?|M\.?Tech\.?|Ph\.?D\.?|M\.?S\.?|MCA|M\.?Sc\.?)[^,\n]*", txt, re.I)
            qual = qual_m.group(0).strip() if qual_m else ""
            
            fn_safe = re.sub(r"[^\w]", "_", clean_name.lower()).strip("_")
            fn_safe = re.sub(r"_+", "_", fn_safe)
            photo_fn = f"ise_{fn_safe}.jpg"
            photo_path = out_dir / photo_fn
            photo.convert("RGB").save(photo_path, "JPEG", quality=88)
            
            all_ise.append({
                "name": clean_name,
                "designation": desig,
                "department": "Information Science and Engineering",
                "dept_code": "ISE",
                "qualification": qual,
                "email": email,
                "phone": phone,
                "photo_path": str(photo_path),
                "source_file": "ISE faculty.pdf",
                "page": p_idx + 1
            })

print(f"Total ISE faculty extracted: {len(all_ise)}")
for idx, p in enumerate(all_ise, 1):
    print(f"{idx}. {p['name']} | {p['designation']} | {p['qualification']} | {p['email']} | {p['phone']} | Page {p['page']}")

with open("ise_faculty_extracted.json", "w", encoding="utf-8") as f:
    json.dump(all_ise, f, indent=2, ensure_ascii=False)
