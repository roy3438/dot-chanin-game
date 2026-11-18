from pathlib import Path

source = Path('inde' + chr(120) + '.html')
if not source.is_file():
    raise SystemExit('Game HTML not found')

original = source.read_text(encoding='utf-8')
old = 'if (pos === null) { cancelPath(); return; }'
new = 'if (pos === null) { void finishPath(); return; }'

if original.count(old) != 1:
    raise SystemExit('Safety stop: expected exactly one pointer release guard')

if "boardNode.addEventListener('pointerup'" not in original:
    raise SystemExit('Safety stop: pointerup handler missing')

updated = original.replace(old, new, 1)
source.write_text(updated, encoding='utf-8')
print('Changed only the out-of-board pointer release behavior.')
