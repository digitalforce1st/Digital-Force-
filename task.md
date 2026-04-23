# Task: Ghost Browser Apple-UX Cookie Authentication

## Phase 1: Backend API Handlers
- [x] Add `POST /{account_id}/ghost-auth/start` in `api/accounts.py`
- [x] Add `POST /{account_id}/ghost-auth/verify` in `api/accounts.py`

## Phase 2: Frontend UX
- [x] Add 'Authenticate' button to Ghost accounts in `settings/page.tsx`
- [x] Build the Glassmorphic Auth Modal overlay
- [x] Wire up start/verify API requests from UI

## Phase 3: Verification
- [ ] Ensure Ghost Browser correctly triggers a local headed Chromium window
- [ ] Ensure Database status updates correctly
