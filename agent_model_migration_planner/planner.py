import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .config import PlannerConfig, config_to_dict
from .evals import EvalComparison, compare_eval_files
from .exceptions import ConfigError
from .io import load_json_object, load_json_or_csv_rows
from .models import ModelSpec, apply_price_rows, estimate_cost, merge_model_catalog
from .prompts import PromptScanResult, scan_prompt_files
from .risk import RiskProfile, build_risk_profile


@dataclass(frozen=True)
class MigrationStep:
    step_id: str
    title: str
    category: str
    description: str
    checks: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.step_id,
            "title": self.title,
            "category": self.category,
            "description": self.description,
            "checks": list(self.checks),
        }


@dataclass(frozen=True)
class MigrationPlan:
    config: PlannerConfig
    source_model: ModelSpec
    target_model: ModelSpec
    prompt_scan: PromptScanResult
    eval_comparison: EvalComparison
    budget_impact: Dict[str, Any]
    risk_profile: RiskProfile
    steps: List[MigrationStep]
    rollout_plan: List[str]
    rollback_checks: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project": self.config.project,
            "config": config_to_dict(self.config),
            "source_model": self.source_model.to_dict(),
            "target_model": self.target_model.to_dict(),
            "prompt_scan": self.prompt_scan.to_dict(),
            "eval_comparison": self.eval_comparison.to_dict(),
            "budget_impact": self.budget_impact,
            "risk_profile": self.risk_profile.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "rollout_plan": list(self.rollout_plan),
            "rollback_checks": list(self.rollback_checks),
        }


def _load_catalog(config: PlannerConfig) -> Dict[str, ModelSpec]:
    overrides = None
    if config.model_catalog_path:
        overrides = load_json_object(config.model_catalog_path).get("models", load_json_object(config.model_catalog_path))
    catalog = merge_model_catalog(overrides)  # type: ignore[arg-type]
    if config.price_table_path:
        catalog = apply_price_rows(catalog, load_json_or_csv_rows(config.price_table_path))
    return catalog


def _get_model(catalog: Dict[str, ModelSpec], name: str) -> ModelSpec:
    if name not in catalog:
        raise ConfigError(f"模型不在能力/价格表中: {name}")
    return catalog[name]


def _budget_impact(config: PlannerConfig, source: ModelSpec, target: ModelSpec) -> Dict[str, Any]:
    input_tokens = config.budget_config.monthly_input_tokens
    output_tokens = config.budget_config.monthly_output_tokens
    old_cost = estimate_cost(source, input_tokens, output_tokens)
    new_cost = estimate_cost(target, input_tokens, output_tokens)
    delta = new_cost - old_cost
    pct = (delta / old_cost) if old_cost > 0 else (None if new_cost == 0 else 1.0)
    return {
        "monthly_input_tokens": input_tokens,
        "monthly_output_tokens": output_tokens,
        "source_monthly_cost_usd": round(old_cost, 4),
        "target_monthly_cost_usd": round(new_cost, 4),
        "monthly_cost_delta_usd": round(delta, 4),
        "monthly_cost_delta_pct": pct,
    }


def _generate_steps(plan_seed: Dict[str, Any]) -> List[MigrationStep]:
    risk_profile: RiskProfile = plan_seed["risk_profile"]
    eval_comparison: EvalComparison = plan_seed["eval_comparison"]
    prompt_scan: PromptScanResult = plan_seed["prompt_scan"]
    steps = [
        MigrationStep(
            "M001",
            "冻结迁移基线",
            "baseline",
            "记录旧模型版本、路由规则、prompt 文件、工具 schema、eval baseline 和当前预算假设。",
            ["baseline eval 可复现", "报告中的 source/target 模型与配置一致", "CI 使用同一份配置文件"],
        ),
        MigrationStep(
            "M002",
            "修正 prompt 兼容性问题",
            "prompt",
            f"处理扫描出的 {len(prompt_scan.findings)} 个 prompt 风险点，优先修复旧工具调用、硬编码模型名和缺少 schema 的结构化输出。",
            ["所有 P001/P002/P003 项均有 owner", "高风险 prompt 修改后重跑相关 eval", "保留旧 prompt 作为回滚版本"],
        ),
        MigrationStep(
            "M003",
            "适配工具调用与结构化输出",
            "tools",
            "对比目标模型 SDK 的 tools、tool_choice、response_format、并行工具调用和错误重试语义。",
            ["工具参数具备 JSON Schema", "工具错误路径有 eval 覆盖", "并行工具调用顺序依赖已显式处理"],
        ),
        MigrationStep(
            "M004",
            "补齐 eval 覆盖缺口",
            "eval",
            f"当前 candidate 缺失 {len(eval_comparison.missing_candidate_ids)} 个 baseline 用例，回归 {eval_comparison.regression_count} 个用例。",
            ["candidate 覆盖全部 baseline case", "关键路径 severe regression 为 0", "新增至少一个目标模型特有失败模式用例"],
        ),
        MigrationStep(
            "M005",
            "建立预算与延迟护栏",
            "budget",
            "按月度 token 假设计算 spend cap，并在灰度路由中记录模型、输入/输出 token、延迟和失败原因。",
            ["预算涨幅在阈值内或有审批", "P95/P99 延迟看板可用", "超预算自动降级或熔断"],
        ),
        MigrationStep(
            "M006",
            "灰度发布",
            "rollout",
            "从影子流量开始，再按低风险用户和低成本场景逐步放量。",
            ["影子流量无用户可见副作用", "1%/5%/25% 阶段均满足质量与成本门槛", "业务 owner 签核后扩大范围"],
        ),
        MigrationStep(
            "M007",
            "回滚演练",
            "rollback",
            "验证配置开关、缓存兼容、会话状态和工具结果能安全回退到旧模型。",
            ["单开关回退成功", "回滚后 eval smoke test 通过", "回滚不会重复执行有副作用工具"],
        ),
    ]
    if risk_profile.has_blocking:
        steps.insert(1, MigrationStep(
            "M000",
            "先解除阻塞风险",
            "risk",
            f"报告发现 {risk_profile.blocking_count} 个阻塞风险，未解除前不建议进入用户可见灰度。",
            ["阻塞项全部关闭或有书面例外", "CI 退出码恢复为 0", "负责人确认风险接受范围"],
        ))
    return steps


def _rollout_plan() -> List[str]:
    return [
        "0% 用户流量：仅离线 eval 和 replay，对比质量、成本、延迟。",
        "影子流量：生产请求双写到目标模型但不返回给用户，禁止有副作用工具执行。",
        "1% 内部/低风险流量：开启实时监控，任一关键指标越线自动回退。",
        "5%-25% 分层灰度：按场景、租户、语言和工具类型分桶观察。",
        "50%-100% 全量：保留旧模型热回退窗口，至少覆盖一个完整业务周期。",
    ]


def _rollback_checks() -> List[str]:
    return [
        "配置中心或环境变量可在一次发布周期内切回 source_model。",
        "目标模型生成的中间状态、缓存键、工具结果不会污染旧模型路径。",
        "回滚 smoke eval 覆盖身份认证、工具调用、结构化输出、长上下文和失败重试。",
        "监控告警包含质量退化、成本突增、延迟突增、工具错误率和 schema 解析失败。",
        "发布记录保留目标模型版本、prompt hash、配置 hash 和 eval run id。",
    ]


def plan_migration(config: PlannerConfig) -> MigrationPlan:
    catalog = _load_catalog(config)
    source = _get_model(catalog, config.source_model)
    target = _get_model(catalog, config.target_model)
    prompt_scan = scan_prompt_files(config.prompt_paths, source_model=config.source_model)
    eval_comparison = compare_eval_files(
        config.eval_config.baseline_path,
        config.eval_config.candidate_path,
        score_key=config.eval_config.score_key,
        latency_key=config.eval_config.latency_key,
    )
    budget_impact = _budget_impact(config, source, target)
    risk_profile = build_risk_profile(config, source, target, prompt_scan, eval_comparison, budget_impact)
    seed = {"risk_profile": risk_profile, "eval_comparison": eval_comparison, "prompt_scan": prompt_scan}
    return MigrationPlan(
        config=config,
        source_model=source,
        target_model=target,
        prompt_scan=prompt_scan,
        eval_comparison=eval_comparison,
        budget_impact=budget_impact,
        risk_profile=risk_profile,
        steps=_generate_steps(seed),
        rollout_plan=_rollout_plan(),
        rollback_checks=_rollback_checks(),
    )


def plan_migration_from_file(config_path: str) -> MigrationPlan:
    from .config import load_config

    return plan_migration(load_config(config_path))
