const fs = require('fs');

const path = 'frontend/src/app/settings/page.tsx';
let text = fs.readFileSync(path, 'utf8');

const startCards = '<div style={{ display: \'flex\', gap: 12, marginBottom: 20 }}>';
const startGhost = '<Section title="Ghost Browser Target Accounts (Distribution Swarm Fallback)">';

const idx1 = text.indexOf(startCards);
const idx2 = text.indexOf(startGhost);

if (idx1 !== -1 && idx2 !== -1) {
    text = text.substring(0, idx1) + text.substring(idx2);
    text = text.replace('<Section title="Ghost Browser Target Accounts (Distribution Swarm Fallback)">', '<Section title="Ghost Browser Swarm Target Accounts">');
    
    fs.writeFileSync(path, text, 'utf8');
    console.log('Successfully removed Buffer API UI.');
} else {
    console.log('Could not find boundaries.');
}

