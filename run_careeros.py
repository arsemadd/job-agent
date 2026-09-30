"""CareerOS Main Launcher.

Starts the CareerOS FastAPI backend and serves the complete 10-module dashboard.
Usage:
    python run_careeros.py
"""
import os
import sys
import webbrowser
from datetime import datetime

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("CAREEROS_HOST", "127.0.0.1")
    port = int(os.environ.get("CAREEROS_PORT", "8000"))
    url = f"http://{host}:{port}"

    print("=" * 65)
    print(" 🚀 Starting CareerOS — Job Search Operating System")
    print(" Candidate: Arsema Doji Wordofa (Product Manager)")
    print(f" Dashboard: {url}")
    print(f" API Docs:  {url}/docs")
    print(f" Database:  data/careeros.db")
    print("=" * 65)

    # Automatically open in browser if not headless
    if "--no-browser" not in sys.argv:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run("backend.app:app", host=host, port=port, reload=True)
