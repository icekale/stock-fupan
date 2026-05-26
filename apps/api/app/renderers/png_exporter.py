from pathlib import Path

from playwright.sync_api import sync_playwright


def export_png(html_path: Path, output_path: Path, width: int = 720) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": 1280}, device_scale_factor=2)
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            page.screenshot(path=str(output_path), full_page=True)
        finally:
            browser.close()
