import unittest

from agent_model_migration_planner.models import (
    DEFAULT_MODEL_CATALOG,
    ModelSpec,
    apply_price_rows,
    compare_capabilities,
    estimate_cost,
    merge_model_catalog,
)


class ModelTests(unittest.TestCase):
    def test_default_catalog_contains_common_models(self):
        self.assertIn("gpt-4o", DEFAULT_MODEL_CATALOG)
        self.assertIn("claude-4-sonnet", DEFAULT_MODEL_CATALOG)
        self.assertIn("gemini-2.5-pro", DEFAULT_MODEL_CATALOG)

    def test_model_from_mapping_defaults(self):
        spec = ModelSpec.from_mapping("x", {"provider": "local"})
        self.assertEqual(spec.name, "x")
        self.assertEqual(spec.provider, "local")
        self.assertEqual(spec.context_window, 8192)

    def test_model_to_dict_roundtrip_name(self):
        spec = DEFAULT_MODEL_CATALOG["gpt-4o"]
        self.assertEqual(spec.to_dict()["name"], "gpt-4o")

    def test_merge_model_catalog_adds_custom_model(self):
        catalog = merge_model_catalog({"custom-a": {"provider": "self", "context_window": 10}})
        self.assertEqual(catalog["custom-a"].provider, "self")
        self.assertEqual(catalog["custom-a"].context_window, 10)

    def test_merge_model_catalog_overrides_existing(self):
        catalog = merge_model_catalog({"gpt-4o": {"input_cost_per_1m": 1.23}})
        self.assertEqual(catalog["gpt-4o"].input_cost_per_1m, 1.23)
        self.assertEqual(catalog["gpt-4o"].provider, "openai")

    def test_compare_capabilities_reports_lost(self):
        old = ModelSpec("old", "x", 10, 0, 0, supports_tools=True)
        new = ModelSpec("new", "x", 10, 0, 0, supports_tools=False)
        changes = compare_capabilities(old, new)
        self.assertIn({"capability": "supports_tools", "label": "工具调用", "direction": "lost"}, changes)

    def test_compare_capabilities_reports_gained(self):
        old = ModelSpec("old", "x", 10, 0, 0, supports_vision=False)
        new = ModelSpec("new", "x", 10, 0, 0, supports_vision=True)
        self.assertIn("gained", [item["direction"] for item in compare_capabilities(old, new)])

    def test_estimate_cost(self):
        spec = ModelSpec("m", "p", 100, 2, 10)
        self.assertAlmostEqual(estimate_cost(spec, 1_000_000, 500_000), 7.0)

    def test_apply_price_rows_updates_existing(self):
        catalog = apply_price_rows(merge_model_catalog(), [{"model": "gpt-4o", "input_cost_per_1m": "9"}])
        self.assertEqual(catalog["gpt-4o"].input_cost_per_1m, 9.0)

    def test_apply_price_rows_creates_new(self):
        catalog = apply_price_rows({}, [{"model": "new-model", "provider": "x", "context_window": "99"}])
        self.assertEqual(catalog["new-model"].context_window, 99)


if __name__ == "__main__":
    unittest.main()
