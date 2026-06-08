import unittest
from pathlib import Path

from agent_model_migration_planner.prompts import estimate_tokens, iter_prompt_files, scan_prompt_text, scan_prompt_files
from tests.helpers import TempProjectTestCase


class PromptTests(TempProjectTestCase):
    def test_estimate_tokens_empty(self):
        self.assertEqual(estimate_tokens(""), 0)

    def test_estimate_tokens_cjk_and_latin(self):
        self.assertGreaterEqual(estimate_tokens("你好 JSON world"), 4)

    def test_iter_prompt_files_accepts_file(self):
        path = self.write_text("a.md", "hello")
        self.assertEqual(iter_prompt_files([path]), [path])

    def test_iter_prompt_files_filters_suffix(self):
        self.write_text("prompts/a.md", "a")
        self.write_text("prompts/b.py", "b")
        files = iter_prompt_files([self.root / "prompts"])
        self.assertEqual(len(files), 1)

    def test_scan_detects_source_model(self):
        findings = scan_prompt_text("use gpt-4o now", Path("p.md"), source_model="gpt-4o")
        self.assertEqual(findings[0].rule_id, "P001")

    def test_scan_detects_legacy_tooling(self):
        findings = scan_prompt_text("call function_call", Path("p.md"))
        self.assertIn("P002", [item.rule_id for item in findings])

    def test_scan_detects_json_without_schema(self):
        findings = scan_prompt_text("Return JSON only", Path("p.md"))
        self.assertIn("P003", [item.rule_id for item in findings])

    def test_scan_does_not_flag_json_with_schema(self):
        findings = scan_prompt_text("Return JSON schema with properties", Path("p.md"))
        self.assertNotIn("P003", [item.rule_id for item in findings])

    def test_scan_detects_strict_words(self):
        findings = scan_prompt_text("must always never do x", Path("p.md"))
        self.assertIn("P004", [item.rule_id for item in findings])

    def test_scan_detects_generation_params(self):
        findings = scan_prompt_text("temperature must be 0", Path("p.md"))
        self.assertIn("P005", [item.rule_id for item in findings])

    def test_scan_detects_vendor_words(self):
        findings = scan_prompt_text("Claude style answer", Path("p.md"))
        self.assertIn("P006", [item.rule_id for item in findings])

    def test_scan_detects_xml_tags(self):
        findings = scan_prompt_text("<tool>search</tool>", Path("p.md"))
        self.assertIn("P007", [item.rule_id for item in findings])

    def test_scan_prompt_files_summarizes(self):
        self.write_text("prompts/a.md", "Return JSON")
        result = scan_prompt_files([self.root / "prompts"])
        self.assertEqual(result.total_files, 1)
        self.assertGreater(result.total_estimated_tokens, 0)

    def test_prompt_finding_level(self):
        finding = scan_prompt_text("function_call", Path("p.md"))[0]
        self.assertEqual(finding.level, "high")


if __name__ == "__main__":
    unittest.main()
