"""Tests for the benchmark harness. Run with: python3 -m unittest discover -s tests"""

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

import run as bench  # noqa: E402


class ScoringTest(unittest.TestCase):
    def test_contains_checks_pass(self):
        task = {"id": "t", "must": ["2026-12-31"], "must_cite": True}
        answer = "The agreement renews on 2026-12-31 (licence-faq.md)."
        self.assertTrue(bench.score_answer(task, answer)["passed"])

    def test_missing_fact_fails(self):
        task = {"id": "t", "must": ["2026-12-31"], "must_cite": True}
        self.assertFalse(bench.score_answer(task, "It renews at the end of the year.")["passed"])

    def test_refusal_is_required(self):
        task = {"id": "t", "must_refuse": True}
        self.assertTrue(bench.score_answer(task, "The documents do not answer that question.")["passed"])
        self.assertFalse(bench.score_answer(task, "The penalty is 2% of the contract value.")["passed"])

    def test_false_premise_is_penalised(self):
        task = {"id": "t", "must_not": ["because"], "must_cite": True}
        self.assertFalse(
            bench.score_answer(task, "They are allowed because an exception exists (dlp-policy.md).")["passed"]
        )

    def test_invented_number_fails(self):
        task = {"id": "t", "must": ["300"], "must_cite": True}
        answer = "The timeout is 300 seconds and the retry budget is 4500 (oncall-runbook.md)."
        self.assertFalse(bench.score_answer(task, answer)["passed"])


class BundleTest(unittest.TestCase):
    def test_bundle_loads_and_every_task_has_a_corpus(self):
        spec, corpus = bench.load_bundle(ROOT / "bench" / "tasks.json")
        self.assertGreaterEqual(len(spec["tasks"]), 10)
        for task in spec["tasks"]:
            source = task.get("source")
            if source is not None:
                self.assertIn(source, corpus)
        ids = [task["id"] for task in spec["tasks"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_prompt_carries_each_document(self):
        spec, corpus = bench.load_bundle(ROOT / "bench" / "tasks.json")
        message = bench.build_user_message("question?", corpus)
        for name in corpus:
            self.assertIn(name, message)


class FakeEndpointTest(unittest.TestCase):
    def test_run_with_stub_endpoint(self):
        original = bench.call_endpoint
        bench.call_endpoint = lambda endpoint, model, messages, api_key: "The documents do not answer that question."
        try:
            report = bench.run("http://stub/v1", "stub", None, ROOT / "bench" / "tasks.json")
        finally:
            bench.call_endpoint = original
        self.assertEqual(report["tasks"], 12)
        # Refusal-only answers pass the refusal tasks and fail the lookups.
        self.assertGreater(report["passed"], 0)
        self.assertLess(report["passed"], report["tasks"])
        json.dumps(report)  # the report must be serialisable


if __name__ == "__main__":
    unittest.main()
