"""PR 6 QA pilot: guarded repair of duplicated static game values."""
import json
import os
import pathlib
import re
import subprocess
import urllib.request

repo = os.environ['REPOSITORY']
pr = os.environ['PR_NUMBER']
token = os.environ['GH_TOKEN']
body = os.environ['COMMENT_BODY']
comment_id = os.environ['COMMENT_ID']
api = 'https://api.github.com/repos/' + repo


def github(method, route, data=None):
    payload = None if data is None else json.dumps(data).encode('utf-8')
    req = urllib.request.Request(api + route, data=payload, method=method, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
        'User-Agent': 'ai-studio-qa-repair',
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def comment(message):
    github('POST', '/issues/' + pr + '/comments', {'body': message})


if pr != '6' or not body.startswith('[QA 수정 요청'):
    raise SystemExit('Pilot accepts only the authorized QA request on PR 6')

info = github('GET', '/pulls/' + pr)
owner = repo.split('/')[0].lower()
if info['base']['ref'] != 'main' or info['head']['repo']['full_name'].lower() != repo.lower():
    raise SystemExit('Unexpected PR base or head repository')
if not info['head']['ref'].startswith('ai/approved-'):
    raise SystemExit('Unexpected branch')

comments = github('GET', '/issues/' + pr + '/comments?per_page=100')
marker = '<!-- qa-repair-request:' + comment_id + ' -->'
if any(marker in item['body'] for item in comments):
    print('Already processed this QA request')
    raise SystemExit(0)

# This first pilot intentionally limits changes to two display labels.
# Never alter scoring, game logic, scripts, or the existing live counters.
path = pathlib.Path('index.html')
original = path.read_text(encoding='utf-8')
new = original
replacements = [
    (r'(<span>목표 점수)\s*\(2,000점\)(</span>)', r'\g<1>\g<2>'),
    (r'(<span>남은 이동)\s*\(20회\)(</span>)', r'\g<1>\g<2>'),
]
counts = []
for pattern, replacement in replacements:
    new, count = re.subn(pattern, replacement, new)
    counts.append(count)

if counts != [1, 1]:
    comment(marker + '\nQA 자동 수정 보류: 예상한 안내 문구 두 곳을 정확히 찾지 못했습니다. 변경 없음. 대표 검토 필요. 발견 수: ' + str(counts))
    raise SystemExit('Expected exact display labels not found')

path.write_text(new, encoding='utf-8')
# Verify only the two expected replacements occurred.
expected = original.replace('목표 점수(2,000점)', '목표 점수').replace('남은 이동 (20회)', '남은 이동')
if new != expected:
    path.write_text(original, encoding='utf-8')
    raise SystemExit('Unexpected change outside allowlist')

subprocess.run(['git', 'diff', '--check'], check=True)
subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
subprocess.run(['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'], check=True)
subprocess.run(['git', 'add', '--', 'index.html'], check=True)
subprocess.run(['git', 'commit', '-m', 'QA: remove duplicated static values from labels'], check=True)
subprocess.run(['git', 'push', 'origin', 'HEAD:' + info['head']['ref']], check=True)
comment(marker + '\nQA 자동 수정 완료: 중복된 목표 점수·이동 횟수 안내 문구만 제거했습니다. 기존 동적 수치 요소와 게임 로직은 변경하지 않았습니다. `git diff --check` 통과. 실제 브라우저 및 모바일 기능 검사는 수행하지 않았습니다. 대표 검토 전 병합 금지.')
