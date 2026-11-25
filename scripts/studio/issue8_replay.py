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
assert hashlib.sha256(raw).hexdigest() == "50290577c818e2466c8aa198d55290ac3c52371a3203b1956969b990113cd0ba"
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
probe = dict(plan, dot_chain_regression=True, probe_only=True, tests=[])
log_path = folder / "reproduction.txt"
if sys.argv[1] == "offline":
    passed, log = engine.run_qa(assets, probe)
    evidence = engine.failure_evidence(log)
    assert not passed and evidence and "level" not in evidence["seed"], log
    assert evidence["observed"]["score"] == 0 and evidence["observed"]["moves"] == 19
    assert evidence["expected"] == {"score": 40, "moves": 19}
    mock = Mock()
    mock.ask.side_effect = [{"paths": ["script.js"]}, {"edits": []}]
    try:
        engine.repair_with_groq(mock, plan, scope, assets, [], log, baseline)
    except engine.Stop as error:
        assert "동일" in str(error)
    else:
        raise AssertionError("Unchanged repair accepted")
    payload = mock.ask.call_args.args[1]
    assert payload["reproduction"] == evidence
    assert any("10 * chosen.length * chosen.length" in item["source"] for item in payload["original_reference"])
    assert mock.ask.call_count == 2
    log_path.write_text(log)
    print("Offline gate passed: observed 0 points / 19 moves, original rule supplied, unchanged repair rejected")
elif sys.argv[1] == "live":
    engine.GENERATION_LIMITS["api.groq.com"] = 4
    try:
        fixed = engine.repair_with_groq(engine.Groq(), plan, scope, assets, [], log_path.read_text(), baseline)
    finally:
        print("Physical Groq requests:", engine.generation_counts["api.groq.com"], flush=True)
    output = folder / "result"
    output.mkdir()
    engine.Checkpoint(output, candidate["identity"]).save(fixed, scope, len(plan["steps"]), 2, [])
    passed, log = engine.run_qa(fixed, probe)
    print("Focused QA", passed, log[-4000:], flush=True)
    if not passed:
        raise SystemExit("Focused QA failed; no further model calls")
    full = dict(plan, dot_chain_regression=True, tests=[*plan["tests"], engine.level_two_negative(plan)])
    passed, log = engine.run_qa(fixed, full)
    print("Full QA", passed, log[-4000:], flush=True)
    if not passed:
        raise SystemExit("Full QA failed; no further model calls")
else:
    raise ValueError("Unknown phase")
