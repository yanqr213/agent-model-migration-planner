import io
import json
import unittest
from contextlib import redirect_stdout

from agent_model_migration_planner.ci import EXIT_BLOCKED, EXIT_OK, ci_exit_code
from agent_model_migration_planner.cli import main
from agent_model_migration_planner.config import load_config
from agent_model_migration_planner.planner import plan_migration
from agent_model_migration_planner.reports import (
    render_markdown_report,
    render_pr_comment_report,
    render_sarif_report,
    write_json_report,
    write_markdown_report,
)
from tests.helpers import TempProjectTestCase


class PlannerReportCliTests(TempProjectTestCase):
    def test_plan_migration_returns_plan(self):
        config = load_config(str(self.write_basic_project()))
        plan = plan_migration(config)
        self.assertEqual(plan.config.project, "demo")
        self.assertGreaterEqual(len(plan.steps), 1)

    def test_plan_to_dict_contains_risk_profile(self):
        plan = plan_migration(load_config(str(self.write_basic_project())))
        self.assertIn("risk_profile", plan.to_dict())

    def test_budget_impact_cost_decreases_for_example(self):
        plan = plan_migration(load_config(str(self.write_basic_project())))
        self.assertLess(plan.budget_impact["target_monthly_cost_usd"], plan.budget_impact["source_monthly_cost_usd"])

    def test_missing_candidate_creates_blocking_risk(self):
        path = self.write_basic_project(candidate={"results": [{"id": "a", "score": 0.9, "passed": True}]})
        plan = plan_migration(load_config(str(path)))
        self.assertTrue(any(item.area == "eval_coverage" and item.blocking for item in plan.risk_profile.items))

    def test_regression_creates_eval_risk(self):
        path = self.write_basic_project(candidate={"results": [
            {"id": "a", "score": 0.1, "passed": False},
            {"id": "b", "score": 0.1, "passed": False}
        ]})
        plan = plan_migration(load_config(str(path)))
        self.assertTrue(any(item.area == "eval_quality" for item in plan.risk_profile.items))

    def test_ci_exit_ok_when_threshold_high_and_no_blocking(self):
        path = self.write_basic_project({"fail_on_risk": False, "fail_on_eval_regression": False})
        self.assertEqual(ci_exit_code(plan_migration(load_config(str(path)))), EXIT_OK)

    def test_ci_exit_blocked_on_missing_candidate(self):
        path = self.write_basic_project(candidate={"results": [{"id": "a", "score": 0.9, "passed": True}]})
        self.assertEqual(ci_exit_code(plan_migration(load_config(str(path)))), EXIT_BLOCKED)

    def test_render_markdown_has_sections(self):
        plan = plan_migration(load_config(str(self.write_basic_project())))
        text = render_markdown_report(plan)
        self.assertIn("## 摘要", text)
        self.assertIn("## 迁移步骤", text)
        self.assertIn("## CI 判定", text)

    def test_render_pr_comment_has_stable_marker(self):
        plan = plan_migration(load_config(str(self.write_basic_project())))
        text = render_pr_comment_report(plan)
        self.assertIn("<!-- agent-model-migration-planner -->", text)
        self.assertIn("model migration gate", text)
        self.assertIn("| Signal | Value |", text)
        self.assertIn("Prompt Rewrite Checklist", text)

    def test_render_sarif_includes_prompt_locations(self):
        plan = plan_migration(load_config(str(self.write_basic_project())))
        payload = json.loads(render_sarif_report(plan))
        run = payload["runs"][0]
        self.assertEqual(payload["version"], "2.1.0")
        self.assertEqual(run["tool"]["driver"]["name"], "agent-model-migration-planner")
        rule_ids = {rule["id"] for rule in run["tool"]["driver"]["rules"]}
        self.assertIn("P001", rule_ids)
        result = next(item for item in run["results"] if item["ruleId"] == "P001")
        location = result["locations"][0]["physicalLocation"]
        self.assertEqual(location["artifactLocation"]["uri"], "prompts/system.md")
        self.assertEqual(location["region"]["startLine"], 1)

    def test_render_sarif_includes_eval_risks(self):
        path = self.write_basic_project(candidate={"results": [{"id": "a", "score": 0.9, "passed": True}]})
        plan = plan_migration(load_config(str(path)))
        payload = json.loads(render_sarif_report(plan))
        rule_ids = {item["ruleId"] for item in payload["runs"][0]["results"]}
        self.assertIn("MIGRATION_EVAL_COVERAGE", rule_ids)

    def test_write_json_report(self):
        plan = plan_migration(load_config(str(self.write_basic_project())))
        path = write_json_report(plan)
        self.assertTrue(path.exists())
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["project"], "demo")

    def test_write_markdown_report(self):
        plan = plan_migration(load_config(str(self.write_basic_project())))
        path = write_markdown_report(plan)
        self.assertTrue(path.exists())
        self.assertIn("模型迁移规划报告", path.read_text(encoding="utf-8"))

    def test_cli_validate_success(self):
        path = self.write_basic_project()
        self.assertEqual(main(["validate", "-c", str(path)]), 0)

    def test_cli_validate_missing_returns_config_error(self):
        self.assertEqual(main(["validate", "-c", str(self.root / "none.json")]), 3)

    def test_cli_catalog_text(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["catalog"])
        self.assertEqual(code, 0)
        self.assertIn("gpt-4o", buffer.getvalue())

    def test_cli_catalog_json(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["catalog", "--json"])
        self.assertEqual(code, 0)
        self.assertIn("gpt-4.1", json.loads(buffer.getvalue()))

    def test_cli_plan_writes_reports_no_ci_fail(self):
        path = self.write_basic_project()
        code = main(["plan", "-c", str(path), "--no-ci-fail", "--print-summary"])
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "out" / "migration-report.json").exists())
        self.assertTrue((self.root / "out" / "migration-report.md").exists())

    def test_cli_plan_json_only(self):
        path = self.write_basic_project()
        code = main(["plan", "-c", str(path), "--format", "json", "--no-ci-fail"])
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "out" / "migration-report.json").exists())

    def test_cli_plan_sarif_only(self):
        path = self.write_basic_project()
        code = main(["plan", "-c", str(path), "--format", "sarif", "--no-ci-fail"])
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "out" / "migration-report.sarif").exists())

    def test_cli_plan_pr_comment_only(self):
        path = self.write_basic_project()
        code = main(["plan", "-c", str(path), "--format", "pr-comment", "--no-ci-fail"])
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "out" / "migration-pr-comment.md").exists())

    def test_cli_plan_output_dir_override(self):
        path = self.write_basic_project()
        out = self.root / "custom-out"
        code = main(["plan", "-c", str(path), "-o", str(out), "--no-ci-fail"])
        self.assertEqual(code, 0)
        self.assertTrue((out / "migration-report.md").exists())

    def test_cli_help_no_command(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main([])
        self.assertEqual(code, 0)
        self.assertIn("plan", buffer.getvalue())

    def test_custom_catalog_model(self):
        self.write_json("models.json", {"models": {
            "old": {"provider": "x", "context_window": 1000, "input_cost_per_1m": 1, "output_cost_per_1m": 1},
            "new": {"provider": "x", "context_window": 2000, "input_cost_per_1m": 1, "output_cost_per_1m": 1}
        }})
        path = self.write_basic_project({"source_model": "old", "target_model": "new", "model_catalog": "models.json"})
        plan = plan_migration(load_config(str(path)))
        self.assertEqual(plan.source_model.name, "old")

    def test_price_table_override(self):
        self.write_text("prices.csv", "model,input_cost_per_1m,output_cost_per_1m\ngpt-4.1,99,99\n")
        path = self.write_basic_project({"price_table": "prices.csv"})
        plan = plan_migration(load_config(str(path)))
        self.assertEqual(plan.target_model.input_cost_per_1m, 99)


if __name__ == "__main__":
    unittest.main()
