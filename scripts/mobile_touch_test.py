from pathlib import Path
import re
import subprocess
import tempfile

source = Path('inde' + chr(120) + '.html').read_text(encoding='utf-8')
assert 'if (pos === null) { void finishPath(); return; }' in source
assert 'if (pos === null) { cancelPath(); return; }' not in source
assert "boardNode.addEventListener('pointercancel'" in source
assert "boardNode.addEventListener('lostpointercapture'" in source
assert 'const GOAL = 2000;' in source
assert 'const START_MOVES = 20;' in source
assert 'const SIDE = 6;' in source
assert 'const base = 10 * chosen.length * chosen.length;' in source
scripts = re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', source, flags=re.S | re.I)
assert len(scripts) == 1, 'Expected one inline game script'
with tempfile.TemporaryDirectory() as temp:
    script = Path(temp) / 'game.js'
    script.write_text(scripts[0], encoding='utf-8')
    subprocess.run(['node', '--check', str(script)], check=True)
print('PASS: source invariants and JavaScript syntax')
print('NOTE: browser touch behavior is NOT verified by this test.')
