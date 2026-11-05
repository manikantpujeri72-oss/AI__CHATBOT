with open("faculty_lookup.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace non-ascii characters in faculty_lookup.py
content = content.replace("\u20b9", "Rs. ")
content = content.replace("\u2013", "-")
content = content.replace("\u2014", "-")
content = content.replace("\u2018", "'")
content = content.replace("\u2019", "'")
content = content.replace("\u201c", '"')
content = content.replace("\u201d", '"')

with open("faculty_lookup.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Sanitized faculty_lookup.py of non-ASCII unicode symbols.")

