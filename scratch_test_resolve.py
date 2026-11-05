import short_forms

test_cases = [
    "hi",
    "hello",
    "hey",
    "overview of ise department",
    "overview of cse department'",
    "tell me about mathematics department",
    "about civil department",
    "fee structure",
    "clubs at mce",
    "asdf qwer",
    "overview of xyz department",
]

for t in test_cases:
    code, can, score = short_forms.resolve_department(t)
    print(f"'{t}' -> code={code}, canonical={can}, score={score}")

