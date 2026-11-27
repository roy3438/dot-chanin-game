"""One-time acceptance trial for the saved issue 8 candidate."""
import base64
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
if sys.argv[1:] == ["score"]:
    # Resume the independently generated 8/12 candidate; freeze every passing input handler.
    previous = folder / "previous"
    files = {name: (previous / name).read_text() for name in scope}
    source = files["script.js"]
    start = source.index("    let cleared = false;", source.index("  function endSelection("))
    end = source.index("    // Decrease move counter", start)
    inputs = {"failed_section": source[start:end], "browser_result":
              "2 red level2 at 1980 -> expected 2020 playing, got 1980. "
              "2 red level3 at 1980 red4 blue6 -> expected 2020 won red6 blue6. "
              "The section only calls addScore for level1, length bonus on level2 or zero on level3.",
              "contract": "selected is the array of chosen indexes. chainLen already equals its length >=2. "
              "Always award base points 10*chainLen*chainLen ONCE for every level and clear every valid chain ONCE. "
              "Keep level2 longChain and bonus, and increment level3 red or blue by chainLen based on "
              "state.board[selected[0]] BEFORE clearing. addScore(total,0,0) increments saved score. "
              "Moves, win/loss decisions, persistence and listeners are handled outside this section."}
    schema = {"type":"object","properties":{"section":{"type":"string"}},
              "required":["section"],"additionalProperties":False}
    engine.GENERATION_LIMITS["api.groq.com"] = 1
    answer = engine.Groq().ask("Write just the replacement JS statements for the indicated section inside "
                               "endSelection. Do not redefine endSelection or chainLen. Return section string.",
                               inputs, 1200, schema=schema)
    output = folder / "result"
    output.mkdir(exist_ok=True)
    (output / "provider-response.json").write_text(engine.canonical(answer))
    section = answer["section"]
    assert isinstance(section, str) and section.strip()
    files["script.js"] = source[:start] + section + "\n" + source[end:]
    proposed = engine.apply_file_response({"files": files}, scope, baseline, True)
    for name in scope:
        (output / name).write_bytes(proposed[name])
    passed, log = engine.run_qa(proposed, full)
    (output / "qa.log").write_text(log)
    print(log, flush=True)
    raise SystemExit(0 if passed else 1)

if sys.argv[1:] == ["repair"]:
    source = assets["script.js"].decode()
    # Restrict the repair to the two handlers implicated by the recorded interactions.
    start = source.index("  function endSelection(")
    end = source.index("  function clearDots(", start)
    buttons = source.index("  $restartBtn.addEventListener(")
    mute = source.index("  $muteBtn.addEventListener(", buttons)
    inputs = {
        "browser_result": "Lv2 two red: moves 5->4, score stays 1980 instead of 2020. Lv3 two red: red stays 4 instead of 6, blue already 6, score stays 1980. Mobile next/restart receive pointerup but no click before assertion. Desktop works.",
        "chain": source[start:end], "buttons": source[buttons:mute],
        "helpers": "addScore(delta,0,0) already increments score; clearDots(positions) replaces selected cells; clearSelection resets selected; finishGame(victory) saves and displays outcome; updateUI and saveState exist; randomizeBoard, renderBoard and generateMission exist.",
        "rules": "Valid chain awards 10*length^2 at all levels; retain existing bonuses. A move costs one turn. Level 1 score>=2000 wins. Level 2 needs score and longChain (5+ at least once). Level 3 needs score and cumulative red AND blue >=6. Win before last-turn loss. Existing level1 baseline two red +40. Preserve legacy saves. Restart resets current level score/moves/mission/board and next level starts fresh with 20 moves, preserving best, unlocked, mute. Click supports keyboard and mouse. For touch handle pointerup immediately on each result button and guard phase/level so a compatibility click cannot double-advance."
    }
    inputs["source_context"] = source[:start] + source[end:buttons] + source[mute:]
    inputs["previous_result"] = ("A previous candidate regressed desktop next-level even when click reached the "
                                 "button. After a win the saved phase is 'won'; after loss it is 'lost'. "
                                 "Retain working mouse click behavior and add touch activation to both result buttons.")
    inputs["approved_task"] = envelope["task"]
    engine.GENERATION_LIMITS["generativelanguage.googleapis.com"] = 1
    engine.GENERATION_LIMITS["api.groq.com"] = 1
    provider = engine.Gemini() if os.environ.get("GEMINI_API_KEY") else engine.Groq()
    schema = {"type": "object", "properties": {k: {"type": "string"} for k in ("chain", "buttons")},
              "required": ["chain", "buttons"], "additionalProperties": False}
    format_options = {"schema": schema} if isinstance(provider, engine.Groq) else {}
    answer = provider.ask("Implement the approved behavior for all cases, including legacy saves. "
                          "Return JSON containing chain and buttons as complete replacement JS strings. "
                          "Read actual helper bodies, identifiers and phase values in source_context. "
                          "In your reasoning simulate level 2 at 1980 plus two dots, level 3 at red 4 blue 6, "
                          "and mouse and touch result button activation. Preserve existing passing controls.", inputs, 4500, **format_options)
    output = folder / "result"
    output.mkdir(exist_ok=True)
    (output / "provider-response.json").write_text(engine.canonical(answer), encoding="utf-8")
    if not all(isinstance(answer.get(k), str) and answer[k].strip() for k in ("chain", "buttons")):
        fields = {k: type(value).__name__ for k, value in answer.items()}
        raise engine.Stop("Invalid replacement blocks; response preserved for offline review: " +
                          engine.canonical(fields)[:500])
    patched = source[:start] + answer["chain"] + "\n" + source[end:buttons] + answer["buttons"] + "\n" + source[mute:]
    proposed = engine.apply_file_response({"files": {"script.js": patched}}, {"script.js":"write"}, assets, True)
    for name in scope:
        (output / name).write_bytes(proposed[name])
    passed, log = engine.run_qa(proposed, full)
    (output / "qa.log").write_text(log)
    print(log, flush=True)
    if not passed:
        raise SystemExit("Full candidate QA failed")
    raise SystemExit(0)

if sys.argv[1:] != ["acceptance"]:
    raise SystemExit("Expected acceptance replay")

payload = json.loads((folder / "rejected.json").read_text())
assert payload["identity"] == candidate["identity"]
assert payload["state"]["files"] != candidate["state"]["files"]
output = folder / "result"
checkpoint = engine.Checkpoint(output, candidate["identity"])
checkpoint.save(assets, scope, len(plan["steps"]), 0, [])
mock = Mock()
mock.ask.return_value = {"files": payload["state"]["files"]}
runs = []
def replay(files, definition):
    if runs:
        assert len(definition["tests"]) == 1
    passed, log = engine.run_qa(files, definition)
    if not runs:
        traces = [json.loads(line.removeprefix("STUDIO_TRACE ")) for line in log.splitlines()
                  if line.startswith("STUDIO_TRACE ")]
        assert len(traces) == 6, [(t["case"], t["device"]) for t in traces]
        (output / "failed-interactions.json").write_text(json.dumps(traces, ensure_ascii=False, indent=2))
        for trace in traces:
            print("Observed interaction", json.dumps(trace, ensure_ascii=False), flush=True)
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
assert len(runs) == 2 and mock.ask.call_count == 1
for row in runs:
    assert row["expected"]["score"] == 2020 and row["observed"]["score"] == 1980
restored = engine.Checkpoint(output, candidate["identity"])
assert restored.state["files"] == candidate["state"]["files"] and restored.state["repairs"] == 0
assert restored.state["files"] != payload["state"]["files"]
print("Verified restored candidate file contents, rejected revision excluded. No provider requests.")
provider = Mock()
try:
    engine.deploy_candidate(provider, plan, envelope["task"], baseline,
                            Mock(return_value=(False, restored.state["log"])), print, checkpoint=restored)
except engine.Stop as error:
    assert "재호출을 중단" in str(error), str(error)
else:
    raise AssertionError("Duplicate repair was allowed")
provider.ask.assert_not_called()
