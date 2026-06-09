import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Optional

from .ci import EXIT_CONFIG_ERROR, EXIT_INTERNAL_ERROR, ci_exit_code
from .config import load_config
from .exceptions import ConfigError, InputDataError
from .models import DEFAULT_MODEL_CATALOG
from .planner import plan_migration
from .reports import write_json_report, write_markdown_report, write_pr_comment_report, write_sarif_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-model-migration-planner",
        description="读取 prompt/config/eval/价格表，生成模型迁移计划和 CI 退出码。",
    )
    sub = parser.add_subparsers(dest="command")

    plan = sub.add_parser("plan", help="生成迁移报告")
    plan.add_argument("-c", "--config", required=True, help="迁移配置 JSON")
    plan.add_argument("-o", "--output-dir", help="覆盖配置中的输出目录")
    plan.add_argument(
        "--format",
        choices=("markdown", "json", "both", "sarif", "pr-comment"),
        default="both",
        help="输出格式",
    )
    plan.add_argument("--no-ci-fail", action="store_true", help="始终返回 0，仅生成报告")
    plan.add_argument("--print-summary", action="store_true", help="在 stdout 打印简短摘要")

    validate = sub.add_parser("validate", help="校验配置和输入路径")
    validate.add_argument("-c", "--config", required=True, help="迁移配置 JSON")

    catalog = sub.add_parser("catalog", help="输出内置模型能力/价格表")
    catalog.add_argument("--json", action="store_true", help="以 JSON 输出")

    return parser


def _print_summary(plan) -> None:
    print(
        f"{plan.config.project}: {plan.source_model.name} -> {plan.target_model.name}; "
        f"risk={plan.risk_profile.level}/{plan.risk_profile.score}; "
        f"eval_delta={plan.eval_comparison.score_delta:+.4f}; "
        f"blocking={plan.risk_profile.blocking_count}"
    )


def _run_plan(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.output_dir:
        from dataclasses import replace

        config = replace(config, output_dir=Path(args.output_dir).resolve())
    plan = plan_migration(config)
    written = []
    if args.format in ("json", "both"):
        written.append(write_json_report(plan))
    if args.format in ("markdown", "both"):
        written.append(write_markdown_report(plan))
    if args.format == "sarif":
        written.append(write_sarif_report(plan))
    if args.format == "pr-comment":
        written.append(write_pr_comment_report(plan))
    if args.print_summary:
        _print_summary(plan)
        for path in written:
            print(f"wrote: {path}")
    return 0 if args.no_ci_fail else ci_exit_code(plan)


def _run_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print(f"配置有效: {config.project}")
    return 0


def _run_catalog(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps({name: spec.to_dict() for name, spec in DEFAULT_MODEL_CATALOG.items()}, ensure_ascii=False, indent=2))
        return 0
    for name, spec in sorted(DEFAULT_MODEL_CATALOG.items()):
        print(f"{name}\t{spec.provider}\tcontext={spec.context_window}\tinput={spec.input_cost_per_1m}/1M\toutput={spec.output_cost_per_1m}/1M")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.command:
        parser.print_help()
        return 0
    try:
        if args.command == "plan":
            return _run_plan(args)
        if args.command == "validate":
            return _run_validate(args)
        if args.command == "catalog":
            return _run_catalog(args)
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except InputDataError as exc:
        print(f"输入错误: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except Exception as exc:
        print(f"内部错误: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR
    return EXIT_INTERNAL_ERROR
