"""One-time acceptance trial for the saved issue 8 candidate."""
import base64
import difflib
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
    rejected = json.loads((folder / "rejected.json").read_text())
    assert rejected["identity"] == candidate["identity"]
    bad_assets = engine.apply_file_response({"files": rejected["state"]["files"]}, scope, baseline, True)
    guard = dict(plan, dot_chain_regression=True, probe_only=True, tests=[])
    good, good_log = engine.run_qa(assets, guard)
    bad, bad_log = engine.run_qa(bad_assets, guard)
    assert good and not bad, good_log + bad_log
    errors = [line for line in bad_log.splitlines() if line.startswith("STUDIO_PAGE_ERRORS ")]
    changes = {}
    for name in scope:
        if assets.get(name) != bad_assets.get(name):
            changes[name] = "\n".join(difflib.unified_diff(
                assets.get(name, b"").decode().splitlines(), bad_assets.get(name, b"").decode().splitlines(),
                n=1, lineterm=""))[:1200]
    print("Rejected changes:", changes, "Browser errors:", errors, flush=True)
    short = engine.level_two_negative(plan)
    def initial(row):
        raw = row.get("seed", {}).get("dot-chain-v1", {})
        return json.loads(raw) if isinstance(raw, str) else raw

    long = next(row for row in plan["tests"] if initial(row).get("level") == 2)
    passed, log = engine.run_qa(assets, dict(plan, dot_chain_regression=False,
                                            tests=[dict(long, capture_mission=True), short]))
    controls = [json.loads(line.removeprefix("STUDIO_CONTROL ")) for line in log.splitlines()
                if line.startswith("STUDIO_CONTROL ")]
    evidence = engine.failure_evidence(log)
    assert not passed and evidence and controls, log
    assert evidence["seed"]["level"] == 2 and all(case["score"] >= 2000 for case in controls)
    evidence["passing_control"] = {"initial_score": initial(long)["score"], "observed": controls[0]}
    evidence["rejected_repair"] = {"changes": changes, "errors": errors, "guard": "Same legacy two-dot drag passed on input and failed on rejected revision."}
    print("Level 2 comparison", controls[0], evidence["observed"], flush=True)
    log_path.write_text("STUDIO_EVIDENCE " + json.dumps(evidence, ensure_ascii=False))
elif sys.argv[1] == "live":
    engine.GENERATION_LIMITS["api.groq.com"] = 4
    try:
        fixed = engine.repair_with_groq(engine.Groq(), plan, scope, assets, [], log_path.read_text(), baseline)
    finally:
        print("Physical Groq requests:", engine.generation_counts["api.groq.com"], flush=True)
    output = folder / "result"
    engine.Checkpoint(output, candidate["identity"]).save(fixed, scope, len(plan["steps"]), 2, [])
    short = engine.level_two_negative(plan)
    target_ok, target_log = engine.run_qa(fixed, dict(plan, dot_chain_regression=False,
                                                      tests=[dict(short, capture_mission=True)]))
    print("Target QA:", target_ok, target_log, flush=True)
    passed, log = engine.run_qa(fixed, full)
    print("Full QA", passed, log, flush=True)
    (output / "qa.log").write_text(log)
    if not passed:
        raise SystemExit("Full QA failed; no further model calls")
else:
    raise ValueError("Unknown phase")
