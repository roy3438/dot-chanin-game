"""DOT CHAIN real-browser regression checks for a PR candidate."""
import functools
import http.server
import json
import pathlib
import threading
import traceback
from playwright.sync_api import TimeoutError as BrowserTimeout, sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "qa-evidence"
KEY = "dot-chain-v1"
PORT = 8765

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

def board_data():
    # The first two adjacent dots are always red; the rest are valid colors.
    colors = ["blue", "yellow", "green", "red"]
    board = [colors[(row + col) % 4] for row in range(6) for col in range(6)]
    board[0] = "red"
    board[1] = "red"
    return board

def saved_state(score=0, moves=20):
    return {
        "board": board_data(), "score": score, "moves": moves,
        "mission": None, "best": score, "phase": "playing",
    }

def put_state(page, data):
    page.goto(f"http://127.0.0.1:{PORT}/index.html")
    page.evaluate(
        "([key, value]) => localStorage.setItem(key, JSON.stringify(value))",
        [KEY, data],
    )
    page.reload()
    page.locator(".cell").first.wait_for()

def read_state(page):
    return page.evaluate(
        "key => JSON.parse(localStorage.getItem(key))", KEY
    )

def gesture(page):
    previous_moves = read_state(page)["moves"]
    first = page.locator(".cell").nth(0).bounding_box()
    second = page.locator(".cell").nth(1).bounding_box()
    assert first and second, "Missing board cells"
    a = (first["x"] + first["width"]/2, first["y"] + first["height"]/2)
    b = (second["x"] + second["width"]/2, second["y"] + second["height"]/2)
    page.mouse.move(*a)
    page.mouse.down()
    page.mouse.move(*b, steps=5)
    page.mouse.up()
    page.wait_for_function(
        "([key, previous]) => JSON.parse(localStorage.getItem(key)).moves === previous - 1",
        arg=[KEY, previous_moves], timeout=5000
    )

def comparison_inputs(seed, scenarios, storage_key):
    """Use the nearest approved saved state and vary one previously absent field."""
    candidates = []
    for test in scenarios:
        value = test.get("seed", {}).get(storage_key)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                continue
        if not isinstance(value, dict) or not seed.keys() <= value.keys():
            continue
        additions = {key: item for key, item in value.items() if key not in seed}
        if additions:
            distance = sum(seed[key] != value[key] for key in seed)
            candidates.append((distance, additions, test["name"]))
    if not candidates:
        return []
    _, additions, source = min(candidates, key=lambda item: item[0])
    return [(key, value, source) for key, value in sorted(additions.items())[:6]]


def compare_inputs(browser, viewport, touch, seed, expected, scenarios):
    results = []
    for key, value, source in comparison_inputs(seed, scenarios, KEY):
        context = browser.new_context(viewport=viewport, has_touch=touch, is_mobile=touch)
        try:
            page = context.new_page()
            page.set_default_timeout(4000)
            put_state(page, {**seed, key: value})
            gesture(page)
            state = read_state(page)
            results.append({"added": {key: value}, "approved_case": source,
                            "observed": {field: state.get(field) for field in expected}})
        except (AssertionError, BrowserTimeout) as error:
            results.append({"added": {key: value}, "approved_case": source, "error": str(error)[:180]})
        finally:
            context.close()
    return results


def run_case(browser, label, viewport, touch, probe_only=False, scenarios=(), verify_fields=()):
    context = browser.new_context(
        viewport=viewport, has_touch=touch, is_mobile=touch,
        device_scale_factor=1,
    )
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"http://127.0.0.1:{PORT}/index.html")
        assert page.title().startswith("DOT CHAIN")
        assert page.locator(".cell").count() == 36
        assert page.locator("#score").inner_text() == "0"
        assert page.locator("#moves").inner_text() == "20"
        assert page.locator("#mission-text").inner_text().strip()
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth + 1"
        ), "Horizontal overflow"

        # Seed a valid deterministic board to avoid random test outcomes.
        seed = saved_state()
        put_state(page, seed)
        gesture(page)
        state = read_state(page)
        observed = {key: state.get(key) for key in ("score", "moves", "phase", "level")}
        expected = {"score": 40, "moves": 19}
        failed = any(observed[key] != value for key, value in expected.items())
        if failed or verify_fields:
            comparisons = compare_inputs(browser, viewport, touch, seed, expected, scenarios)
            evidence = {"case": "two_adjacent_dots", "device": label, "seed": seed,
                        "action": "drag cell 0 to adjacent cell 1", "expected": expected,
                        "observed": observed, "comparisons": comparisons}
            print("STUDIO_EVIDENCE " + json.dumps(evidence, ensure_ascii=False, separators=(",", ":")), flush=True)
            if failed:
                raise AssertionError(f"Expected {expected}, observed {observed}")
            for field in verify_fields:
                assert any(field in row["added"] and row.get("observed") == expected for row in comparisons), (
                    f"Comparative regression failed for {field}")
        if probe_only:
            print(f"PASS {label}: two adjacent dots, moves={state['moves']} score={state['score']}", flush=True)
            return
        assert state["moves"] == 19
        assert page.locator("#score").inner_text() == "40"
        assert page.locator("#moves").inner_text() == "19"
        assert page.locator(".cell").count() == 36

        page.reload()
        assert read_state(page)["score"] == 40
        assert page.locator("#moves").inner_text() == "19"

        page.locator("#new-game").click()
        assert read_state(page)["score"] == 0
        assert read_state(page)["moves"] == 20

        # A two-dot chain awards 40, crossing the 2,000-point win goal.
        put_state(page, saved_state(score=1980))
        gesture(page)
        assert read_state(page)["phase"] == "won"
        assert page.locator("#result").is_visible()
        assert page.locator("#result-title").inner_text() == "승리!"
        page.locator("#restart").click()
        assert read_state(page)["phase"] == "playing"

        # Exhaust the last move below the target.
        put_state(page, saved_state(score=0, moves=1))
        # Wait for move 1 -> 0 instead of the default gesture wait condition.
        first = page.locator(".cell").nth(0).bounding_box()
        second = page.locator(".cell").nth(1).bounding_box()
        a = (first["x"] + first["width"]/2, first["y"] + first["height"]/2)
        b = (second["x"] + second["width"]/2, second["y"] + second["height"]/2)
        page.mouse.move(*a)
        page.mouse.down()
        page.mouse.move(*b, steps=5)
        page.mouse.up()
        page.wait_for_function(
            "key => JSON.parse(localStorage.getItem(key)).moves === 0",
            arg=KEY, timeout=5000,
        )
        assert read_state(page)["phase"] == "lost"
        assert page.locator("#result-title").inner_text() == "패배"
        assert not errors, f"Browser JavaScript errors: {errors}"
        print(f"PASS: {label}")
    except Exception:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(EVIDENCE / f"{label}.png"), full_page=True)
        (EVIDENCE / f"{label}.txt").write_text(
            traceback.format_exc() + "\nBrowser errors:\n" + "\n".join(errors),
            encoding="utf-8",
        )
        raise
    finally:
        context.close()

def main():
    if not (ROOT / "index.html").is_file():
        raise SystemExit("index.html not found in repository root")
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                run_case(browser, "desktop", {"width": 1280, "height": 800}, False)
                run_case(browser, "mobile", {"width": 375, "height": 812}, True)
            finally:
                browser.close()
    finally:
        server.shutdown()

if __name__ == "__main__":
    main()
