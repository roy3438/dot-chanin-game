"""Offline regression checks for the approved development retry."""
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

import engine


class RetryTests(unittest.TestCase):
    def test_wait_for_tokens_before_retry(self):
        error = engine.GroqRateLimit({"Retry-After": "5", "x-ratelimit-reset-tokens": "41.79s"})
        with patch.object(engine, "request", side_effect=[error, {"ok": True}]), patch.object(engine.time, "sleep") as wait:
            self.assertEqual(engine.request_groq("url", {}, {}), {"ok": True})
            wait.assert_called_once_with(42)

    def test_unauthorized_file_rejected(self):
        with self.assertRaises(engine.Stop):
            engine.apply_file_response({"files": {"a.js": "a", "b.js": "b"}}, {"a.js": "write"}, {}, True)

    def test_budget_before_network(self):
        host = "api.groq.com"
        with patch.dict(engine.generation_counts, {host: engine.GENERATION_LIMITS[host]}), patch.object(engine.urllib.request, "urlopen") as network:
            with self.assertRaises(engine.Stop):
                engine.request("https://" + host, "POST", {}, {})
            network.assert_not_called()

    def test_resume_after_qa_environment_failure(self):
        plan = {"steps": [{"files": {"index.html": "write"}}], "mode": "update-game", "tests": []}
        base = {"index.html": b"old"}
        original = Mock()
        original.ask.side_effect = [{"files": {"index.html": "candidate"}}, {"issues": []}]
        identity = [8, 123, "456", "base"]
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = engine.Checkpoint(folder, identity)
            with self.assertRaisesRegex(engine.Stop, "environment"):
                engine.deploy_candidate(original, plan, "", base, Mock(side_effect=engine.Stop("environment")), print, checkpoint=checkpoint)
            self.assertEqual(original.ask.call_count, 2)
            with self.assertRaises(engine.Stop):
                engine.Checkpoint(folder, identity[:-1] + ["other"])
            resumed = Mock()
            assets, _, repairs = engine.deploy_candidate(resumed, plan, "", base, lambda *_: (True, "pass"), print,
                                                        checkpoint=engine.Checkpoint(folder, identity))
            resumed.ask.assert_not_called()
            self.assertEqual((assets["index.html"], repairs), (b"candidate", 0))

    def test_repair_size_uses_serialized_utf8_before_transport(self):
        data = {"browser_result": "시험", "source": {"game.js": "한" * 50}}
        with patch.dict(engine.os.environ, {"GROQ_API_KEY": "fixture", "STUDIO_REPAIR_BYTES": "4096"}), patch.object(engine, "request_groq") as network:
            network.return_value = {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
            engine.Groq().ask("fixture", data, 100)
            size = len(engine.canonical(network.call_args.args[2]).encode())
            network.reset_mock()
            with patch.dict(engine.os.environ, {"STUDIO_REPAIR_BYTES": str(size - 1)}):
                with self.assertRaisesRegex(engine.Stop, "전송 전 중단"):
                    engine.Groq().ask("fixture", data, 100)
            network.assert_not_called()
            with patch.dict(engine.os.environ, {"STUDIO_REPAIR_BYTES": str(size)}):
                engine.Groq().ask("fixture", data, 100)
            network.assert_called_once()

    def test_repair_gate_uses_same_case_and_keeps_regression(self):
        evidence = {"case": "short"}
        plan = {"tests": [{"name": "long"}, {"name": "short"}], "dot_chain_regression": True}
        qa = Mock(return_value=(True, "PASS"))
        engine.verify_repair(qa, {"game.js": b"candidate"}, plan, evidence)
        self.assertEqual(qa.call_args.args[1], {"tests": [{"name": "short"}], "dot_chain_regression": True})
        self.assertEqual(len(plan["tests"]), 2)
        qa.return_value = False, "legacy drag failed"
        with self.assertRaisesRegex(engine.Stop, "기존 후보 유지"):
            engine.verify_repair(qa, {}, plan, evidence)

    def test_restored_rejected_repair_skips_provider_until_evidence_changes(self):
        scope = {"index.html": "write"}
        plan = {"steps": [{"files": scope}], "mode": "update-game", "tests": []}
        base = {"index.html": b"old"}
        ai = Mock()
        ai.ask.return_value = {"files": {"index.html": "ineffective"}}
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = engine.Checkpoint(folder, ["trial"])
            checkpoint.save(base, scope, 1, 0, [])
            def resume(log):
                restored = engine.Checkpoint(folder, ["trial"])
                qa = Mock(return_value=(False, log))
                engine.deploy_candidate(ai, plan, "", base, qa, lambda *_: None, checkpoint=restored)

            with self.assertRaises(engine.RejectedRepair):
                resume("failed case A")
            self.assertEqual(ai.ask.call_count, 1)
            with self.assertRaisesRegex(engine.Stop, "재호출을 중단"):
                resume("failed case A")
            self.assertEqual(ai.ask.call_count, 1)
            with self.assertRaises(engine.RejectedRepair):
                resume("failed case B")
            self.assertEqual(ai.ask.call_count, 2)
            restored = engine.Checkpoint(folder, ["trial"])
            self.assertEqual(restored.state["files"], {"index.html": "old"})

    def test_level_two_short_chain_is_independent(self):
        original = {"level": 2, "score": 1900, "moves": 5, "missionProgress": {"longChain": False}}
        plan = {"tests": [{"seed": {"dot-chain-v1": json.dumps(original)}}]}
        negative = engine.level_two_negative(plan)
        self.assertEqual(negative["seed"]["dot-chain-v1"]["score"], 1980)
        self.assertEqual(negative["steps"][0]["target"], "[data-pos='1']")
        self.assertEqual(json.loads(plan["tests"][0]["seed"]["dot-chain-v1"]), original)


if __name__ == "__main__":
    unittest.main()
