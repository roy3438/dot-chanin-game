"""One-time acceptance trial for the saved issue 8 candidate."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock

import engine

folder = Path(os.environ["RUNNER_TEMP"]) / "issue8"
raw = (folder / "candidate.json").read_bytes()
candidate = json.loads(raw)
assert candidate["identity"] == [8, 7091498356, "7091487940", "11dd8fc11bd74e6e28b92ae83bc1e879f3fcc86b"]
plan_comment = json.loads((folder / "plan-comment.json").read_text())
assert plan_comment["id"] == 7091487940 and plan_comment["user"]["login"] == engine.BOT
envelope = json.loads(base64.b64decode(plan_comment["body"].split("\n    studio-data ")[-1], validate=True))
inventory, baseline = engine.snapshot()
plan = envelope["plan"]
engine.validate_task_plan(plan, inventory, envelope["task"])
scope = {key: op for step in plan["steps"] for key, op in step["files"].items()}
assets = engine.apply_file_response({"files": candidate["state"]["files"]}, scope, baseline, True)
full = dict(plan, dot_chain_regression=True, tests=[*plan["tests"], engine.level_two_negative(plan)])
if sys.argv[1:] != ["acceptance"]:
    raise SystemExit("Expected acceptance replay")

payload = json.loads((folder / "rejected.json").read_text())
assert payload["identity"] == candidate["identity"]
assert payload["state"]["files"] != candidate["state"]["files"]
output = folder / "result"
checkpoint = engine.Checkpoint(output, candidate["identity"])
checkpoint.save(assets, scope, len(plan["steps"]), 0, [])
digest = lambda: hashlib.sha256(checkpoint.file.read_bytes()).hexdigest()
mock = Mock()
mock.ask.return_value = {"files": payload["state"]["files"]}
input_digest = None
runs = []
def replay(files, definition):
    global input_digest
    if runs:
        input_digest = digest()
        assert len(definition["tests"]) == 1
    passed, log = engine.run_qa(files, definition)
    evidence = engine.failure_evidence(log)
    assert not passed and evidence, log
    runs.append(evidence)
    return passed, log

try:
    engine.deploy_candidate(mock, plan, envelope["task"], baseline, replay, print, checkpoint=checkpoint)
except engine.Stop as error:
    assert "수정 기각" in str(error), str(error)
    print(error, flush=True)
else:
    raise AssertionError("Ineffective changes were accepted")
assert len(runs) == 2 and mock.ask.call_count == 1 and input_digest == digest()
for row in runs:
    assert row["expected"]["score"] == 2020 and row["observed"]["score"] == 1980
restored = engine.Checkpoint(output, candidate["identity"])
assert restored.state["files"] == candidate["state"]["files"] and restored.state["repairs"] == 0
assert restored.state["files"] != payload["state"]["files"]
print("Verified restored candidate file contents, rejected revision excluded. No provider requests.")
