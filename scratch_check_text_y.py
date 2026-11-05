from pypdf import PdfReader
import re

reader = PdfReader(r"D:\MINI Project\Knowledge base\hod s of college.pdf")
stream_data = reader.pages[0].get_contents().get_data().decode('latin-1')

# Find text blocks and their tm / Td positions
text_matches = re.findall(r'([0-9.-]+\s+[0-9.-]+)\s+Td\s*\n?\s*\((.*?)\)\s*Tj', stream_data)
print("Text positions:")
for tm in text_matches:
    print(f"  Pos: {tm[0]} -> Text: {tm[1]}")

