import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .planner import MigrationPlan
from .risk import RiskItem


def write_json_report(plan: MigrationPlan, output_dir: Optional[Path] = None, filename: str = "migration-report.json") -> Path:
    target_dir = output_dir or plan.config.output_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_sarif_report(plan: MigrationPlan, output_dir: Optional[Path] = None, filename: str = "migration-report.sarif") -> Path:
    target_dir = output_dir or plan.config.output_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_text(render_sarif_report(plan), encoding="utf-8")
    return path


def write_pr_comment_report(plan: MigrationPlan, output_dir: Optional[Path] = None, filename: str = "migration-pr-comment.md") -> Path:
    target_dir = output_dir or plan.config.output_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_text(render_pr_comment_report(plan), encoding="utf-8")
    return path


def _pct(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.2%}"


def _money(value: object) -> str:
    return f"${float(value):,.2f}"


def _lines(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _table_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


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


def render_pr_comment_report(plan: MigrationPlan) -> str:
    risk = plan.risk_profile
    evals = plan.eval_comparison
    budget = plan.budget_impact
    sections = [
        "<!-- agent-model-migration-planner -->",
        f"## {plan.config.project} model migration gate",
        "",
        (
            f"**Path:** `{plan.source_model.name}` -> `{plan.target_model.name}` | "
            f"**Risk:** `{risk.level}` / {risk.score} | "
            f"**Blocking:** {risk.blocking_count} | "
            f"**Eval delta:** {evals.score_delta:+.4f}"
        ),
        "",
        "### Summary",
        "",
        "| Signal | Value |",
        "| --- | --- |",
        f"| Prompt files | {plan.prompt_scan.total_files} |",
        f"| Prompt findings | {len(plan.prompt_scan.findings)} |",
        f"| Eval regressions | {evals.regression_count} |",
        f"| Missing candidate cases | {len(evals.missing_candidate_ids)} |",
        f"| Monthly cost delta | {_money(budget['monthly_cost_delta_usd'])} ({_pct(budget['monthly_cost_delta_pct'])}) |",
        "",
        "### Top Risks",
        "",
    ]
    if plan.risk_profile.items:
        sections.extend(["| Level | Area | Blocking | Reason | Recommendation |", "| --- | --- | --- | --- | --- |"])
        for item in plan.risk_profile.items[:10]:
            sections.append(
                "| "
                f"`{item.level}` | "
                f"{_table_cell(item.area)} | "
                f"{item.blocking} | "
                f"{_table_cell(item.reason)} | "
                f"{_table_cell(item.recommendation)} |"
            )
    else:
        sections.append("No migration risks detected.")

    sections.extend(["", "### Prompt Rewrite Checklist", ""])
    if plan.prompt_scan.findings:
        sections.extend(["| Rule | Level | File | Line | Fix |", "| --- | --- | --- | ---: | --- |"])
        for finding in plan.prompt_scan.findings[:10]:
            sections.append(
                "| "
                f"`{finding.rule_id}` | "
                f"`{finding.level}` | "
                f"`{_table_cell(_display_path(plan, finding.path))}` | "
                f"{finding.line} | "
                f"{_table_cell(finding.recommendation)} |"
            )
    else:
        sections.append("No prompt rewrites required by the scanner.")

    sections.extend(["", "### Next Migration Steps", ""])
    for step in plan.steps[:5]:
        sections.append(f"- **{step.step_id} {step.title}:** {step.description}")
    sections.extend(
        [
            "",
            "_Generated by `agent-model-migration-planner plan --format pr-comment`._",
        ]
    )
    return "\n".join(sections).rstrip() + "\n"


def render_sarif_report(plan: MigrationPlan) -> str:
    rules: Dict[str, Dict[str, Any]] = {}
    results: List[Dict[str, Any]] = []

    for finding in plan.prompt_scan.findings:
        rule_id = finding.rule_id
        rules.setdefault(
            rule_id,
            {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": finding.message},
                "fullDescription": {"text": finding.recommendation},
                "help": {"text": finding.recommendation},
                "properties": {"tags": ["prompt", "model-migration", "ai-agent"]},
            },
        )
        results.append(
            {
                "ruleId": rule_id,
                "level": _sarif_level(finding.severity),
                "message": {"text": finding.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": _sarif_uri(plan, finding.path)},
                            "region": {
                                "startLine": max(1, int(finding.line)),
                                "snippet": {"text": finding.snippet},
                            },
                        }
                    }
                ],
                "properties": {
                    "severity": finding.severity,
                    "recommendation": finding.recommendation,
                    "riskLevel": finding.level,
                },
            }
        )

    for index, item in enumerate(plan.risk_profile.items, start=1):
        if item.area == "prompt":
            continue
        rule_id = f"MIGRATION_{item.area.upper()}"
        rules.setdefault(
            rule_id,
            {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": item.reason},
                "fullDescription": {"text": item.recommendation},
                "help": {"text": item.recommendation},
                "properties": {"tags": ["model-migration", "ai-agent", item.area]},
            },
        )
        results.append(_risk_sarif_result(plan, item, rule_id, index))

    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "agent-model-migration-planner",
                        "informationUri": "https://github.com/yanqr213/agent-model-migration-planner",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
                "properties": {
                    "project": plan.config.project,
                    "sourceModel": plan.source_model.name,
                    "targetModel": plan.target_model.name,
                    "riskScore": plan.risk_profile.score,
                    "riskLevel": plan.risk_profile.level,
                    "blockingCount": plan.risk_profile.blocking_count,
                },
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _risk_sarif_result(plan: MigrationPlan, item: RiskItem, rule_id: str, index: int) -> Dict[str, Any]:
    uri = _risk_artifact_uri(plan, item)
    return {
        "ruleId": rule_id,
        "level": _sarif_level(item.severity),
        "message": {"text": item.reason},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": 1},
                }
            }
        ],
        "partialFingerprints": {
            "migrationRisk": f"{rule_id}:{index}:{item.area}:{item.evidence}"[:256],
        },
        "properties": {
            "severity": item.severity,
            "blocking": item.blocking,
            "evidence": item.evidence,
            "recommendation": item.recommendation,
            "riskLevel": item.level,
        },
    }


def _risk_artifact_uri(plan: MigrationPlan, item: RiskItem) -> str:
    if item.area.startswith("eval"):
        return _sarif_uri(plan, str(plan.config.eval_config.candidate_path))
    if item.area in {"budget", "model_capability", "context", "latency"}:
        return _sarif_uri(plan, str(plan.config.config_path or plan.config.output_dir))
    return "."


def _display_path(plan: MigrationPlan, raw_path: str) -> str:
    root = _report_root(plan)
    path = Path(raw_path)
    try:
        return str(path.resolve().relative_to(root)).replace("\\", "/")
    except (OSError, ValueError):
        return str(path).replace("\\", "/")


def _sarif_uri(plan: MigrationPlan, raw_path: str) -> str:
    uri = _display_path(plan, raw_path)
    if uri in {"", "."}:
        return "."
    return uri


def _sarif_level(severity: int) -> str:
    if severity >= 80:
        return "error"
    if severity >= 35:
        return "warning"
    return "note"


def _report_root(plan: MigrationPlan) -> Path:
    candidates = [
        plan.config.output_dir.parent.resolve(),
        plan.config.eval_config.baseline_path.resolve(),
        plan.config.eval_config.candidate_path.resolve(),
    ]
    if plan.config.config_path:
        candidates.append(plan.config.config_path.resolve())
    candidates.extend(path.resolve() for path in plan.config.prompt_paths)
    try:
        return Path(os.path.commonpath([str(path) for path in candidates]))
    except ValueError:
        return plan.config.output_dir.parent.resolve()


def write_markdown_report(plan: MigrationPlan, output_dir: Optional[Path] = None, filename: str = "migration-report.md") -> Path:
    target_dir = output_dir or plan.config.output_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_text(render_markdown_report(plan), encoding="utf-8")
    return path
