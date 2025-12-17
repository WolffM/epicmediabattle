"""
Server utility functions for the Arena application.
"""

import os
import subprocess
import sys


def kill_existing_server(port: int = 5000) -> bool:
    """Kill any existing process using the specified port."""
    if sys.platform == "win32":
        try:
            # Find PID using the port
            result = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True,
                text=True
            )

            for line in result.stdout.split("\n"):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != os.getpid():
                        print(f"Killing existing process on port {port} (PID: {pid})...")
                        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                        return True
        except Exception as e:
            print(f"Warning: Could not check for existing server: {e}")
    else:
        # Unix-like systems
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                for pid in result.stdout.strip().split("\n"):
                    if pid.isdigit() and int(pid) != os.getpid():
                        print(f"Killing existing process on port {port} (PID: {pid})...")
                        subprocess.run(["kill", "-9", pid], capture_output=True)
                        return True
        except Exception as e:
            print(f"Warning: Could not check for existing server: {e}")

    return False
