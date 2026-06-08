from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class ModelSpec:
    name: str
    provider: str
    context_window: int
    input_cost_per_1m: float
    output_cost_per_1m: float
    supports_tools: bool = True
    supports_json_mode: bool = True
    supports_vision: bool = False
    supports_parallel_tool_calls: bool = False
    supports_system_prompt: bool = True
    supports_reasoning_control: bool = False
    status: str = "active"
    notes: Tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, name: str, data: Mapping[str, Any]) -> "ModelSpec":
        return cls(
            name=str(data.get("name", name)),
            provider=str(data.get("provider", "custom")),
            context_window=int(data.get("context_window", 8192)),
            input_cost_per_1m=float(data.get("input_cost_per_1m", 0.0)),
            output_cost_per_1m=float(data.get("output_cost_per_1m", 0.0)),
            supports_tools=bool(data.get("supports_tools", True)),
            supports_json_mode=bool(data.get("supports_json_mode", True)),
            supports_vision=bool(data.get("supports_vision", False)),
            supports_parallel_tool_calls=bool(data.get("supports_parallel_tool_calls", False)),
            supports_system_prompt=bool(data.get("supports_system_prompt", True)),
            supports_reasoning_control=bool(data.get("supports_reasoning_control", False)),
            status=str(data.get("status", "active")),
            notes=tuple(str(item) for item in data.get("notes", ())),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "context_window": self.context_window,
            "input_cost_per_1m": self.input_cost_per_1m,
            "output_cost_per_1m": self.output_cost_per_1m,
            "supports_tools": self.supports_tools,
            "supports_json_mode": self.supports_json_mode,
            "supports_vision": self.supports_vision,
            "supports_parallel_tool_calls": self.supports_parallel_tool_calls,
            "supports_system_prompt": self.supports_system_prompt,
            "supports_reasoning_control": self.supports_reasoning_control,
            "status": self.status,
            "notes": list(self.notes),
        }


DEFAULT_MODEL_CATALOG: Dict[str, ModelSpec] = {
    "gpt-4o": ModelSpec(
        name="gpt-4o",
        provider="openai",
        context_window=128000,
        input_cost_per_1m=5.0,
        output_cost_per_1m=15.0,
        supports_tools=True,
        supports_json_mode=True,
        supports_vision=True,
        supports_parallel_tool_calls=True,
        supports_reasoning_control=False,
        notes=("内置价格用于规划示例；生产 CI 建议用自有价格表覆盖。",),
    ),
    "gpt-4.1": ModelSpec(
        name="gpt-4.1",
        provider="openai",
        context_window=1000000,
        input_cost_per_1m=2.0,
        output_cost_per_1m=8.0,
        supports_tools=True,
        supports_json_mode=True,
        supports_vision=True,
        supports_parallel_tool_calls=True,
        supports_reasoning_control=False,
    ),
    "gpt-5-codex": ModelSpec(
        name="gpt-5-codex",
        provider="openai",
        context_window=400000,
        input_cost_per_1m=1.25,
        output_cost_per_1m=10.0,
        supports_tools=True,
        supports_json_mode=True,
        supports_vision=True,
        supports_parallel_tool_calls=True,
        supports_reasoning_control=True,
    ),
    "claude-3-5-sonnet": ModelSpec(
        name="claude-3-5-sonnet",
        provider="anthropic",
        context_window=200000,
        input_cost_per_1m=3.0,
        output_cost_per_1m=15.0,
        supports_tools=True,
        supports_json_mode=False,
        supports_vision=True,
        supports_parallel_tool_calls=False,
        supports_reasoning_control=False,
    ),
    "claude-4-sonnet": ModelSpec(
        name="claude-4-sonnet",
        provider="anthropic",
        context_window=200000,
        input_cost_per_1m=3.0,
        output_cost_per_1m=15.0,
        supports_tools=True,
        supports_json_mode=False,
        supports_vision=True,
        supports_parallel_tool_calls=True,
        supports_reasoning_control=True,
    ),
    "gemini-1.5-pro": ModelSpec(
        name="gemini-1.5-pro",
        provider="google",
        context_window=1000000,
        input_cost_per_1m=3.5,
        output_cost_per_1m=10.5,
        supports_tools=True,
        supports_json_mode=True,
        supports_vision=True,
        supports_parallel_tool_calls=False,
        supports_reasoning_control=False,
    ),
    "gemini-2.5-pro": ModelSpec(
        name="gemini-2.5-pro",
        provider="google",
        context_window=1000000,
        input_cost_per_1m=1.25,
        output_cost_per_1m=10.0,
        supports_tools=True,
        supports_json_mode=True,
        supports_vision=True,
        supports_parallel_tool_calls=True,
        supports_reasoning_control=True,
    ),
    "local-agent-default": ModelSpec(
        name="local-agent-default",
        provider="self-hosted",
        context_window=32768,
        input_cost_per_1m=0.0,
        output_cost_per_1m=0.0,
        supports_tools=False,
        supports_json_mode=False,
        supports_vision=False,
        supports_parallel_tool_calls=False,
        supports_reasoning_control=False,
    ),
}


CAPABILITY_LABELS = {
    "supports_tools": "工具调用",
    "supports_json_mode": "JSON/结构化输出模式",
    "supports_vision": "视觉输入",
    "supports_parallel_tool_calls": "并行工具调用",
    "supports_system_prompt": "system prompt",
    "supports_reasoning_control": "推理强度控制",
}


def merge_model_catalog(overrides: Optional[Mapping[str, Mapping[str, Any]]] = None) -> Dict[str, ModelSpec]:
    catalog = dict(DEFAULT_MODEL_CATALOG)
    if not overrides:
        return catalog
    for name, data in overrides.items():
        if name in catalog:
            base = catalog[name].to_dict()
            base.update(dict(data))
            catalog[name] = ModelSpec.from_mapping(name, base)
        else:
            catalog[name] = ModelSpec.from_mapping(name, data)
    return catalog


def compare_capabilities(source: ModelSpec, target: ModelSpec) -> List[Dict[str, str]]:
    changes: List[Dict[str, str]] = []
    for attr, label in CAPABILITY_LABELS.items():
        old = bool(getattr(source, attr))
        new = bool(getattr(target, attr))
        if old != new:
            direction = "lost" if old and not new else "gained"
            changes.append({"capability": attr, "label": label, "direction": direction})
    return changes


def estimate_cost(model: ModelSpec, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * model.input_cost_per_1m / 1_000_000
        + output_tokens * model.output_cost_per_1m / 1_000_000
    )


def apply_price_rows(catalog: Dict[str, ModelSpec], rows: Iterable[Mapping[str, Any]]) -> Dict[str, ModelSpec]:
    updated = dict(catalog)
    for row in rows:
        name = str(row.get("model") or row.get("name") or "").strip()
        if not name:
            continue
        base = updated.get(name, ModelSpec(name=name, provider=str(row.get("provider", "custom")), context_window=8192, input_cost_per_1m=0.0, output_cost_per_1m=0.0))
        changes = {}
        for key in ("provider", "context_window", "input_cost_per_1m", "output_cost_per_1m"):
            if row.get(key) not in (None, ""):
                changes[key] = int(row[key]) if key == "context_window" else (float(row[key]) if key.endswith("_per_1m") else str(row[key]))
        updated[name] = replace(base, **changes)
    return updated
