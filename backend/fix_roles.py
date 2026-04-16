import os
import re

d = 'agent/nodes'
files_to_check = [f for f in os.listdir(d) if f.endswith('.py')]

for f in files_to_check:
    p = os.path.join(d, f)
    with open(p, 'r', encoding='utf-8') as file:
        content = file.read()
    
    def replacer(match):
        role_val = match.group(1)
        if role_val in ['user', 'assistant', 'system']:
            return match.group(0)
        # Rewrite to correct LangChain format
        return f'{{\"role\": \"assistant\", \"name\": \"{role_val}\", \"content\":'

    # Match {"role": "<xyz>", "content": ...
    new_content = re.sub(r'\{\s*"role"\s*:\s*"([a-zA-Z0-9_]+)"\s*,\s*"content"\s*:', replacer, content)
    
    # Also handle single quote syntax if any: {'role': 'xyz', 'content': ...
    def replacer2(match):
        role_val = match.group(1)
        if role_val in ['user', 'assistant', 'system']:
            return match.group(0)
        return f"{{\'role\': \'assistant\', \'name\': \'{role_val}\', \'content\':"

    new_content = re.sub(r'\{\s*\'role\'\s*:\s*\'([a-zA-Z0-9_]+)\'\s*,\s*\'content\'\s*:', replacer2, new_content)

    if new_content != content:
        with open(p, 'w', encoding='utf-8') as file:
            file.write(new_content)
        print(f'Updated {f}')

# Fix executive.py special case dynamically defined logic
p = os.path.join(d, 'executive.py')
with open(p, 'r', encoding='utf-8') as file:
    content = file.read()
fixed_content = content.replace(
    '{"role": m.get("role", "user") if isinstance(m, dict) else "user",',
    '{"role": m.get("role", "user") if isinstance(m, dict) and m.get("role") in ["user","assistant","system"] else "assistant",'
)
if fixed_content != content:
    with open(p, 'w', encoding='utf-8') as file:
        file.write(fixed_content)
        print(f'Updated executive.py (custom)')
print("DONE")
