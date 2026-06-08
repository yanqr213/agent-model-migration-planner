import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .exceptions import ConfigError


@dataclass(frozen=True)
class EvaluationConfig:
    baseline_path: Path
    candidate_path: Path
    score_key: str = "score"
    pass_threshold_delta: float = -0.02
    max_regression_rate: float = 0.05
    latency_key: str = "latency_ms"
    max_latency_delta_pct: float = 0.35


@dataclass(frozen=True)
class BudgetConfig:
    monthly_input_tokens: int = 0
    monthly_output_tokens: int = 0
    max_monthly_cost_increase_pct: float = 0.20


@dataclass(frozen=True)
class PlannerConfig:
    project: str
    source_model: str
    target_model: str
    prompt_paths: List[Path]
    eval_config: EvaluationConfig
    budget_config: BudgetConfig
    output_dir: Path
    model_catalog_path: Optional[Path] = None
    price_table_path: Optional[Path] = None
    risk_threshold: int = 70
    fail_on_risk: bool = True
    fail_on_eval_regression: bool = True
    raw: Optional[Mapping[str, Any]] = None


def _require_mapping(data: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise ConfigError(f"{label} 必须是 JSON object")
    return data


def _resolve_path(base_dir: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} 必须是非空路径字符串")
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path


def _optional_path(base_dir: Path, value: Any, label: str) -> Optional[Path]:
    if value in (None, ""):
        return None
    return _resolve_path(base_dir, value, label)


def load_config(path: str) -> PlannerConfig:
    config_path = Path(path).resolve()
    if not config_path.exists():
        raise ConfigError(f"配置文件不存在: {config_path}")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"配置文件不是合法 JSON: {exc}") from exc
    raw = _require_mapping(data, "配置根节点")
    base_dir = config_path.parent

    for key in ("project", "source_model", "target_model", "prompts", "evals"):
        if key not in raw:
            raise ConfigError(f"缺少必填配置项: {key}")

    project = str(raw["project"]).strip()
    source_model = str(raw["source_model"]).strip()
    target_model = str(raw["target_model"]).strip()
    if not project or not source_model or not target_model:
        raise ConfigError("project/source_model/target_model 均不能为空")

    prompts = raw["prompts"]
    if not isinstance(prompts, list) or not prompts:
        raise ConfigError("prompts 必须是非空路径数组")
    prompt_paths = [_resolve_path(base_dir, item, "prompts[]") for item in prompts]

    evals = _require_mapping(raw["evals"], "evals")
    if "baseline" not in evals or "candidate" not in evals:
        raise ConfigError("evals 必须包含 baseline 和 candidate")
    eval_config = EvaluationConfig(
        baseline_path=_resolve_path(base_dir, evals["baseline"], "evals.baseline"),
        candidate_path=_resolve_path(base_dir, evals["candidate"], "evals.candidate"),
        score_key=str(evals.get("score_key", "score")),
        pass_threshold_delta=float(evals.get("pass_threshold_delta", -0.02)),
        max_regression_rate=float(evals.get("max_regression_rate", 0.05)),
        latency_key=str(evals.get("latency_key", "latency_ms")),
        max_latency_delta_pct=float(evals.get("max_latency_delta_pct", 0.35)),
    )

    budget_raw = _require_mapping(raw.get("budget", {}), "budget")
    budget_config = BudgetConfig(
        monthly_input_tokens=int(budget_raw.get("monthly_input_tokens", 0)),
        monthly_output_tokens=int(budget_raw.get("monthly_output_tokens", 0)),
        max_monthly_cost_increase_pct=float(budget_raw.get("max_monthly_cost_increase_pct", 0.20)),
    )

    output_dir = _resolve_path(base_dir, raw.get("output_dir", "migration-report"), "output_dir")
    risk_threshold = int(raw.get("risk_threshold", 70))
    if not (0 <= risk_threshold <= 100):
        raise ConfigError("risk_threshold 必须在 0-100 之间")

    config = PlannerConfig(
        project=project,
        source_model=source_model,
        target_model=target_model,
        prompt_paths=prompt_paths,
        eval_config=eval_config,
        budget_config=budget_config,
        output_dir=output_dir,
        model_catalog_path=_optional_path(base_dir, raw.get("model_catalog"), "model_catalog"),
        price_table_path=_optional_path(base_dir, raw.get("price_table"), "price_table"),
        risk_threshold=risk_threshold,
        fail_on_risk=bool(raw.get("fail_on_risk", True)),
        fail_on_eval_regression=bool(raw.get("fail_on_eval_regression", True)),
        raw=raw,
    )
    validate_config(config)
    return config


def validate_config(config: PlannerConfig) -> None:
    missing = [str(path) for path in config.prompt_paths if not path.exists()]
    for path in (config.eval_config.baseline_path, config.eval_config.candidate_path):
        if not path.exists():
            missing.append(str(path))
    if config.model_catalog_path and not config.model_catalog_path.exists():
        missing.append(str(config.model_catalog_path))
    if config.price_table_path and not config.price_table_path.exists():
        missing.append(str(config.price_table_path))
    if missing:
        raise ConfigError("以下输入路径不存在: " + ", ".join(missing))
    if config.budget_config.monthly_input_tokens < 0 or config.budget_config.monthly_output_tokens < 0:
        raise ConfigError("budget token 数不能为负数")
    if config.eval_config.max_regression_rate < 0:
        raise ConfigError("max_regression_rate 不能为负数")
    if config.eval_config.max_latency_delta_pct < 0:
        raise ConfigError("max_latency_delta_pct 不能为负数")


def config_to_dict(config: PlannerConfig) -> Dict[str, Any]:
    return {
        "project": config.project,
        "source_model": config.source_model,
        "target_model": config.target_model,
        "prompts": [str(path) for path in config.prompt_paths],
        "evals": {
            "baseline": str(config.eval_config.baseline_path),
            "candidate": str(config.eval_config.candidate_path),
            "score_key": config.eval_config.score_key,
            "pass_threshold_delta": config.eval_config.pass_threshold_delta,
            "max_regression_rate": config.eval_config.max_regression_rate,
            "latency_key": config.eval_config.latency_key,
            "max_latency_delta_pct": config.eval_config.max_latency_delta_pct,
        },
        "budget": {
            "monthly_input_tokens": config.budget_config.monthly_input_tokens,
            "monthly_output_tokens": config.budget_config.monthly_output_tokens,
            "max_monthly_cost_increase_pct": config.budget_config.max_monthly_cost_increase_pct,
        },
        "output_dir": str(config.output_dir),
        "model_catalog": str(config.model_catalog_path) if config.model_catalog_path else None,
        "price_table": str(config.price_table_path) if config.price_table_path else None,
        "risk_threshold": config.risk_threshold,
        "fail_on_risk": config.fail_on_risk,
        "fail_on_eval_regression": config.fail_on_eval_regression,
    }
