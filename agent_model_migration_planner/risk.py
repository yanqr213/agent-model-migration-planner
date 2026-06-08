from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .config import PlannerConfig
from .evals import EvalComparison
from .models import ModelSpec, compare_capabilities
from .prompts import PromptScanResult


@dataclass(frozen=True)
class RiskItem:
    area: str
    severity: int
    reason: str
    evidence: str
    recommendation: str
    blocking: bool = False

    @property
    def level(self) -> str:
        return severity_to_level(self.severity)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "area": self.area,
            "severity": self.severity,
            "level": self.level,
            "reason": self.reason,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class RiskProfile:
    score: int
    level: str
    blocking_count: int
    items: List[RiskItem]

    @property
    def has_blocking(self) -> bool:
        return self.blocking_count > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level,
            "blocking_count": self.blocking_count,
            "items": [item.to_dict() for item in self.items],
        }


def severity_to_level(severity: int) -> str:
    if severity >= 85:
        return "critical"
    if severity >= 70:
        return "high"
    if severity >= 40:
        return "medium"
    return "low"


def aggregate_risk(items: Iterable[RiskItem]) -> RiskProfile:
    collected = sorted(list(items), key=lambda item: item.severity, reverse=True)
    if not collected:
        return RiskProfile(score=0, level="low", blocking_count=0, items=[])
    top = collected[:5]
    score = round(max(item.severity for item in top) * 0.55 + sum(item.severity for item in top) / len(top) * 0.45)
    blocking_count = sum(1 for item in collected if item.blocking)
    return RiskProfile(score=score, level=severity_to_level(score), blocking_count=blocking_count, items=collected)


def build_risk_profile(
    config: PlannerConfig,
    source: ModelSpec,
    target: ModelSpec,
    prompt_scan: PromptScanResult,
    eval_comparison: EvalComparison,
    budget_impact: Mapping[str, Any],
) -> RiskProfile:
    items: List[RiskItem] = []
    for change in compare_capabilities(source, target):
        if change["direction"] == "lost":
            items.append(RiskItem(
                area="model_capability",
                severity=82,
                reason=f"目标模型缺少旧模型能力: {change['label']}",
                evidence=f"{source.name} -> {target.name}: {change['capability']} lost",
                recommendation="为该能力补充适配层、替代模型路由或关闭依赖该能力的场景后再灰度。",
                blocking=True,
            ))
        else:
            items.append(RiskItem(
                area="model_capability",
                severity=18,
                reason=f"目标模型新增能力: {change['label']}",
                evidence=f"{source.name} -> {target.name}: {change['capability']} gained",
                recommendation="评估是否能简化 prompt 或工具编排，但不要在同一次迁移里扩大变更范围。",
            ))

    if prompt_scan.total_estimated_tokens > target.context_window:
        items.append(RiskItem(
            area="context",
            severity=90,
            reason="现有 prompt 估算 token 超过目标模型上下文窗口",
            evidence=f"estimated={prompt_scan.total_estimated_tokens}, target_context={target.context_window}",
            recommendation="拆分上下文、引入检索压缩或选择更大上下文的目标模型。",
            blocking=True,
        ))
    elif target.context_window and prompt_scan.total_estimated_tokens > target.context_window * 0.8:
        items.append(RiskItem(
            area="context",
            severity=55,
            reason="现有 prompt 接近目标模型上下文窗口上限",
            evidence=f"estimated={prompt_scan.total_estimated_tokens}, target_context={target.context_window}",
            recommendation="在灰度前加入 token 预算监控和截断测试。",
        ))

    for finding in prompt_scan.findings:
        items.append(RiskItem(
            area="prompt",
            severity=finding.severity,
            reason=finding.message,
            evidence=f"{finding.path}:{finding.line} {finding.snippet}",
            recommendation=finding.recommendation,
            blocking=finding.severity >= 80,
        ))

    if eval_comparison.missing_candidate_ids:
        items.append(RiskItem(
            area="eval_coverage",
            severity=78,
            reason="candidate eval 缺少 baseline 用例",
            evidence=", ".join(eval_comparison.missing_candidate_ids[:10]),
            recommendation="补齐缺失用例后重新比较，避免覆盖率下降被误判为通过。",
            blocking=True,
        ))
    if eval_comparison.score_delta < config.eval_config.pass_threshold_delta:
        items.append(RiskItem(
            area="eval_quality",
            severity=85,
            reason="candidate 平均分低于允许阈值",
            evidence=f"score_delta={eval_comparison.score_delta:.4f}, threshold={config.eval_config.pass_threshold_delta:.4f}",
            recommendation="定位退化用例，改造 prompt/tool schema 后重跑 eval。",
            blocking=config.fail_on_eval_regression,
        ))
    if eval_comparison.regression_rate > config.eval_config.max_regression_rate:
        items.append(RiskItem(
            area="eval_quality",
            severity=80,
            reason="回归用例比例超过阈值",
            evidence=f"regression_rate={eval_comparison.regression_rate:.2%}, threshold={config.eval_config.max_regression_rate:.2%}",
            recommendation="按业务关键性排序修复 severe regressions，并追加针对性断言。",
            blocking=config.fail_on_eval_regression,
        ))
    if eval_comparison.latency_delta_pct is not None and eval_comparison.latency_delta_pct > config.eval_config.max_latency_delta_pct:
        items.append(RiskItem(
            area="latency",
            severity=62,
            reason="candidate 平均延迟涨幅超过阈值",
            evidence=f"latency_delta_pct={eval_comparison.latency_delta_pct:.2%}",
            recommendation="拆分长 prompt、开启缓存、调整并发或保留旧模型作为慢路径回退。",
        ))

    increase_pct = budget_impact.get("monthly_cost_delta_pct")
    if increase_pct is not None and increase_pct > config.budget_config.max_monthly_cost_increase_pct:
        items.append(RiskItem(
            area="budget",
            severity=72,
            reason="月度预算涨幅超过配置阈值",
            evidence=f"cost_delta_pct={increase_pct:.2%}, threshold={config.budget_config.max_monthly_cost_increase_pct:.2%}",
            recommendation="先对高 token 场景做灰度，设置 route-level spend cap 和降级策略。",
            blocking=False,
        ))

    return aggregate_risk(items)
