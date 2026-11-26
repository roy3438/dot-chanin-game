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
assert hashlib.sha256(raw).hexdigest() == "a1878add40627a28a75bb86d68de1626cc6e230b591669f9861c5a2723bae688"
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
log_path = folder / "reproduction.txt"
if sys.argv[1] == "offline":
    duplicate = "first\nsame\nsame\nlast\n"
    edit = {"start": 3, "end": 3, "anchor": "same", "replacement": "changed"}
    assert engine.apply_line_edits(duplicate, [edit]) == "first\nsame\nchanged\nlast\n"
    for invalid in ([dict(edit, anchor="wrong")], [edit, edit], [dict(edit, end=9)]):
        try:
            engine.apply_line_edits(duplicate, invalid)
        except engine.Stop:
            pass
        else:
            raise AssertionError("Invalid source edit accepted")
    passed, log = engine.run_qa(assets, dict(plan, dot_chain_regression=True, tests=[]))
    evidence = engine.failure_evidence(log)
    assert not passed and evidence, log
    outcomes = evidence["terminal_cases"]
    assert [row["expected"]["phase"] for row in outcomes] == ["won", "lost"]
    mock = Mock()
    mock.ask.side_effect = [{"paths": ["script.js"]}, {"edits": []}]
    try:
        engine.repair_with_groq(mock, plan, scope, assets, [], log, baseline)
    except engine.Stop as error:
        assert "동일" in str(error)
    else:
        raise AssertionError("Unchanged repair accepted")
    assert mock.ask.call_args.args[1]["reproduction"]["terminal_cases"] == outcomes
    print("QA terminal outcomes", [(row["case"], row["observed"]) for row in outcomes], flush=True)
    log_path.write_text(log)
elif sys.argv[1] == "live":
    engine.GENERATION_LIMITS["api.groq.com"] = 4
    try:
        fixed = engine.repair_with_groq(engine.Groq(), plan, scope, assets, [], log_path.read_text(), baseline)
    finally:
        print("Physical Groq requests:", engine.generation_counts["api.groq.com"], flush=True)
    output = folder / "result"
    engine.Checkpoint(output, candidate["identity"]).save(fixed, scope, len(plan["steps"]), 2, [])
    passed, log = engine.run_qa(fixed, full)
    print("Full QA", passed, log, flush=True)
    (output / "qa.log").write_text(log)
    if not passed:
        raise SystemExit("Full QA failed; no further model calls")
else:
    raise ValueError("Unknown phase")
