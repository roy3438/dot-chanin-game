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
assert hashlib.sha256(raw).hexdigest() == "fca87510360931a0fb3bdee95473fc83c1bfd6b9c0aebfcfbf1864fb3af9f289"
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
probe = dict(plan, dot_chain_regression=True, probe_only=True)
log_path = folder / "reproduction.txt"
if sys.argv[1] == "offline":
    previous_raw = (folder / "previous" / "candidate.json").read_bytes()
    assert hashlib.sha256(previous_raw).hexdigest() == "35bf52383639ff03ac3153936a7e5cd198821735fef845fd68eb25d1abcccde2"
    prior = engine.apply_file_response({"files": json.loads(previous_raw)["state"]["files"]}, scope, baseline, True)
    prior_pass, prior_log = engine.run_qa(prior, probe)
    previous = engine.failure_evidence(prior_log)
    assert not prior_pass and previous["observed"]["score"] == 0
    (folder / "previous.json").write_text(json.dumps(previous))
    passed, log = engine.run_qa(assets, probe)
    evidence = engine.failure_evidence(log)
    assert not passed and evidence and "level" not in evidence["seed"], log
    assert evidence["observed"]["score"] == 80 and evidence["observed"]["moves"] == 19
    assert evidence["expected"] == {"score": 40, "moves": 19}
    mock = Mock()
    mock.ask.side_effect = [{"paths": ["script.js"]}, {"edits": []}]
    try:
        engine.repair_with_groq(mock, plan, scope, assets, [], log, baseline, previous)
    except engine.Stop as error:
        assert "동일" in str(error)
    else:
        raise AssertionError("Unchanged repair accepted")
    payload = mock.ask.call_args.args[1]
    assert payload["reproduction"] == evidence and payload["qa_assignment"]
    assert payload["remaining_mismatches"]["score"] == {"expected": 40, "previous": 0, "current": 80}
    assert len(payload["candidate_write_sites"]) >= 2
    print("Automatic QA comparisons:", engine.canonical(evidence["comparisons"]), flush=True)
    assert any(row["added"] == {"level": 1} and row["observed"] == {"moves": 19, "score": 80}
               for row in evidence["comparisons"])
    assert any("level" not in row["added"] and row.get("observed", {}).get("score") == 80 for row in evidence["comparisons"])

    assert any("10 * chosen.length * chosen.length" in item["source"] for item in payload["original_reference"])
    assert mock.ask.call_count == 2
    log_path.write_text(log)
    print("Offline gate passed: observed 80 points / 19 moves, original rule supplied, unchanged repair rejected")
elif sys.argv[1] == "live":
    engine.GENERATION_LIMITS["api.groq.com"] = 2
    try:
        fixed = engine.repair_with_groq(engine.Groq(), plan, scope, assets, [], log_path.read_text(), baseline,
                                        json.loads((folder / "previous.json").read_text()))
    finally:
        print("Physical Groq requests:", engine.generation_counts["api.groq.com"], flush=True)
    output = folder / "result"
    output.mkdir()
    engine.Checkpoint(output, candidate["identity"]).save(fixed, scope, len(plan["steps"]), 2, [])
    before = engine.failure_evidence(log_path.read_text())
    fields = [next(iter(row["added"])) for row in before["comparisons"] if "observed" in row]
    passed, log = engine.run_qa(fixed, dict(probe, verify_fields=fields))
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
