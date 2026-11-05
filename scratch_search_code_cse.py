from pathlib import Path
import re

for p in sorted(Path(".").glob("*.py")):
    if p.name.startswith("scratch"):
        continue
    txt = p.read_text(encoding="utf-8", errors="ignore")
    for i, line in enumerate(txt.split("\n")):
        if re.search(r"\bhod\b", line, re.I) and re.search(r"\bcse\b", line, re.I):
            print(f"{p.name}:{i+1}: {line.strip()[:100]}")

