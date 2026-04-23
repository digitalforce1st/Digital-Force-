import sys

with open('frontend/src/app/settings/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Remove the metric cards and the Buffer API Credential Pool section
start_cards = '<div style={{ display: \'flex\', gap: 12, marginBottom: 20 }}>'
start_ghost = '<Section title="Ghost Browser Target Accounts (Distribution Swarm Fallback)">'

idx1 = text.find(start_cards)
idx2 = text.find(start_ghost)

if idx1 != -1 and idx2 != -1:
    # remove the snippet between the start of the cards and the start of the ghost accounts section!
    text = text[:idx1] + text[idx2:]

    # Rename the ghost section title to not say Fallback
    text = text.replace('<Section title="Ghost Browser Target Accounts (Distribution Swarm Fallback)">', '<Section title="Ghost Browser Swarm Target Accounts">')

    # Remove buffer variables from top of file to prevent unused var linting? Not strictly needed for js, maybe react strict will complain
    # We will just leave them or let's remove fetch calls if we want.

    with open('frontend/src/app/settings/page.tsx', 'w', encoding='utf-8') as f:
        f.write(text)
    print('Successfully removed Buffer API UI.')
else:
    print('Could not find boundaries.')
