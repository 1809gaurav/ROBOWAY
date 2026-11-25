#!/usr/bin/env python3
"""Playwright browser checks for the ROBOWAY dashboard and phone monitor."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
API = "http://127.0.0.1:8000"
FRONTEND = "http://localhost:5173"
PID_FILE = ROOT / "logs" / "pids.json"
CHECKS: list[tuple[str, str, str]] = []
LAST_HTTP_ERROR = ""


def record(name: str, outcome: str, details: str = "") -> None:
    CHECKS.append((name, outcome, details))


def wait_http(url: str, timeout: float) -> bool:
    global LAST_HTTP_ERROR
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if requests.get(url, timeout=1).ok:
                return True
        except requests.RequestException as exc:
            LAST_HTTP_ERROR = str(exc)
        time.sleep(0.25)
    return False


def tcp_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def read_pids() -> dict:
    if not PID_FILE.exists():
        raise RuntimeError("logs/pids.json not found; launch the system with .\\start_all.ps1 first")
    return json.loads(PID_FILE.read_text(encoding="utf-8-sig"))


def terminate_backend(pid: int) -> None:
    if os.name != "nt":
        os.kill(pid, signal.SIGTERM)
        return
    command = f"""
function Stop-BackendTree([int]$ProcessId) {{
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {{ Stop-BackendTree ([int]$child.ProcessId) }}
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {{
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop
    }}
}}
Stop-BackendTree {pid}
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not stop backend process tree {pid}: {result.stderr.strip()}")


def powershell_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def restart_backend() -> int:
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    log = ROOT / "logs" / "backend-restart.log"
    if os.name == "nt":
        error_log = ROOT / "logs" / "backend-restart-error.log"
        command = (
            f"$process = Start-Process -FilePath {powershell_quote(python)} "
            "-ArgumentList @('-u','run_server.py','--host','0.0.0.0','--port','8000') "
            f"-WorkingDirectory {powershell_quote(ROOT)} "
            f"-RedirectStandardOutput {powershell_quote(log)} "
            f"-RedirectStandardError {powershell_quote(error_log)} -PassThru; $process.Id"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip().isdigit():
            raise RuntimeError(f"Could not restart backend: {result.stderr.strip() or result.stdout.strip()}")
        process_pid = int(result.stdout.strip())
    else:
        with log.open("w", encoding="utf-8") as output:
            process = subprocess.Popen(
                [str(python), "-u", "run_server.py", "--host", "0.0.0.0", "--port", "8000"],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        process_pid = process.pid
    pids = read_pids()
    pids["backend"] = process_pid
    PID_FILE.write_text(json.dumps(pids, indent=2), encoding="utf-8")
    return process_pid


def print_results() -> None:
    width = max((len(name) for name, _, _ in CHECKS), default=8)
    print(f"\n{'CHECK':<{width}}  RESULT  DETAILS")
    print(f"{'-' * width}  ------  -------")
    for name, status, details in CHECKS:
        print(f"{name:<{width}}  {status:<6}  {details}")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: Playwright is not installed. Optional browser check: .\\.venv\\Scripts\\python.exe -m pip install playwright; .\\.venv\\Scripts\\python.exe -m playwright install chromium")
        record("Playwright browser checks", "SKIP", "Install playwright and Chromium to enable")
        print_results()
        return 0

    ARTIFACTS.mkdir(exist_ok=True)
    if not wait_http(f"{API}/health", 3) or not wait_http(FRONTEND, 3):
        record("Browser test prerequisites", "FAIL", "Start backend and frontend with .\\start_all.ps1")
        print_results()
        return 1

    with sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            print("SKIP: Playwright is installed but Chromium is missing. Optional install: .\\.venv\\Scripts\\python.exe -m playwright install chromium")
            record("Playwright browser checks", "SKIP", "Chromium browser binary is not installed")
            print_results()
            return 0
        browser = playwright.chromium.launch(headless=True)
        console_errors: list[str] = []
        desktop = browser.new_page(viewport={"width": 1366, "height": 768})
        desktop.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        desktop.on("pageerror", lambda error: console_errors.append(str(error)))

        try:
            desktop.goto(FRONTEND, wait_until="networkidle", timeout=20000)
            desktop.get_by_role("button", name="Simulator", exact=True).click()
            desktop.locator("canvas").first.wait_for(timeout=10000)
            record("Desktop simulator + canvas", "PASS")
            desktop.screenshot(path=str(ARTIFACTS / "desktop-simulator.png"), full_page=True)

            scenario = desktop.get_by_label("Scenario")
            scenario.select_option("failed_robot")
            desktop.get_by_role("button", name="Load scenario").click()
            desktop.get_by_role("button", name="Run simulation").click()
            before_text = desktop.locator(".sim-stat").filter(has_text="SIM TICK").locator("strong").inner_text()
            desktop.wait_for_timeout(5500)
            after_text = desktop.locator(".sim-stat").filter(has_text="SIM TICK").locator("strong").inner_text()
            if int(after_text) <= int(before_text):
                raise AssertionError(f"simulation tick did not advance ({before_text} -> {after_text})")
            if desktop.locator(".fleet-row").count() == 0:
                raise AssertionError("robot fleet list is empty")
            record("Desktop live simulation tick + robot list", "PASS")

            desktop.get_by_label("Pickup").select_option("P1")
            desktop.get_by_label("Drop").select_option("D1")
            desktop.get_by_role("button", name="Add job").click()
            desktop.locator(".jobs-panel .job-list").get_by_text("J7", exact=True).wait_for(timeout=8000)
            record("Desktop add job through UI", "PASS")

            desktop.get_by_label("Robot").select_option("R4")
            desktop.get_by_role("button", name="Fail robot").click()
            desktop.locator(".fleet-list").get_by_text("failed", exact=False).wait_for(timeout=8000)
            record("Desktop fail robot through UI", "PASS")
            desktop.screenshot(path=str(ARTIFACTS / "desktop-failure.png"), full_page=True)
            if console_errors:
                raise AssertionError("console errors: " + "; ".join(console_errors[:5]))
            record("Desktop browser console", "PASS")
        except Exception as exc:
            record("Desktop interaction checks", "FAIL", str(exc))
            desktop.screenshot(path=str(ARTIFACTS / "desktop-failure.png"), full_page=True)

        mobile = browser.new_page(**playwright.devices["iPhone 12"])
        mobile_errors: list[str] = []
        mobile.on("console", lambda message: mobile_errors.append(message.text) if message.type == "error" else None)
        mobile.on("pageerror", lambda error: mobile_errors.append(str(error)))
        try:
            mobile.goto(f"{FRONTEND}/monitor?api=http://localhost:8000", wait_until="networkidle", timeout=20000)
            mobile.locator(".monitor-connection").get_by_text("Live", exact=True).wait_for(timeout=10000)
            mobile.locator("canvas").first.wait_for(timeout=10000)
            record("Mobile live banner + 2D/3D canvas", "PASS")
            mobile.screenshot(path=str(ARTIFACTS / "mobile-monitor.png"), full_page=True)
            first_robot = mobile.locator(".monitor-list-row").first
            robot_id = first_robot.locator("strong").inner_text()
            first_robot.click()
            mobile.locator(".monitor-follow-chip").get_by_text(f"Follow {robot_id}", exact=False).wait_for(timeout=5000)
            record("Mobile robot follow selection", "PASS")

            mobile.evaluate("""() => {
              const canvas = document.querySelector('canvas');
              const makeTouch = (identifier, clientX, clientY) => new Touch({identifier, target: canvas, clientX, clientY});
              const send = (type, touches, changedTouches) => canvas.dispatchEvent(new TouchEvent(type, {bubbles:true, cancelable:true, touches, targetTouches:touches, changedTouches}));
              const a = makeTouch(1, 80, 120), b = makeTouch(2, 170, 120);
              send('touchstart', [a, b], [a, b]);
              send('touchmove', [makeTouch(1, 65, 130), makeTouch(2, 195, 130)], [makeTouch(1, 65, 130), makeTouch(2, 195, 130)]);
              send('touchend', [], [a, b]);
            }""")
            horizontal_overflow = mobile.evaluate("document.documentElement.scrollWidth > window.innerWidth")
            if horizontal_overflow:
                raise AssertionError("mobile page has horizontal overflow")
            if mobile_errors:
                raise AssertionError("mobile console errors: " + "; ".join(mobile_errors[:5]))
            record("Mobile pinch/drag + no horizontal scroll", "PASS")
        except Exception as exc:
            record("Mobile monitor interaction checks", "FAIL", str(exc))
            mobile.screenshot(path=str(ARTIFACTS / "mobile-failure.png"), full_page=True)

        try:
            backend_pid = int(read_pids()["backend"])
            terminate_backend(backend_pid)
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline and tcp_port_open("127.0.0.1", 8000):
                time.sleep(0.2)
            if tcp_port_open("127.0.0.1", 8000):
                raise AssertionError("backend TCP listener remained open after stopping its recorded process tree")
            mobile.locator(".monitor-connection").get_by_text("Disconnected, retrying...", exact=True).wait_for(timeout=6000)
            record("Backend disconnect banner", "PASS")

            new_pid = restart_backend()
            if not wait_http(f"{API}/health", 10):
                restart_log = ROOT / "logs" / "backend-restart.log"
                tail = restart_log.read_text(encoding="utf-8", errors="replace").splitlines()[-12:] if restart_log.exists() else []
                process_status = "unknown"
                if os.name == "nt":
                    process_status = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", f"Get-Process -Id {new_pid} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
                        capture_output=True,
                        text=True,
                        check=False,
                    ).stdout.strip() or "not running"
                raise AssertionError(
                    f"restarted backend PID {new_pid} (after terminating {backend_pid}) did not become healthy within 10 seconds "
                    f"(process lookup: {process_status}); last probe: {LAST_HTTP_ERROR}; restart log tail: {' | '.join(tail)}"
                )
            mobile.locator(".monitor-connection").get_by_text("Live", exact=True).wait_for(timeout=10000)
            record("Backend restart reconnect", "PASS")
        except Exception as exc:
            record("Backend kill-and-restart", "FAIL", str(exc))

        browser.close()

    print_results()
    return 1 if any(status == "FAIL" for _, status, _ in CHECKS) else 0


if __name__ == "__main__":
    sys.exit(main())
