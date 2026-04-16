import sys
import asyncio

if sys.platform == 'win32':
    # Explicitly set Proactor event loop policy (required by Playwright)
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # Intercept any attempts from Uvicorn's setup_event_loop to override this with SelectorEventLoop
    _original_set_policy = asyncio.set_event_loop_policy
    def _intercept_set_policy(policy):
        if isinstance(policy, asyncio.WindowsSelectorEventLoopPolicy):
            # Block the incompatible policy!
            return
        _original_set_policy(policy)
    asyncio.set_event_loop_policy = _intercept_set_policy

import uvicorn

if __name__ == "__main__":
    # We pass the application as an import string to support reload
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
