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

async def run_in_e2b(code: str, function_name: str = None, test_args: dict = None, dependencies: list[str] = None) -> dict:
    """
    Execute generated code using a local subprocess. Supports dynamic pip requirements execution.
    """
    uses_playwright = is_playwright_used(code)

    if function_name:
        test_code = f"import asyncio\n{code}\n\nasync def _test():\n    return await {function_name}(**{json.dumps(test_args or {})})\n\nprint('RESULT:', asyncio.run(_test()))"
    else:
        test_code = code

    logger.info(f"[Sandbox] Running code in Local Subprocess Sandbox... (Dependencies: {dependencies or 'None'})")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(test_code)
        temp_path = f.name
        
    temp_site_packages = None
    env = {}
    
    try:
        import os
        env = os.environ.copy()
        
        # Inject dependencies dynamically if requested
        if dependencies and isinstance(dependencies, list) and len(dependencies) > 0:
            temp_site_packages = tempfile.mkdtemp(prefix="sandbox_deps_")
            logger.info(f"[Sandbox] Installing dynamic dependencies {dependencies} into {temp_site_packages}")
            
            # Use pip to install into target directory
            pip_process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "--target", temp_site_packages, *dependencies,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await pip_process.communicate()
            if pip_process.returncode != 0:
                logger.error(f"[Sandbox] Dependency installation failed: {stderr.decode()}")
                return {"success": False, "error": f"Failed to install dependencies: {stderr.decode()}"}
                
            env["PYTHONPATH"] = f"{temp_site_packages}{os.pathsep}{env.get('PYTHONPATH', '')}"

        # Run local subprocess with 45 second timeout (to account for installation overhead if needed)
        process = await asyncio.create_subprocess_exec(
            sys.executable, temp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=45.0)
        except asyncio.TimeoutError:
            process.kill()
            return {"success": False, "error": "Execution timed out after 45 seconds."}

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
