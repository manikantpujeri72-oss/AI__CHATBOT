from PIL import Image

img = Image.open("scratch/hod_pdf_images/page_1_img_3_Image3.jpg")
print("Card size:", img.size)

# The photo box in the card
# Let's crop x: 45 to 430, y: 35 to 475
photo = img.crop((45, 35, 430, 475))
photo.save("scratch/dr_ezhil_vannan_s_crop.jpg", quality=95)
print("Saved photo crop (size:", photo.size, ")")

