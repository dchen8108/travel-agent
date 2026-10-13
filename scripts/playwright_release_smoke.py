from __future__ import annotations

import argparse
from contextlib import suppress

from playwright.sync_api import Page, sync_playwright

from playwright_smoke import start_server, stop_server, wait_for_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the production v1 and v2 browser surfaces.")
    parser.add_argument("--base-url", help="Use an existing server instead of starting a temporary one.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def _assert_no_horizontal_overflow(page: Page, *, label: str) -> None:
    dimensions = page.evaluate(
        """() => ({
          clientWidth: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
        })"""
    )
    if dimensions["scrollWidth"] > dimensions["clientWidth"] + 1:
        raise AssertionError(f"{label} has horizontal overflow: {dimensions}")


def _visit(page: Page, url: str, selector: str, *, label: str) -> None:
    page.goto(url, wait_until="networkidle")
    page.wait_for_selector(selector)
    _assert_no_horizontal_overflow(page, label=label)


def main() -> int:
    args = parse_args()
    base_url = args.base_url or f"http://{args.host}:{args.port}"
    server = None
    if not args.base_url:
        server = start_server(args.host, args.port)
        wait_for_server(base_url)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            desktop = browser.new_page(viewport={"width": 1440, "height": 1024})
            runtime_errors: list[str] = []
            desktop.on("pageerror", lambda error: runtime_errors.append(str(error)))
            desktop.on(
                "console",
                lambda message: runtime_errors.append(message.text) if message.type == "error" else None,
            )

            _visit(desktop, f"{base_url}/", ".dashboard-workbench", label="v1 desktop")
            v1_resources = desktop.evaluate(
                "performance.getEntriesByType('resource').map((entry) => entry.name)"
            )
            if any("V2Page" in resource for resource in v1_resources):
                raise AssertionError("v1 loaded v2 route assets")

            _visit(desktop, f"{base_url}/v2", ".v2-hero", label="v2 home desktop")
            v2_resources = desktop.evaluate(
                "performance.getEntriesByType('resource').map((entry) => entry.name)"
            )
            if not any("V2Page" in resource for resource in v2_resources):
                raise AssertionError("v2 route chunk was not loaded")

            for path, heading in (
                ("schedule", "Upcoming schedule"),
                ("inbox", "Only the work that needs you"),
                ("rules", "Recurring travel rules"),
            ):
                desktop.locator(f'.v2-nav a[href="/v2/{path}"]').click()
                desktop.wait_for_url(f"**/v2/{path}")
                desktop.get_by_role("heading", name=heading).wait_for()
                _assert_no_horizontal_overflow(desktop, label=f"v2 {path} desktop")

            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.on("pageerror", lambda error: runtime_errors.append(str(error)))
            mobile.on(
                "console",
                lambda message: runtime_errors.append(message.text) if message.type == "error" else None,
            )
            _visit(mobile, f"{base_url}/v2", ".v2-mobile-nav", label="v2 home mobile")
            mobile.locator('.v2-mobile-nav a[href="/v2/schedule"]').click()
            mobile.wait_for_url("**/v2/schedule")
            mobile.get_by_role("heading", name="Upcoming schedule").wait_for()
            _assert_no_horizontal_overflow(mobile, label="v2 schedule mobile")

            if runtime_errors:
                raise AssertionError(f"Browser runtime errors: {runtime_errors}")
            browser.close()
    finally:
        with suppress(Exception):
            stop_server(server)

    print("Browser release smoke passed for v1 and v2 at desktop and mobile widths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
