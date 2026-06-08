import json
import tempfile
import unittest
from pathlib import Path


class TempProjectTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write_json(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def write_text(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_basic_project(self, extra_config=None, candidate=None):
        self.write_text("prompts/system.md", "You are gpt-4o. Return JSON. Use function_call when needed.\n")
        self.write_json("baseline.json", {
            "results": [
                {"id": "a", "score": 0.9, "passed": True, "latency_ms": 100, "cost_usd": 0.01},
                {"id": "b", "score": 0.8, "passed": True, "latency_ms": 120, "cost_usd": 0.02}
            ]
        })
        self.write_json("candidate.json", candidate or {
            "results": [
                {"id": "a", "score": 0.91, "passed": True, "latency_ms": 90, "cost_usd": 0.005},
                {"id": "b", "score": 0.82, "passed": True, "latency_ms": 100, "cost_usd": 0.01}
            ]
        })
        config = {
            "project": "demo",
            "source_model": "gpt-4o",
            "target_model": "gpt-4.1",
            "prompts": ["prompts"],
            "evals": {"baseline": "baseline.json", "candidate": "candidate.json"},
            "budget": {"monthly_input_tokens": 1000, "monthly_output_tokens": 500},
            "output_dir": "out",
            "risk_threshold": 95
        }
        if extra_config:
            config.update(extra_config)
        return self.write_json("config.json", config)
