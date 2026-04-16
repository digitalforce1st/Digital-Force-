"""
Digital Force — Sandbox Execution Tool
Provides a Local subprocess runner for all agents to execute Python/Playwright scraping code.
"""

import json
import logging
import asyncio
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

def is_playwright_used(code: str) -> bool:
    """Detect if the generated script uses Playwright."""
    return "playwright" in code.lower() or "async_playwright" in code

async def run_in_e2b(code: str, function_name: str = None, test_args: dict = None) -> dict:
    """
    Execute generated code using a local subprocess.
    Maintains the 'run_in_e2b' signature for backwards compatibility but does not use E2B.
    """
    uses_playwright = is_playwright_used(code)

    if function_name:
        test_code = f"import asyncio\n{code}\n\nasync def _test():\n    return await {function_name}(**{json.dumps(test_args or {})})\n\nprint('RESULT:', asyncio.run(_test()))"
    else:
        test_code = code

    logger.info("[Sandbox] Running code in Local Subprocess Sandbox...")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(test_code)
        temp_path = f.name
        
    try:
        # Run local subprocess with 30 second timeout
        process = await asyncio.create_subprocess_exec(
            sys.executable, temp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
        except asyncio.TimeoutError:
            process.kill()
            return {"success": False, "error": "Execution timed out after 30 seconds."}

        output = stdout.decode(errors='replace').strip()
        error = stderr.decode(errors='replace').strip()
        
        sandbox_type = "local_playwright" if uses_playwright else "local_standard"
        
        # Determine success
        if process.returncode != 0:
            return {"success": False, "error": error or output, "output": output, "sandbox": sandbox_type}
            
        success = ("'success': False" not in output)
        return {"success": success, "output": output, "error": error if error else None, "sandbox": sandbox_type}
        
    except Exception as e:
        logger.error("Local execution failed: %s", str(e), exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except Exception:
            pass
