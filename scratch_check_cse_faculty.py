import json

with open("faculty_profiles_new.json", "r", encoding="utf-8") as f:
    profiles = json.load(f)

print("--- Computer Science and Engineering Faculty ---")
for p in profiles:
    if "computer science and engineering" == p.get("department", "").lower():
        print(f"Name: {p.get('name')}, Desig: {p.get('designation')}, Qual: {p.get('qualification')}, Email: {p.get('email')}, Phone: {p.get('phone')}, Photo: {p.get('photo_path')}")

