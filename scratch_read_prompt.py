import json

path = r'C:\Users\manik\.gemini\antigravity\brain\c0148c6b-1464-49ea-bba5-3b144657d9bf\.system_generated\logs\transcript_full.jsonl'
with open(path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'TASK: Fix five bugs' in line:
            d = json.loads(line)
            content = d.get('content', '')
            print(f'Found at line {i}, step {d.get("step_index")}')
            with open('full_task_prompt.txt', 'w', encoding='utf-8') as out:
                out.write(content)
            print('Saved to full_task_prompt.txt (bytes:', len(content), ')')
            break
