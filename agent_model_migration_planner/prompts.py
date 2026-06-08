import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .exceptions import InputDataError


PROMPT_SUFFIXES = {".txt", ".md", ".prompt", ".json", ".yaml", ".yml"}


@dataclass(frozen=True)
class PromptFileSummary:
    path: str
    estimated_tokens: int
    lines: int


@dataclass(frozen=True)
class PromptFinding:
    rule_id: str
    path: str
    line: int
    severity: int
    message: str
    recommendation: str
    snippet: str

    @property
    def level(self) -> str:
        if self.severity >= 80:
            return "critical"
        if self.severity >= 60:
            return "high"
        if self.severity >= 35:
            return "medium"
        return "low"

    def to_dict(self) -> Dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "path": self.path,
            "line": self.line,
            "severity": self.severity,
            "level": self.level,
            "message": self.message,
            "recommendation": self.recommendation,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class PromptScanResult:
    files: List[PromptFileSummary]
    findings: List[PromptFinding]

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_estimated_tokens(self) -> int:
        return sum(item.estimated_tokens for item in self.files)

    def to_dict(self) -> Dict[str, object]:
        return {
            "total_files": self.total_files,
            "total_estimated_tokens": self.total_estimated_tokens,
            "files": [item.__dict__ for item in self.files],
            "findings": [item.to_dict() for item in self.findings],
        }


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_tokens = len(re.findall(r"[A-Za-z0-9_./:-]+", text))
    punctuation = max(0, len(text) - cjk_chars) // 18
    return max(1, cjk_chars + latin_tokens + punctuation)


def iter_prompt_files(paths: Sequence[Path]) -> List[Path]:
    files: List[Path] = []
    for root in paths:
        if root.is_file():
            if root.suffix.lower() in PROMPT_SUFFIXES:
                files.append(root)
            continue
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix.lower() in PROMPT_SUFFIXES:
                    files.append(path)
            continue
        raise InputDataError(f"prompt 路径不存在: {root}")
    return sorted(set(files))


def _make_finding(rule_id: str, path: Path, line_no: int, severity: int, message: str, recommendation: str, line: str) -> PromptFinding:
    return PromptFinding(
        rule_id=rule_id,
        path=str(path),
        line=line_no,
        severity=severity,
        message=message,
        recommendation=recommendation,
        snippet=line.strip()[:180],
    )


def scan_prompt_files(paths: Sequence[Path], source_model: Optional[str] = None) -> PromptScanResult:
    summaries: List[PromptFileSummary] = []
    findings: List[PromptFinding] = []
    for path in iter_prompt_files(paths):
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines() or [""]
        summaries.append(PromptFileSummary(path=str(path), estimated_tokens=estimate_tokens(text), lines=len(lines)))
        findings.extend(scan_prompt_text(text, path, source_model=source_model))
    return PromptScanResult(files=summaries, findings=findings)


def scan_prompt_text(text: str, path: Path, source_model: Optional[str] = None) -> List[PromptFinding]:
    findings: List[PromptFinding] = []
    source_pattern = re.compile(re.escape(source_model), re.IGNORECASE) if source_model else None
    json_words = re.compile(r"\b(json|JSON|structured output|结构化输出)\b")
    schema_words = re.compile(r"\b(schema|json_schema|properties|字段|模式)\b", re.IGNORECASE)
    legacy_tool_words = re.compile(r"\b(function_call|functions|tool_choice\s*:\s*auto)\b", re.IGNORECASE)
    strict_words = re.compile(r"(必须|一定|永远|绝不|exactly|always|never|must)", re.IGNORECASE)
    gen_param_words = re.compile(r"\b(temperature|top_p|max_tokens|presence_penalty|frequency_penalty)\b", re.IGNORECASE)
    vendor_words = re.compile(r"\b(Claude|Anthropic|OpenAI|Gemini|Codex)\b", re.IGNORECASE)
    xml_tool_words = re.compile(r"<(tool|function|answer|thinking)[^>]*>", re.IGNORECASE)

    for line_no, line in enumerate(text.splitlines(), start=1):
        if source_pattern and source_pattern.search(line):
            findings.append(_make_finding(
                "P001", path, line_no, 65,
                "prompt 中硬编码了旧模型名称",
                "改为通过运行时变量注入模型名，或删除与旧模型绑定的行为描述。",
                line,
            ))
        if legacy_tool_words.search(line):
            findings.append(_make_finding(
                "P002", path, line_no, 75,
                "发现旧式工具/function 调用提示",
                "迁移到目标模型 SDK 的 tools/tool_choice/response_format 约定，并为工具参数补齐 JSON Schema。",
                line,
            ))
        if json_words.search(line) and not schema_words.search(line):
            findings.append(_make_finding(
                "P003", path, line_no, 45,
                "要求结构化输出但缺少明确 schema",
                "在配置或 prompt 中提供字段名、类型、必填项和错误处理示例。",
                line,
            ))
        if len(strict_words.findall(line)) >= 3:
            findings.append(_make_finding(
                "P004", path, line_no, 35,
                "同一行存在较多绝对化约束",
                "保留真正不可违反的约束，把风格偏好降级为可测试的评分标准。",
                line,
            ))
        if gen_param_words.search(line):
            findings.append(_make_finding(
                "P005", path, line_no, 40,
                "prompt 中混入采样或 token 参数",
                "把 temperature/top_p/max_tokens 等参数移动到调用配置，避免不同 SDK 迁移时失效。",
                line,
            ))
        if vendor_words.search(line) and (not source_pattern or not source_pattern.search(line)):
            findings.append(_make_finding(
                "P006", path, line_no, 30,
                "prompt 中出现供应商或模型族名称",
                "确认这是业务必要信息；否则改为中性描述，降低跨供应商路由风险。",
                line,
            ))
        if xml_tool_words.search(line):
            findings.append(_make_finding(
                "P007", path, line_no, 50,
                "发现 XML 风格工具或思考标签",
                "确认目标模型是否仍推荐该格式；必要时改成 SDK 原生消息、工具和结构化输出。",
                line,
            ))
    return findings
