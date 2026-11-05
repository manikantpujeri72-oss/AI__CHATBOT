from pypdf import PdfReader

r = PdfReader(r"D:\MINI Project\Knowledge base\hod s of college.pdf")
p = r.pages[0]

# Let's see the order and positions of images on page 0
print("MediaBox:", p.mediabox)

# We can inspect the raw content stream
content = p.get_contents()
if content:
    data = content.get_data().decode('latin-1', errors='ignore')
    # look for Do operator (draw object) and cm (current transformation matrix)
    lines = data.split('\n')
    for i, line in enumerate(lines):
        if '/Do' in line or 'Do' in line.split():
            # print preceding few lines for transformation matrix
            context = lines[max(0, i-4):i+1]
            print("Image call context:", " | ".join(c.strip() for c in context))

