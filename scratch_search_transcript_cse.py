import json

path = r'C:\Users\manik\.gemini\antigravity\brain\c0148c6b-1464-49ea-bba5-3b144657d9bf\.system_generated\logs\transcript_full.jsonl'

matches = []
with open(path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if any(k in line.lower() for k in ["cse hod", "hod of cse", "real cse hod", "chandrika", "ananda babu"]):
            if "USER_INPUT" in line:
                d = json.loads(line)
                matches.append((i, d.get("content", "")[:300]))

print(f"Total matching user turns: {len(matches)}")
for idx, content in matches[-5:]:
    print(f"\nTurn line {idx}:\n{content}")

