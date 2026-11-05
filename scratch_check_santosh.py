import json
from pathlib import Path

with open("faculty_profiles_new.json", "r", encoding="utf-8") as f:
    profs = json.load(f)

for p in profs:
    if "santosh" in p.get("name", "").lower() or "santhosh" in p.get("name", "").lower():
        print(p.get("name"), "| Dept:", p.get("department"), "| Photo:", p.get("photo_path"))
        if p.get("photo_path"):
            print("  Exists:", Path(p.get("photo_path")).exists())

