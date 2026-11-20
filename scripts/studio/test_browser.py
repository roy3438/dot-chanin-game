"""Browser regression for seeding once and isolating scenarios."""
from pathlib import Path
from tempfile import TemporaryDirectory

from browser import run


PAGE = """<!doctype html>
<html lang="en">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Storage test</title>
<button id="next">Next</button><output id="level"></output>
<script>
const level = document.getElementById('level');
const read = () => JSON.parse(localStorage.getItem('progress') || '{"level":1}');
const show = () => { level.textContent = read().level; };
document.getElementById('next').addEventListener('click', () => {
    localStorage.setItem('progress', JSON.stringify({level: read().level + 1}));
    show();
});
show();
</script>
</html>"""


def level_is(value):
    return {"do": "text", "selector": "#level", "value": str(value)}


if __name__ == "__main__":
    advance = {"do": "click", "selector": "#next"}
    cases = [
        {"name": "Seed once, then preserve actual progress",
         "seed": {"progress": {"level": 40}},
         "steps": [level_is(40), advance, level_is(41), {"do": "reload"}, level_is(41)]},
        {"name": "Next scenario starts with fresh storage",
         "steps": [level_is(1), advance, level_is(2)]},
    ]
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "index.html").write_text(PAGE, encoding="utf-8")
        run(root, {"entry": "index.html", "dot_chain_regression": False, "tests": cases})
