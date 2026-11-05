from PIL import Image
import numpy as np

img1 = Image.open("scratch/hod_pdf_images/page_1_img_1_Image1.jpg")
img2 = Image.open("scratch/hod_pdf_images/page_1_img_2_Image2.jpg")

arr1 = np.array(img1)
arr2 = np.array(img2)

print("Sizes:", img1.size, img2.size)
diff = np.abs(arr1.astype(int) - arr2.astype(int))
print("Max pixel diff:", np.max(diff), "Mean diff:", np.mean(diff))

