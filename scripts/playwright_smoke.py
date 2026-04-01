from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import suppress
from pathlib import Path

from playwright.sync_api import sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a lightweight Playwright smoke check against the local app."
    )
    parser.add_argument("--base-url", help="Existing app base URL. Defaults to a local uvicorn server when --serve is used.")
    parser.add_argument("--serve", action="store_true", help="Start a temporary local uvicorn server for the smoke check.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the temporary server to.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind the temporary server to.")
    parser.add_argument("--path", default="/", help="Path to visit after the app is available.")
    parser.add_argument("--wait-for", action="append", default=[], dest="wait_for", help="Selector to wait for after navigation or actions.")
    parser.add_argument("--click", action="append", default=[], help="Selector to click. May be passed multiple times.")
    parser.add_argument(
        "--fill",
        action="append",
        default=[],
        help="Fill action in the form '<selector>=<value>'. May be passed multiple times.",
    )
    parser.add_argument("--timeout-ms", type=int, default=10000, help="Navigation and selector timeout in milliseconds.")
    parser.add_argument("--wait-ms", type=int, default=250, help="Extra settle time after actions in milliseconds.")
    parser.add_argument("--headed", action="store_true", help="Run Chromium headed instead of headless.")
    parser.add_argument("--screenshot", help="Optional path to save a screenshot.")
    return parser.parse_args()


def wait_for_server(base_url: str, timeout_seconds: float = 15.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url, timeout=1.0) as response:
                if response.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            last_error = error
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for server at {base_url!r}") from last_error


def start_server(host: str, port: int) -> subprocess.Popen[str]:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)


def stop_server(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    with suppress(ProcessLookupError):
        process.terminate()
    with suppress(subprocess.TimeoutExpired):
        process.wait(timeout=3)
        return
    with suppress(ProcessLookupError):
        process.kill()
    with suppress(subprocess.TimeoutExpired):
        process.wait(timeout=3)


def parse_fill_action(action: str) -> tuple[str, str]:
    selector, separator, value = action.partition("=")
    if not separator or not selector.strip():
        raise ValueError(f"Invalid --fill value {action!r}; expected '<selector>=<value>'")
    return selector.strip(), value


def main() -> int:
    args = parse_args()
    base_url = args.base_url
    server_process: subprocess.Popen[str] | None = None

    if args.serve:
        if base_url:
            raise ValueError("Use either --serve or --base-url, not both.")
        base_url = f"http://{args.host}:{args.port}"
        server_process = start_server(args.host, args.port)
        wait_for_server(base_url)
    elif not base_url:
        raise ValueError("Provide --base-url or use --serve.")

    target_url = f"{base_url.rstrip('/')}{args.path}"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headed)
            page = browser.new_page(viewport={"width": 1440, "height": 1024})
            page.set_default_timeout(args.timeout_ms)
            page.goto(target_url, wait_until="networkidle")

            for selector in args.wait_for:
                page.wait_for_selector(selector)

            for action in args.fill:
                selector, value = parse_fill_action(action)
                page.locator(selector).fill(value)

            for selector in args.click:
                page.locator(selector).click()

            if args.fill or args.click:
                page.wait_for_timeout(args.wait_ms)
                for selector in args.wait_for:
                    page.wait_for_selector(selector)

            if args.screenshot:
                screenshot_path = Path(args.screenshot)
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot_path), full_page=True)

            print(f"URL: {page.url}")
            print(f"Title: {page.title()}")
            browser.close()
    finally:
        stop_server(server_process)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
