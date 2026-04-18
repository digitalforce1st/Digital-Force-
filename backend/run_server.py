import sys
import asyncio
import os

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

def start_ngrok(port: int = 8000):
    """Start ngrok tunnel and print the public URL."""
    try:
        from pyngrok import ngrok, conf
        # Use the authtoken from env or hardcoded for local dev
        authtoken = os.environ.get("NGROK_AUTHTOKEN", "3CTdhTZhb44Ddv3fw4DlQZRkjAs_2atEtEaWJKsbbMLaWbyu9")
        conf.get_default().auth_token = authtoken
        tunnel = ngrok.connect(port, "http", domain="lunacy-unsettled-probe.ngrok-free.dev")
        public_url = tunnel.public_url
        print("\n" + "="*60)
        print(f"  🌐 DIGITAL FORCE PUBLIC URL (Ngrok)")
        print(f"  ➜  {public_url}")
        print(f"  ➜  API Docs: {public_url}/api/docs")
        print("="*60 + "\n")
        # Write URL to a file so it can be read by other scripts
        with open(".ngrok_url", "w") as f:
            f.write(public_url)
        return public_url
    except Exception as e:
        print(f"\n⚠️  Ngrok tunnel could not start: {e}")
        print("   Backend will run locally only.\n")
        return None

if __name__ == "__main__":
    # Start ngrok tunnel before uvicorn
    # start_ngrok(port=8000) # disabled to run ngrok in separate terminal
    # Exclude venv from reload watcher to prevent infinite restart loops
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["d:\\KASHIRI BRIGHTON\\BUSINESS\\AiiA\\Digital Force\\backend"],
        reload_excludes=["venv/*", "*.pyc", "__pycache__/*", "ngrok*", ".ngrok*"],
    )

