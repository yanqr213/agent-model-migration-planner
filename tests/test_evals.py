import unittest

from agent_model_migration_planner.evals import EvalCase, compare_eval_cases, compare_eval_files, load_eval_cases
from tests.helpers import TempProjectTestCase


class EvalTests(TempProjectTestCase):
    def test_load_eval_cases_from_json_results(self):
        path = self.write_json("eval.json", {"results": [{"id": "a", "score": 0.9, "passed": True}]})
        cases = load_eval_cases(path)
        self.assertEqual(cases[0].case_id, "a")

    def test_load_eval_cases_from_json_list(self):
        path = self.write_json("eval.json", [{"case_id": "a", "score": 0.9}])
        self.assertEqual(load_eval_cases(path)[0].case_id, "a")

    def test_load_eval_cases_from_csv(self):
        path = self.write_text("eval.csv", "id,score,passed\na,0.7,false\n")
        case = load_eval_cases(path)[0]
        self.assertFalse(case.passed)

    def test_load_eval_default_pass_by_score(self):
        path = self.write_json("eval.json", [{"id": "a", "score": 0.81}])
        self.assertTrue(load_eval_cases(path)[0].passed)

    def test_compare_eval_cases_counts_matched(self):
        comp = compare_eval_cases([EvalCase("a", 1, True)], [EvalCase("a", 1, True)])
        self.assertEqual(comp.matched_count, 1)

    def test_compare_eval_cases_missing_candidate(self):
        comp = compare_eval_cases([EvalCase("a", 1, True)], [])
        self.assertEqual(comp.missing_candidate_ids, ["a"])

    def test_compare_eval_cases_new_candidate(self):
        comp = compare_eval_cases([], [EvalCase("b", 1, True)])
        self.assertEqual(comp.new_candidate_ids, ["b"])

    def test_compare_eval_cases_score_delta(self):
        comp = compare_eval_cases([EvalCase("a", 0.8, True)], [EvalCase("a", 0.9, True)])
        self.assertAlmostEqual(comp.score_delta, 0.1)

    def test_compare_eval_cases_regression(self):
        comp = compare_eval_cases([EvalCase("a", 0.9, True)], [EvalCase("a", 0.7, True)])
        self.assertEqual(comp.regression_count, 1)
        self.assertEqual(comp.severe_regression_count, 1)

    def test_compare_eval_cases_pass_to_fail_is_regression(self):
        comp = compare_eval_cases([EvalCase("a", 0.9, True)], [EvalCase("a", 0.91, False)])
        self.assertEqual(comp.regression_count, 1)

    def test_compare_eval_cases_latency_delta(self):
        comp = compare_eval_cases([EvalCase("a", 1, True, latency_ms=100)], [EvalCase("a", 1, True, latency_ms=150)])
        self.assertAlmostEqual(comp.latency_delta_pct, 0.5)

    def test_compare_eval_cases_cost_delta(self):
        comp = compare_eval_cases([EvalCase("a", 1, True, cost_usd=1)], [EvalCase("a", 1, True, cost_usd=2)])
        self.assertAlmostEqual(comp.cost_delta_pct, 1.0)

    def test_compare_eval_files(self):
        baseline = self.write_json("b.json", [{"id": "a", "score": 1}])
        candidate = self.write_json("c.json", [{"id": "a", "score": 1}])
        self.assertEqual(compare_eval_files(baseline, candidate).matched_count, 1)

    def test_eval_case_to_dict(self):
        data = EvalCase("x", 0.1, False).to_dict()
        self.assertEqual(data["id"], "x")


if __name__ == "__main__":
    unittest.main()
