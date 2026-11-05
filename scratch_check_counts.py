import chromadb

client = chromadb.PersistentClient('chroma_db')
counts = {c.name: c.count() for c in client.list_collections()}
print('INITIAL CHROMA COLLECTION COUNTS:')
for k, v in sorted(counts.items()):
    print(f'  {k}: {v}')
assert counts.get('mce_docs') == 83, f"Expected 83, got {counts.get('mce_docs')}"
print('mce_docs is exactly 83.')
