"""ValueHunt Web UI — точка входа для локального запуска."""
import os
import signal
import socket
import subprocess
import sys
import time

import uvicorn
from src.db import init_db
from src.web.app import app

PORT = 8100
BACKUP_SCRIPT = os.path.join(os.path.dirname(__file__), "scripts", "backup.py")


def free_port(port: int):
    """Kill any process listening on the given port (Windows)."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, shell=True
        )
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                try:
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True, timeout=5)
                    print(f"Killed old process PID {pid} on port {port}")
                    time.sleep(1)
                except Exception:
                    pass
    except Exception:
        pass


def run_backup():
    """Auto-backup БД при запуске сервера."""
    if not os.path.exists(BACKUP_SCRIPT):
        print("backup.py not found, skipping...")
        return
    print("Running auto-backup...")
    subprocess.run([sys.executable, BACKUP_SCRIPT], capture_output=False)


if __name__ == "__main__":
    free_port(PORT)
    time.sleep(0.5)
    init_db()
    run_backup()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
