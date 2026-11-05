import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import io

doc = fitz.open(r"D:\MINI Project\Knowledge base\hod s of college.pdf")
print("Total pages in fitz:", len(doc))

with open("hod_pdf_ocr.txt", "w", encoding="utf-8") as out:
    for page_idx, page in enumerate(doc):
        out.write(f"\n================ PAGE {page_idx + 1} ================\n")
        text = page.get_text()
        out.write("--- DIRECT TEXT ---\n" + text + "\n")
        
        image_list = page.get_images(full=True)
        out.write(f"--- IMAGES FOUND: {len(image_list)} ---\n")
        for img_idx, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            img_obj = Image.open(io.BytesIO(image_bytes))
            out.write(f"Image {img_idx+1} (xref {xref}, size {img_obj.size}, ext {image_ext}):\n")
            try:
                ocr_text = pytesseract.image_to_string(img_obj)
                out.write("  OCR TEXT:\n" + ocr_text + "\n")
            except Exception as e:
                out.write(f"  OCR ERROR: {e}\n")

print("OCR complete! Check hod_pdf_ocr.txt")

