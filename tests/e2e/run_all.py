"""Run every browser test in order against the mock backend.

    cd frontend && npm run build && cd ..
    python tests/e2e/run_all.py

Starts mock_backend.py (port 5000) and proxy.py (port 5173), runs e2e1..e2e6 in order (later ones use what earlier
ones made), stops both and prints a summary. Screenshots go to tests/e2e/out (or $E2E_OUT).
"""
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = ["e2e1.py", "e2e2.py", "e2e3.py", "e2e4.py", "e2e5.py", "e2e6.py"]


def wait_up(url, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    if not os.path.exists(os.path.join(HERE, "..", "..", "frontend", "dist", "index.html")) and not os.environ.get("E2E_STATIC"):
        sys.exit("Build the frontend first: cd frontend && npm run build")
    procs = [subprocess.Popen([sys.executable, os.path.join(HERE, "mock_backend.py")], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT),
             subprocess.Popen([sys.executable, os.path.join(HERE, "proxy.py")], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)]
    failed = []
    try:
        if not wait_up("http://127.0.0.1:5173/api/backups"):
            sys.exit("The mock backend or the proxy did not start")
        for s in SCRIPTS:
            print(f"== {s}", flush=True)
            r = subprocess.run([sys.executable, os.path.join(HERE, s)], capture_output=True, text=True)
            out = r.stdout + r.stderr
            print("\n".join(l for l in out.splitlines() if l.startswith(("PASS", "FAIL", "FAILS"))))
            if r.returncode or "FAIL " in out or "Traceback" in out:
                failed.append(s)
                if "Traceback" in out:
                    print(out[-1500:])
    finally:
        for p in procs:
            p.terminate()
    print("\nALL PASSED" if not failed else f"\nFAILED: {', '.join(failed)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
