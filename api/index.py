import os
import sys

# Ensure both current directory, parent root, and CWD are in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
cwd = os.getcwd()

for p in [root_dir, current_dir, cwd]:
    if p and p not in sys.path:
        sys.path.insert(0, p)

try:
    from app import app
except Exception:
    import traceback
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    tb_str = traceback.format_exc()
    app = FastAPI(title="StudioGate Diagnostic")

    @app.get("/{full_path:path}")
    async def diagnostic(full_path: str):
        return HTMLResponse(
            f"<html><body style='background:#0d0a1a;color:#f43f5e;font-family:monospace;padding:2rem;'>"
            f"<h2>StudioGate Lambda Diagnostic Trace</h2>"
            f"<pre style='background:#1b132e;padding:1.5rem;border:1px solid #f43f5e;border-radius:8px;color:#fff;'>{tb_str}</pre>"
            f"<p style='color:#a78bfa;'><b>CWD:</b> {cwd}</p>"
            f"<p style='color:#a78bfa;'><b>sys.path:</b> {sys.path}</p>"
            f"</body></html>",
            status_code=500,
        )
