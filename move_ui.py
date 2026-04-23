import sys

with open('frontend/src/app/settings/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

start_str = '<Section title="Ghost Browser Target Accounts (Distribution Swarm Fallback)">'
end_str = '<Section title="Proxy Provider Integration">'

start_idx = text.find(start_str)
end_idx = text.find(end_str)

if start_idx != -1 and end_idx != -1:
    ghost_block = text[start_idx:end_idx].strip()
    # remove the block from current place
    text = text[:start_idx] + text[end_idx:]

    # find where to insert it: right before the </div> closing the publishing tab
    buffer_end = text.find('        {/* ── Autonomous Mode ── */}')
    if buffer_end != -1:
        insert_idx = text.rfind('          </div>\n        )}', 0, buffer_end)
        if insert_idx != -1:
            # Add padding
            text = text[:insert_idx] + '            ' + ghost_block + '\n\n' + text[insert_idx:]

            with open('frontend/src/app/settings/page.tsx', 'w', encoding='utf-8') as f:
                f.write(text)
            print('Successfully moved Ghost Browser Target Accounts UI block to Publishing Fleet tab.')
        else:
            print('Could not find insert point.')
    else:
        print('Could not find buffer end marker.')
else:
    print('Could not find ghost block boundaries.')
