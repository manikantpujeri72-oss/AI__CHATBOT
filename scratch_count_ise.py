import json

with open("faculty_profiles_new.json", "r", encoding="utf-8") as f:
    profs = json.load(f)

ise = [p for p in profs if p.get("department") == "Information Science and Engineering"]
print("ISE count:", len(ise))
for p in ise:
    print(" ", p.get("name"), "->", p.get("designation"))

