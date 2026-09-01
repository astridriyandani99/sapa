import os
import sys
import time
import webbrowser
import threading
import uvicorn

# Pastikan current working directory ada di sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.importer import auto_seed_local_files

def open_browser():
    time.sleep(1.5)
    url = "http://localhost:8000"
    print(f"\n[SIHA Dashboard] Membuka antarmuka di browser: {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass

if __name__ == "__main__":
    print("=" * 65)
    print("   SIHA & SIMRS CLINICAL & RESEARCH INTELLIGENCE DASHBOARD")
    print("=" * 65)
    print("[1/2] Memeriksa database & file lokal...")
    auto_seed_local_files()
    
    print("[2/2] Memulai server aplikasi FastAPI...")
    print("      Akses Dashboard: http://localhost:8000")
    print("      Atau melalui IP: http://127.0.0.1:8000")
    print("=" * 65)
    
    threading.Thread(target=open_browser, daemon=True).start()
    
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
