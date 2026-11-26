"""Execute approved declarative test cases in a disposable offline browser."""
import functools
import http.server
import importlib.util
import json
from pathlib import Path
import sys
import threading
from urllib.parse import urlsplit

if Path("/qa-driver").is_dir():
    sys.path.insert(0, "/qa-driver")

try:
    from playwright.sync_api import TimeoutError as BrowserTimeout, expect, sync_playwright
except ImportError:
    print("STUDIO_QA_INFRA", file=sys.stderr, flush=True)
    raise

VIEWPORTS = (
    ("desktop", {"width": 1280, "height": 800}, False),
    ("mobile", {"width": 375, "height": 812}, True),
)


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def end_headers(self):
        self.send_header("Content-Security-Policy",
                         "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; "
                         "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
                         "form-action 'none'; object-src 'none'; base-uri 'self'; worker-src 'none'")
        super().end_headers()


def point(locator):
    expect(locator).to_be_visible(timeout=2500)
    box = locator.bounding_box()
    if not box:
        raise AssertionError("Drag target has no bounding box")
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def drag(page, source, target, touch):
    first = point(source)
    last = point(target)
    if not touch:
        page.mouse.move(*first)
        page.mouse.down()
        page.mouse.move(*last, steps=8)
        page.mouse.up()
        return
    session = page.context.new_cdp_session(page)
    try:
        session.send("Input.dispatchTouchEvent", {
            "type": "touchStart", "touchPoints": [{"x": first[0], "y": first[1]}],
        })
        for ratio in (0.25, 0.5, 0.75, 1):
            session.send("Input.dispatchTouchEvent", {
                "type": "touchMove", "touchPoints": [{
                    "x": first[0] + ratio * (last[0] - first[0]),
                    "y": first[1] + ratio * (last[1] - first[1]),
                }],
            })
        session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    finally:
        session.detach()


def execute(page, action, touch):
    kind = action["do"]
    item = page.locator(action["selector"]) if "selector" in action else None
    if kind == "visible":
        expect(item).to_be_visible(timeout=2500)
    elif kind == "text":
        expect(item).to_have_text(action["value"], timeout=2500)
    elif kind == "click":
        if touch:
            item.tap()
        else:
            item.click()
    elif kind == "drag":
        drag(page, item, page.locator(action["target"]), touch)
    elif kind == "key":
        page.keyboard.press(action["value"])
    elif kind == "playing-after-short-chain":
        page.wait_for_function("""() => {
            const state = JSON.parse(localStorage.getItem('dot-chain-v1'));
            return state && state.moves === 4 && state.score >= 2000 && state.phase === 'playing'
                && state.missionProgress?.longChain === false;
        }""", timeout=2500)
        expect(page.locator("#result")).to_be_hidden()
    elif kind == "reload":
        page.reload(wait_until="load")
    else:
        raise AssertionError("Invalid browser action")


def mission_observation(page):
    return page.evaluate("""() => {
        const s = JSON.parse(localStorage.getItem('dot-chain-v1')) || {};
        return {score:s.score, moves:s.moves, phase:s.phase, level:s.level,
                missionProgress:s.missionProgress, title:document.querySelector('#result-title')?.textContent};
    }""")


def run_case(browser, origin, entry, scenario, viewport, touch):
    context = browser.new_context(viewport=viewport, is_mobile=touch, has_touch=touch,
                                  service_workers="block", accept_downloads=False)
    problems = []

    def route_request(route):
        url = urlsplit(route.request.url)
        if f"{url.scheme}://{url.netloc}" == origin:
            route.continue_()
        else:
            problems.append("External network request blocked")
            route.abort()

    context.route("**/*", route_request)
    context.route_web_socket("**/*", lambda socket: socket.close())
    page = context.new_page()
    page.set_default_timeout(2500)
    page.on("pageerror", lambda error: problems.append(f"JavaScript: {error}"))
    page.on("response", lambda response: problems.append(f"HTTP {response.status}: {response.url}")
            if response.status >= 400 else None)
    try:
        if "seed" in scenario:
            setup = origin + "/__studio_seed__"
            page.route(setup, lambda route: route.fulfill(status=200, content_type="text/html", body="<!doctype html>"),
                       times=1)
            page.goto(setup, wait_until="load", timeout=5000)
            seed = {key: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
                    for key, value in scenario["seed"].items()}
            page.evaluate("(seed) => Object.entries(seed).forEach(([key, value]) => localStorage.setItem(key, value))",
                          seed)
        response = page.goto(origin + "/" + entry, wait_until="load", timeout=5000)
        assert response and response.ok, "Game entry point failed to load"
        assert page.title().strip(), "Page title is missing"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "Horizontal overflow"
        if touch:
            assert page.evaluate("Math.abs(innerWidth - screen.width) <= 2"), "Mobile viewport is missing"
        for index, action in enumerate(scenario["steps"], 1):
            try:
                execute(page, action, touch)
            except (AssertionError, BrowserTimeout) as error:
                if action["do"] == "playing-after-short-chain":
                    state = mission_observation(page)
                    initial = scenario["seed"]["dot-chain-v1"]
                    evidence = {"case": scenario["name"], "device": "mobile" if touch else "desktop",
                                "action": scenario["steps"][0], "seed": initial,
                                "expected": {"score": initial["score"] + 40, "moves": initial["moves"] - 1,
                                             "phase": "playing", "missionProgress": {"longChain": False}},
                                "observed": state}
                    print("STUDIO_EVIDENCE " + json.dumps(evidence, separators=(",", ":")), flush=True)
                raise AssertionError(f"Step {index} ({action['do']}): {error}") from None
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "Horizontal overflow"
        assert not problems, str(problems[:5])
        if scenario.get("capture_mission"):
            print("STUDIO_CONTROL " + json.dumps(mission_observation(page)), flush=True)
    finally:
        context.close()


def baseline_suite(browser, root, port, plan):
    path = Path("/dot_qa.py")
    if not path.exists():
        path = Path(__file__).resolve().parents[1] / "browser_qa.py"
    spec = importlib.util.spec_from_file_location("studio_dot_chain_baseline", path)
    suite = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(suite)
    except Exception:
        print("STUDIO_QA_INFRA", file=sys.stderr, flush=True)
        raise
    suite.ROOT = root
    suite.EVIDENCE = Path("/tmp/studio-dot-evidence")
    suite.PORT = port
    for device, viewport, touch in VIEWPORTS:
        try:
            suite.run_case(browser, device, viewport, touch, probe_only=plan.get("probe_only", False),
                           scenarios=plan["tests"], verify_fields=plan.get("verify_fields", []))
        except (AssertionError, BrowserTimeout) as error:
            raise AssertionError(f"STUDIO_QA_CASE_FAILURE {device} / 기존 DOT CHAIN 회귀 시험: {error}") from error


def run(root, plan):
    handler = functools.partial(Handler, directory=str(root))
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        port = server.server_port
        origin = f"http://127.0.0.1:{port}"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser_path = None
                if not Path("/qa-driver").is_dir() and Path("/usr/bin/chromium").is_file():
                    browser_path = "/usr/bin/chromium"
                try:
                    browser = playwright.chromium.launch(headless=True, executable_path=browser_path)
                except Exception:
                    print("STUDIO_QA_INFRA", file=sys.stderr, flush=True)
                    raise
                try:
                    if plan["dot_chain_regression"]:
                        baseline_suite(browser, root, port, plan)
                    failures = []
                    for device, viewport, touch in VIEWPORTS:
                        for scenario in ([] if plan.get("probe_only") else plan["tests"]):
                            label = f"{device} / {scenario['name']}"
                            try:
                                run_case(browser, origin, plan["entry"], scenario, viewport, touch)
                                print(f"PASS {label}", flush=True)
                            except (AssertionError, BrowserTimeout) as error:
                                failures.append(f"FAIL {label}: {str(error)[:500]}")
                    if failures:
                        raise AssertionError("\n".join(failures) + "\nSTUDIO_QA_CASE_FAILURE")
                finally:
                    browser.close()
        finally:
            server.shutdown()
    print("\nSTUDIO_QA_PASS", flush=True)


if __name__ == "__main__":
    run(Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
