
"""PR 6 QA pilot: guarded repair of duplicated static game values."""

import json
import os
import pathlib
import re
import subprocess
import urllib.request

repo = os.environ["REPOSITORY"]
pr = os.environ["PR_NUMBER"]
token = os.environ["GH_TOKEN"]
body = os.environ["COMMENT_BODY"]
comment_id = os.environ["COMMENT_ID"]

api = "https://api.github.com/repos/" + repo


def github(method, route, data=None):
    payload = None

    if data is not None:
        payload = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(
        api + route,
        data=payload,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "ai-studio-qa-repair",
        },
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def comment(message):
    github(
        "POST",
        "/issues/" + pr + "/comments",
        {"body": message},
    )


def run(*args):
    subprocess.run(list(args), check=True)


# --------------------------------------------------
# 1. Validate authorized request
# --------------------------------------------------

if pr != "6" or not body.startswith("[QA 수정 요청"):
    raise SystemExit(
        "Pilot accepts only the authorized QA request on PR 6"
    )

info = github("GET", "/pulls/" + pr)

if info["state"] != "open":
    raise SystemExit("PR is not open")

if info["base"]["ref"] != "main":
    raise SystemExit("Unexpected base branch")

if info["head"]["repo"]["full_name"].lower() != repo.lower():
    raise SystemExit("Unexpected head repository")

branch = info["head"]["ref"]

if not branch.startswith("ai/approved-"):
    raise SystemExit("Unexpected development branch")


# --------------------------------------------------
# 2. Prevent duplicate processing
# --------------------------------------------------

marker = "<!-- qa-repair-request:" + comment_id + " -->"

comments = github(
    "GET",
    "/issues/" + pr + "/comments?per_page=100",
)

if any(marker in item.get("body", "") for item in comments):
    print("Already processed this QA request")
    raise SystemExit(0)


# --------------------------------------------------
# 3. Read game source
# --------------------------------------------------

path = pathlib.Path("index.html")

if not path.is_file():
    raise SystemExit("Game source not found")

original = path.read_text(encoding="utf-8")


# --------------------------------------------------
# 4. Define strictly allowed changes
# --------------------------------------------------

replacements = [
    (
        r"(<span>목표 점수)\s*\(2,000점\)(</span>)",
        r"\g<1>\g<2>",
    ),
    (
        r"(<span>남은 이동)\s*\(20회\)(</span>)",
        r"\g<1>\g<2>",
    ),
]


# --------------------------------------------------
# 5. Apply guarded repair
# --------------------------------------------------

new = original
counts = []

for pattern, replacement in replacements:
    new, count = re.subn(
        pattern,
        replacement,
        new,
    )
    counts.append(count)

if counts != [1, 1]:
    comment(
        marker
        + "\nQA 자동 수정 보류: "
        + "예상한 안내 문구 두 곳을 정확히 찾지 못했습니다. "
        + "변경 없음. 대표 검토 필요. "
        + "발견 수: "
        + str(counts)
    )

    raise SystemExit(
        "Expected exact display labels not found"
    )


# --------------------------------------------------
# 6. Verify the allowed result
# --------------------------------------------------

expected = original

for pattern, replacement in replacements:
    expected = re.sub(
        pattern,
        replacement,
        expected,
    )

if new != expected:
    raise SystemExit(
        "Unexpected change outside allowlist"
    )

# Independently verify that only two span labels changed.
before_labels = re.findall(
    r"<span>[^<]*</span>",
    original,
)

after_labels = re.findall(
    r"<span>[^<]*</span>",
    new,
)

if len(before_labels) != len(after_labels):
    raise SystemExit(
        "Unexpected change in span element count"
    )

changed_labels = [
    (before, after)
    for before, after in zip(before_labels, after_labels)
    if before != after
]

allowed_pairs = [
    (
        "<span>목표 점수(2,000점)</span>",
        "<span>목표 점수</span>",
    ),
    (
        "<span>남은 이동 (20회)</span>",
        "<span>남은 이동</span>",
    ),
]

# The regular expressions also allow whitespace variations.
# Confirm the final labels and exact number of changes.
if len(changed_labels) != 2:
    raise SystemExit(
        "Unexpected number of changed labels"
    )

if [after for _, after in changed_labels] != [
    "<span>목표 점수</span>",
    "<span>남은 이동</span>",
]:
    raise SystemExit(
        "Unexpected resulting labels"
    )


# --------------------------------------------------
# 7. Write and validate changes
# --------------------------------------------------

path.write_text(new, encoding="utf-8")

try:
    run("git", "diff", "--check")

    changed_files = subprocess.check_output(
        ["git", "diff", "--name-only"],
        text=True,
    ).splitlines()

    if changed_files != ["index.html"]:
        raise RuntimeError(
            "Unexpected changed files: " + str(changed_files)
        )

except Exception:
    path.write_text(original, encoding="utf-8")
    raise


# --------------------------------------------------
# 8. Commit and push to the same PR branch
# --------------------------------------------------

run(
    "git",
    "config",
    "user.name",
    "github-actions[bot]",
)

run(
    "git",
    "config",
    "user.email",
    "41898282+github-actions[bot]@users.noreply.github.com",
)

run("git", "add", "--", "index.html")

run(
    "git",
    "commit",
    "-m",
    "QA: remove duplicated static values from labels",
)

run(
    "git",
    "push",
    "origin",
    "HEAD:" + branch,
)


# --------------------------------------------------
# 9. Report result
# --------------------------------------------------

comment(
    marker
    + "\nQA 자동 수정 완료: "
    + "중복된 목표 점수·이동 횟수 안내 문구만 제거했습니다. "
    + "기존 동적 수치 요소와 게임 로직은 변경하지 않았습니다. "
    + "정적 변경 검사 통과. "
    + "실제 브라우저 및 모바일 기능 검사는 수행하지 않았습니다. "
    + "대표 검토 전 병합 금지."
)

print("QA repair completed successfully")
