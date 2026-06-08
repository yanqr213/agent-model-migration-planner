import json
import unittest

from agent_model_migration_planner.config import config_to_dict, load_config, validate_config
from agent_model_migration_planner.exceptions import ConfigError
from tests.helpers import TempProjectTestCase


class ConfigTests(TempProjectTestCase):
    def test_load_valid_config(self):
        path = self.write_basic_project()
        config = load_config(str(path))
        self.assertEqual(config.project, "demo")
        self.assertEqual(config.source_model, "gpt-4o")

    def test_resolves_relative_paths(self):
        path = self.write_basic_project()
        config = load_config(str(path))
        self.assertTrue(config.prompt_paths[0].is_absolute())
        self.assertTrue(str(config.prompt_paths[0]).endswith("prompts"))

    def test_missing_config_file_raises(self):
        with self.assertRaises(ConfigError):
            load_config(str(self.root / "missing.json"))

    def test_invalid_json_raises(self):
        path = self.write_text("bad.json", "{")
        with self.assertRaises(ConfigError):
            load_config(str(path))

    def test_root_must_be_mapping(self):
        path = self.write_text("bad.json", "[]")
        with self.assertRaises(ConfigError):
            load_config(str(path))

    def test_requires_project(self):
        path = self.write_basic_project()
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["project"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_config(str(path))

    def test_requires_non_empty_prompts(self):
        path = self.write_basic_project({"prompts": []})
        with self.assertRaises(ConfigError):
            load_config(str(path))

    def test_requires_eval_candidate(self):
        path = self.write_basic_project({"evals": {"baseline": "baseline.json"}})
        with self.assertRaises(ConfigError):
            load_config(str(path))

    def test_risk_threshold_range(self):
        path = self.write_basic_project({"risk_threshold": 101})
        with self.assertRaises(ConfigError):
            load_config(str(path))

    def test_validate_config_missing_prompt_path(self):
        path = self.write_basic_project({"prompts": ["missing"]})
        with self.assertRaises(ConfigError):
            load_config(str(path))

    def test_negative_budget_rejected(self):
        path = self.write_basic_project({"budget": {"monthly_input_tokens": -1}})
        with self.assertRaises(ConfigError):
            load_config(str(path))

    def test_config_to_dict_contains_output_dir(self):
        config = load_config(str(self.write_basic_project()))
        self.assertIn("output_dir", config_to_dict(config))

    def test_optional_model_catalog_path(self):
        self.write_json("models.json", {"models": {"x": {"provider": "p"}}})
        path = self.write_basic_project({"model_catalog": "models.json"})
        self.assertTrue(load_config(str(path)).model_catalog_path.exists())

    def test_optional_price_table_path(self):
        self.write_text("prices.csv", "model,input_cost_per_1m\nx,1\n")
        path = self.write_basic_project({"price_table": "prices.csv"})
        self.assertTrue(load_config(str(path)).price_table_path.exists())


if __name__ == "__main__":
    unittest.main()
