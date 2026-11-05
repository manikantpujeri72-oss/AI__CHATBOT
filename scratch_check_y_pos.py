from pypdf import PdfReader

reader = PdfReader(r"D:\MINI Project\Knowledge base\hod s of college.pdf")
page = reader.pages[0]

# In pypdf, we can inspect page['/Resources']['/XObject']
xobjects = page['/Resources']['/XObject'].get_object()

print("XObjects on Page 1:", list(xobjects.keys()))

# Let's inspect the content stream to find cm matrices before each Do
contents = page.get_contents()
stream_data = contents.get_data().decode('latin-1')

import re
# Find all occurrences of cm followed by /ImageX Do
matches = re.findall(r'([0-9.-]+\s+[0-9.-]+\s+[0-9.-]+\s+[0-9.-]+\s+[0-9.-]+\s+[0-9.-]+)\s+cm\s*\n?\s*(/[A-Za-z0-9_]+)\s+Do', stream_data)
for m in matches:
    matrix = [float(x) for x in m[0].split()]
    print(f"Image {m[1]} drawn at x={matrix[4]}, y={matrix[5]}, w={matrix[0]}, h={matrix[3]}")

