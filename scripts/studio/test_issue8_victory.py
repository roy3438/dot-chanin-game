"""Run the two victory-dialog checks on desktop and touch Chromium."""
import functools
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright
from browser import Handler, VIEWPORTS, drag

ROOT = Path(__file__).resolve().parents[2]


def check(page, origin, touch):
    page.goto(origin)
    page.evaluate("""() => localStorage.setItem('dot-chain-v1', JSON.stringify({
        board: Array(36).fill('red'), moves: 1, score: 1980, best: 1980,
        level: 1, unlocked: 1, mission: null, phase: 'playing'
    }))""")
    page.reload()
    drag(page, page.locator(".cell").nth(0), page.locator(".cell").nth(1), touch)
    dialog = page.get_by_role("dialog")
    dialog.get_by_text("승리!", exact=True).wait_for()
    for stage in ("win", "reload"):
        if stage == "reload":
            page.reload()
            dialog.wait_for()
        unlocked = page.evaluate("JSON.parse(localStorage.getItem('dot-chain-v1')).unlocked")
        preview = dialog.get_by_text("다음 미션", exact=False).filter(has_text="5개").is_visible()
        button = dialog.locator("#next-level").is_visible()
        yield stage, unlocked, preview, button


if __name__ == "__main__":
    failures = []
    handler = functools.partial(Handler, directory=str(ROOT))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server, sync_playwright() as playwright:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        browser = playwright.chromium.launch()
        for device, viewport, touch in VIEWPORTS:
            page = browser.new_page(viewport=viewport, has_touch=touch, is_mobile=touch)
            for stage, unlocked, preview, button in check(page, f"http://127.0.0.1:{server.server_port}", touch):
                print(device, stage, f"unlocked={unlocked} preview={preview} button={button}", flush=True)
                if unlocked != 2 or not preview or not button:
                    failures.append((device, stage))
            page.close()
        browser.close()
    if failures:
        raise SystemExit(f"Victory checks failed: {failures}")
