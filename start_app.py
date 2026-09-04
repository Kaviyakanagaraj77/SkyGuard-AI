"""
SkyGuard AI v2 - Unified Application Launcher
------------------------------------------------
Launches both the FastAPI backend server (Port 8000) and the web frontend (Port 8080),
then opens http://127.0.0.1:8080 in the default web browser.

Usage:
    python start_app.py
"""

import os
import sys
import subprocess
import time
import webbrowser
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")


def main():
    print("=" * 60)
    print(" 🌦️  SkyGuard AI v2 - Production Application Launcher")
    print(" SIH 2026 · Ministry of Earth Sciences (MoES) / IMD")
    print("=" * 60)

    # 1. Start FastAPI Backend Server
    print("\n[1/3] Launching FastAPI Backend Server on http://127.0.0.1:8000...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=BACKEND_DIR
    )

    # Wait for backend health check
    print("     Waiting for backend initialization...")
    backend_ready = False
    for attempt in range(15):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as resp:
                if resp.status == 200:
                    backend_ready = True
                    break
        except Exception:
            time.sleep(1)

    if backend_ready:
        print("     ✓ Backend API is ONLINE and HEALTHY!")
    else:
        print("     ⚠️ Backend start took longer than expected. Continuing...")

    # 2. Start Frontend HTTP Server
    print("\n[2/3] Launching Web Frontend Server on http://127.0.0.1:8080...")
    frontend_proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8080"],
        cwd=FRONTEND_DIR
    )
    time.sleep(1)
    print("     ✓ Frontend Web Application is ONLINE at http://127.0.0.1:8080")

    # 3. Open Browser
    print("\n[3/3] Opening SkyGuard AI Production Dashboard in Browser...")
    webbrowser.open("http://127.0.0.1:8080")

    print("\n" + "=" * 60)
    print(" 🚀 SkyGuard AI v2 is actively running!")
    print(" Press CTRL+C in this terminal to stop both servers.")
    print("=" * 60)

    try:
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping SkyGuard AI servers...")
        backend_proc.terminate()
        frontend_proc.terminate()
        print("Goodbye!")


if __name__ == "__main__":
    main()
