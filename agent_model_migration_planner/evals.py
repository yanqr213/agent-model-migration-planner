from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .io import load_json_or_csv_rows


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    score: float
    passed: bool
    latency_ms: Optional[float] = None
    cost_usd: Optional[float] = None
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.case_id,
            "score": self.score,
            "passed": self.passed,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


@dataclass(frozen=True)
class EvalComparison:
    baseline_count: int
    candidate_count: int
    matched_count: int
    missing_candidate_ids: List[str]
    new_candidate_ids: List[str]
    baseline_average_score: float
    candidate_average_score: float
    score_delta: float
    baseline_pass_rate: float
    candidate_pass_rate: float
    pass_rate_delta: float
    regression_count: int
    severe_regression_count: int
    regression_rate: float
    latency_delta_pct: Optional[float]
    cost_delta_pct: Optional[float]
    regressions: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_count": self.baseline_count,
            "candidate_count": self.candidate_count,
            "matched_count": self.matched_count,
            "missing_candidate_ids": self.missing_candidate_ids,
            "new_candidate_ids": self.new_candidate_ids,
            "baseline_average_score": self.baseline_average_score,
            "candidate_average_score": self.candidate_average_score,
            "score_delta": self.score_delta,
            "baseline_pass_rate": self.baseline_pass_rate,
            "candidate_pass_rate": self.candidate_pass_rate,
            "pass_rate_delta": self.pass_rate_delta,
            "regression_count": self.regression_count,
            "severe_regression_count": self.severe_regression_count,
            "regression_rate": self.regression_rate,
            "latency_delta_pct": self.latency_delta_pct,
            "cost_delta_pct": self.cost_delta_pct,
            "regressions": self.regressions,
        }


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "ok"}


def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _to_optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    return float(value)


def load_eval_cases(path: Path, score_key: str = "score", latency_key: str = "latency_ms") -> List[EvalCase]:
    cases: List[EvalCase] = []
    for index, row in enumerate(load_json_or_csv_rows(path), start=1):
        case_id = str(row.get("id") or row.get("case_id") or row.get("name") or index)
        score = _to_float(row.get(score_key, row.get("score", row.get("accuracy", 0.0))))
        passed = _to_bool(row.get("passed", row.get("pass", score >= 0.8)))
        cases.append(EvalCase(
            case_id=case_id,
            score=score,
            passed=passed,
            latency_ms=_to_optional_float(row.get(latency_key, row.get("latency_ms"))),
            cost_usd=_to_optional_float(row.get("cost_usd")),
            input_tokens=int(_to_float(row.get("input_tokens"), 0.0)),
            output_tokens=int(_to_float(row.get("output_tokens"), 0.0)),
        ))
    return cases


def _average(values: Iterable[float]) -> float:
    collected = list(values)
    return mean(collected) if collected else 0.0


def _rate(values: Iterable[bool]) -> float:
    collected = list(values)
    if not collected:
        return 0.0
    return sum(1 for item in collected if item) / len(collected)


def compare_eval_cases(baseline: List[EvalCase], candidate: List[EvalCase]) -> EvalComparison:
    baseline_by_id = {case.case_id: case for case in baseline}
    candidate_by_id = {case.case_id: case for case in candidate}
    matched_ids = sorted(set(baseline_by_id) & set(candidate_by_id))
    missing_candidate_ids = sorted(set(baseline_by_id) - set(candidate_by_id))
    new_candidate_ids = sorted(set(candidate_by_id) - set(baseline_by_id))

    regressions: List[Dict[str, Any]] = []
    severe = 0
    for case_id in matched_ids:
        old = baseline_by_id[case_id]
        new = candidate_by_id[case_id]
        delta = new.score - old.score
        passed_to_failed = old.passed and not new.passed
        if delta < -0.02 or passed_to_failed:
            if delta <= -0.10 or passed_to_failed:
                severe += 1
            regressions.append({
                "id": case_id,
                "baseline_score": old.score,
                "candidate_score": new.score,
                "score_delta": delta,
                "baseline_passed": old.passed,
                "candidate_passed": new.passed,
                "passed_to_failed": passed_to_failed,
            })

    baseline_matched = [baseline_by_id[item] for item in matched_ids]
    candidate_matched = [candidate_by_id[item] for item in matched_ids]
    baseline_score = _average(case.score for case in baseline_matched)
    candidate_score = _average(case.score for case in candidate_matched)
    baseline_pass_rate = _rate(case.passed for case in baseline_matched)
    candidate_pass_rate = _rate(case.passed for case in candidate_matched)

    old_latency = _average(case.latency_ms for case in baseline_matched if case.latency_ms is not None)
    new_latency = _average(case.latency_ms for case in candidate_matched if case.latency_ms is not None)
    latency_delta_pct = ((new_latency - old_latency) / old_latency) if old_latency > 0 else None

    old_cost = _average(case.cost_usd for case in baseline_matched if case.cost_usd is not None)
    new_cost = _average(case.cost_usd for case in candidate_matched if case.cost_usd is not None)
    cost_delta_pct = ((new_cost - old_cost) / old_cost) if old_cost > 0 else None

    regression_rate = (len(regressions) / len(matched_ids)) if matched_ids else 0.0
    return EvalComparison(
        baseline_count=len(baseline),
        candidate_count=len(candidate),
        matched_count=len(matched_ids),
        missing_candidate_ids=missing_candidate_ids,
        new_candidate_ids=new_candidate_ids,
        baseline_average_score=baseline_score,
        candidate_average_score=candidate_score,
        score_delta=candidate_score - baseline_score,
        baseline_pass_rate=baseline_pass_rate,
        candidate_pass_rate=candidate_pass_rate,
        pass_rate_delta=candidate_pass_rate - baseline_pass_rate,
        regression_count=len(regressions),
        severe_regression_count=severe,
        regression_rate=regression_rate,
        latency_delta_pct=latency_delta_pct,
        cost_delta_pct=cost_delta_pct,
        regressions=regressions,
    )


def compare_eval_files(baseline_path: Path, candidate_path: Path, score_key: str = "score", latency_key: str = "latency_ms") -> EvalComparison:
    return compare_eval_cases(
        load_eval_cases(baseline_path, score_key=score_key, latency_key=latency_key),
        load_eval_cases(candidate_path, score_key=score_key, latency_key=latency_key),
    )
