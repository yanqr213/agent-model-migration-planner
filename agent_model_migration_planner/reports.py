import json
from pathlib import Path
from typing import Iterable, Optional

from .planner import MigrationPlan


def write_json_report(plan: MigrationPlan, output_dir: Optional[Path] = None, filename: str = "migration-report.json") -> Path:
    target_dir = output_dir or plan.config.output_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _pct(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.2%}"


def _money(value: object) -> str:
    return f"${float(value):,.2f}"


def _lines(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_markdown_report(plan: MigrationPlan) -> str:
    risk = plan.risk_profile
    evals = plan.eval_comparison
    budget = plan.budget_impact
    prompt_findings = plan.prompt_scan.findings[:30]
    risk_items = plan.risk_profile.items[:30]
    sections = [
        f"# {plan.config.project} 模型迁移规划报告",
        "",
        "## 摘要",
        "",
        f"- 迁移路径: `{plan.source_model.name}` -> `{plan.target_model.name}`",
        f"- 综合风险: **{risk.level} / {risk.score}**，阻塞项: **{risk.blocking_count}**",
        f"- Prompt 文件: {plan.prompt_scan.total_files}，估算 token: {plan.prompt_scan.total_estimated_tokens}",
        f"- Eval 平均分变化: {evals.score_delta:+.4f}，通过率变化: {_pct(evals.pass_rate_delta)}，回归用例: {evals.regression_count}",
        f"- 月度成本变化: {_money(budget['monthly_cost_delta_usd'])} ({_pct(budget['monthly_cost_delta_pct'])})",
        "",
        "## 模型能力与预算",
        "",
        "| 项目 | 旧模型 | 新模型 |",
        "| --- | --- | --- |",
        f"| Provider | {plan.source_model.provider} | {plan.target_model.provider} |",
        f"| Context window | {plan.source_model.context_window} | {plan.target_model.context_window} |",
        f"| Input $/1M tokens | {plan.source_model.input_cost_per_1m} | {plan.target_model.input_cost_per_1m} |",
        f"| Output $/1M tokens | {plan.source_model.output_cost_per_1m} | {plan.target_model.output_cost_per_1m} |",
        f"| Tools | {plan.source_model.supports_tools} | {plan.target_model.supports_tools} |",
        f"| JSON mode | {plan.source_model.supports_json_mode} | {plan.target_model.supports_json_mode} |",
        f"| Vision | {plan.source_model.supports_vision} | {plan.target_model.supports_vision} |",
        "",
        "## Eval 对比",
        "",
        f"- Baseline cases: {evals.baseline_count}",
        f"- Candidate cases: {evals.candidate_count}",
        f"- Matched cases: {evals.matched_count}",
        f"- Missing candidate ids: {', '.join(evals.missing_candidate_ids) if evals.missing_candidate_ids else '无'}",
        f"- New candidate ids: {', '.join(evals.new_candidate_ids) if evals.new_candidate_ids else '无'}",
        f"- Latency delta: {_pct(evals.latency_delta_pct)}",
        f"- Eval cost delta: {_pct(evals.cost_delta_pct)}",
        "",
        "## 风险清单",
        "",
    ]
    if risk_items:
        sections.extend([
            "| Level | Area | Severity | Blocking | Reason | Evidence | Recommendation |",
            "| --- | --- | ---: | --- | --- | --- | --- |",
        ])
        for item in risk_items:
            evidence = item.evidence.replace("|", "\\|")
            recommendation = item.recommendation.replace("|", "\\|")
            sections.append(f"| {item.level} | {item.area} | {item.severity} | {item.blocking} | {item.reason} | {evidence} | {recommendation} |")
    else:
        sections.append("未发现显著风险。")
    sections.extend(["", "## Prompt 改造清单", ""])
    if prompt_findings:
        sections.extend([
            "| Rule | Level | File | Line | Message | Recommendation |",
            "| --- | --- | --- | ---: | --- | --- |",
        ])
        for finding in prompt_findings:
            sections.append(
                f"| {finding.rule_id} | {finding.level} | `{finding.path}` | {finding.line} | {finding.message} | {finding.recommendation} |"
            )
    else:
        sections.append("未发现需要立即改造的 prompt 项。")
    sections.extend([
        "",
        "## 迁移步骤",
        "",
    ])
    for step in plan.steps:
        sections.extend([
            f"### {step.step_id} {step.title}",
            "",
            step.description,
            "",
            _lines(step.checks),
            "",
        ])
    sections.extend([
        "## 灰度计划",
        "",
        _lines(plan.rollout_plan),
        "",
        "## 回滚检查",
        "",
        _lines(plan.rollback_checks),
        "",
        "## CI 判定",
        "",
        f"- fail_on_risk: {plan.config.fail_on_risk}",
        f"- risk_threshold: {plan.config.risk_threshold}",
        f"- fail_on_eval_regression: {plan.config.fail_on_eval_regression}",
        "- 退出码 0 表示可继续；2 表示风险或 eval 阻塞；3 表示配置/输入错误；1 表示内部错误。",
        "",
    ])
    return "\n".join(sections)


def write_markdown_report(plan: MigrationPlan, output_dir: Optional[Path] = None, filename: str = "migration-report.md") -> Path:
    target_dir = output_dir or plan.config.output_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_text(render_markdown_report(plan), encoding="utf-8")
    return path
