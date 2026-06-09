# agent-model-migration-planner

`agent-model-migration-planner` 是一个面向 AI Agent 团队的模型迁移规划工具。它读取 prompt、迁移配置、eval baseline/candidate 结果和价格表，自动输出兼容性风险、prompt 改造清单、工具调用差异、预算影响、eval 覆盖缺口、灰度计划、回滚检查，并用 CI 退出码阻止高风险迁移。

项目优先使用 Python 标准库，无运行时外部依赖，提供 CLI 和可导入 API，兼容 Python 3.9+。适合使用 Codex、Claude Code、自研 Agent、OpenAI/Anthropic/Gemini 多模型路由的团队接入发布流程。

## 场景

- 从旧模型迁移到新模型前，检查 prompt 是否硬编码旧模型名、旧式 function_call、缺失 JSON schema、供应商绑定描述等问题。
- 对比 baseline 与 candidate eval，发现质量退化、缺失用例、延迟或成本变化。
- 用内置或自定义模型能力/价格表评估上下文窗口、工具调用、JSON mode、视觉、并行工具调用等兼容性。
- 在 CI 中根据综合风险、阻塞项、eval 回归阈值返回非零退出码。
- 生成 Markdown 报告给研发、产品、SRE、成本 owner 共同评审，同时生成 JSON、SARIF、PR comment 供自动化系统消费。

## 安装

本地开发安装：

```bash
python -m pip install -e .
```

直接运行模块：

```bash
python -m agent_model_migration_planner --help
```

安装后使用命令：

```bash
agent-model-migration-planner --help
amm-plan --help
```

## CLI

校验配置：

```bash
python -m agent_model_migration_planner validate -c examples/migration-config.json
```

生成 Markdown 和 JSON 报告：

```bash
python -m agent_model_migration_planner plan \
  -c examples/migration-config.json \
  --format both \
  --print-summary
```

仅生成报告，不让 CI 因风险失败：

```bash
python -m agent_model_migration_planner plan \
  -c examples/migration-config.json \
  --no-ci-fail
```

生成 GitHub Code Scanning / PR 评论报告：

```bash
python -m agent_model_migration_planner plan \
  -c examples/migration-config.json \
  --format sarif \
  --no-ci-fail

python -m agent_model_migration_planner plan \
  -c examples/migration-config.json \
  --format pr-comment \
  --no-ci-fail
```

查看内置模型表：

```bash
python -m agent_model_migration_planner catalog --json
```

退出码：

- `0`: 通过，可继续发布或进入下一阶段。
- `2`: 风险阈值、阻塞项或 eval 回归触发 CI 阻断。
- `3`: 配置或输入数据错误。
- `1`: 内部错误。

## API

```python
from agent_model_migration_planner import load_config, plan_migration
from agent_model_migration_planner.ci import ci_exit_code
from agent_model_migration_planner.reports import write_json_report, write_markdown_report

config = load_config("examples/migration-config.json")
plan = plan_migration(config)

write_json_report(plan)
write_markdown_report(plan)
exit_code = ci_exit_code(plan)
```

`MigrationPlan.to_dict()` 会返回完整结构化结果，适合接入内部发布平台、PR bot 或质量看板。

## 输入格式

配置文件使用 JSON，示例见 `examples/migration-config.json`：

```json
{
  "project": "codex-agent-router",
  "source_model": "gpt-4o",
  "target_model": "gpt-4.1",
  "prompts": ["prompts"],
  "evals": {
    "baseline": "evals/baseline.json",
    "candidate": "evals/candidate.json",
    "score_key": "score",
    "pass_threshold_delta": -0.03,
    "max_regression_rate": 0.2
  },
  "budget": {
    "monthly_input_tokens": 120000000,
    "monthly_output_tokens": 35000000,
    "max_monthly_cost_increase_pct": 0.15
  },
  "price_table": "prices.csv",
  "output_dir": "../outputs/example-report",
  "risk_threshold": 75
}
```

Prompt 输入支持目录或文件，后缀包括 `.txt`、`.md`、`.prompt`、`.json`、`.yaml`、`.yml`。

Eval 支持 JSON 或 CSV。JSON 可以是数组，也可以是包含 `results` 或 `rows` 的对象。推荐字段：

- `id` 或 `case_id`: 用例唯一标识。
- `score`: 分数，默认比较 key。
- `passed`: 是否通过。
- `latency_ms`: 延迟。
- `cost_usd`: 单用例成本。
- `input_tokens` / `output_tokens`: token 统计。

价格表 CSV 字段：

```csv
model,provider,context_window,input_cost_per_1m,output_cost_per_1m
gpt-4o,openai,128000,5.00,15.00
gpt-4.1,openai,1000000,2.00,8.00
```

自定义模型能力表可以用 JSON：

```json
{
  "models": {
    "internal-agent-v2": {
      "provider": "self-hosted",
      "context_window": 65536,
      "input_cost_per_1m": 0,
      "output_cost_per_1m": 0,
      "supports_tools": true,
      "supports_json_mode": true
    }
  }
}
```

## 迁移规则

当前规则覆盖以下方面：

- 模型能力差异：工具调用、JSON mode、视觉输入、并行工具调用、system prompt、推理强度控制。
- 上下文风险：prompt 估算 token 超过或接近目标模型上下文窗口。
- Prompt 扫描：旧模型名硬编码、旧式 `function_call/functions`、结构化输出缺 schema、过多绝对化约束、采样参数混入 prompt、供应商绑定、XML 工具/思考标签。
- Eval 质量：平均分下降、通过率变化、回归用例比例、缺失 candidate case、严重回归。
- 预算与延迟：月度成本涨幅、eval 成本变化、平均延迟涨幅。

风险分数为 0-100，报告会列出 `low`、`medium`、`high`、`critical` 等级。带 `blocking=true` 的风险会在默认 CI 策略中返回退出码 `2`。

## 报告说明

默认输出到配置里的 `output_dir`。如果未配置，使用 `migration-report/`。示例配置会写到 `outputs/example-report/`。

- `migration-report.md`: 面向人工评审的 Markdown 报告。
- `migration-report.json`: 面向自动化系统的结构化报告。
- `migration-report.sarif`: 面向 GitHub Code Scanning / 安全质量平台的 SARIF 2.1.0 报告。
- `migration-pr-comment.md`: 面向 PR 评论或 GitHub Actions step summary 的精简门禁摘要。

报告包含摘要、模型能力与预算、eval 对比、风险清单、prompt 改造清单、迁移步骤、灰度计划、回滚检查和 CI 判定。SARIF 会把 prompt finding 定位到具体文件和行号；eval 覆盖、质量、预算、延迟和模型能力风险会定位到 candidate eval 或迁移配置文件。

## CI 集成

GitHub Actions 示例已包含在 `.github/workflows/ci.yml`。在你的项目中可以添加：

```yaml
- name: Plan model migration
  run: python -m agent_model_migration_planner plan -c migration-config.json --format both --print-summary
```

当 `risk_threshold` 被触发、存在阻塞项，或 eval 回归超过配置阈值时，命令默认返回 `2`，从而阻止合并或发布。审计阶段可加 `--no-ci-fail` 只生成报告。

上传 SARIF 到 GitHub Code Scanning：

```yaml
- name: Build migration SARIF
  run: python -m agent_model_migration_planner plan -c migration-config.json -o migration-report --format sarif --no-ci-fail
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: migration-report/migration-report.sarif
```

写入 GitHub Actions step summary：

```yaml
- name: Build migration PR summary
  run: |
    python -m agent_model_migration_planner plan -c migration-config.json -o migration-report --format pr-comment --no-ci-fail
    cat migration-report/migration-pr-comment.md >> "$GITHUB_STEP_SUMMARY"
```

如果要让迁移门禁阻断合并，同时也保留可读摘要，可以分两步：第一步 `--format both` 不加 `--no-ci-fail`，第二步用 `if: always()` 生成 `pr-comment` 摘要。

## 限制

- 内置模型能力和价格表用于规划与测试，不承诺代表实时价格或最新供应商规格；生产环境应使用团队自己的价格表和模型能力表覆盖。
- Prompt token 估算使用轻量启发式，不等同于供应商 tokenizer。
- 本工具不调用真实模型，不读取 token，不上传数据，不发布 GitHub。
- Eval 对比依赖输入数据质量；如果 baseline 本身覆盖不足，工具只能提示缺口，不能证明迁移安全。

## 开发指南

运行测试：

```bash
python -m unittest discover -v
```

运行示例：

```bash
python -m agent_model_migration_planner validate -c examples/migration-config.json
python -m agent_model_migration_planner plan -c examples/migration-config.json --no-ci-fail --print-summary
```

项目结构：

- `agent_model_migration_planner/config.py`: 配置解析与校验。
- `agent_model_migration_planner/models.py`: 模型能力/价格表与预算估算。
- `agent_model_migration_planner/prompts.py`: prompt 文件扫描。
- `agent_model_migration_planner/evals.py`: eval baseline/candidate 对比。
- `agent_model_migration_planner/risk.py`: 风险项与综合评分。
- `agent_model_migration_planner/planner.py`: 迁移计划生成。
- `agent_model_migration_planner/reports.py`: Markdown/JSON 报告。
- `agent_model_migration_planner/cli.py`: CLI 入口。

## English

`agent-model-migration-planner` is an open-source Python tool for planning AI agent model migrations. It helps teams that use Codex, Claude Code, custom agents, or multi-model routing across OpenAI, Anthropic, Gemini, and internal models.

The tool reads prompts, migration config, eval baseline/candidate results, and price tables. It produces compatibility risks, prompt rewrite tasks, tool-calling differences, budget impact, eval coverage gaps, rollout steps, rollback checks, Markdown/JSON/SARIF/PR-comment reports, and CI exit codes.

### Use Cases

- Check whether prompts are tied to an old model, old function-calling syntax, vendor-specific behavior, or underspecified structured output.
- Compare eval baseline and candidate results to catch score regressions, missing cases, latency increases, and cost changes.
- Compare source and target model capabilities such as context window, tools, JSON mode, vision, parallel tool calls, system prompts, and reasoning controls.
- Block unsafe migrations in CI while keeping reviewable Markdown, machine-readable JSON, GitHub Code Scanning SARIF, and PR-comment summaries.

### Installation

```bash
python -m pip install -e .
```

Run the module:

```bash
python -m agent_model_migration_planner --help
```

Or use the installed console scripts:

```bash
agent-model-migration-planner --help
amm-plan --help
```

### CLI

Validate a config:

```bash
python -m agent_model_migration_planner validate -c examples/migration-config.json
```

Generate both reports:

```bash
python -m agent_model_migration_planner plan -c examples/migration-config.json --format both --print-summary
```

Generate reports without failing CI:

```bash
python -m agent_model_migration_planner plan -c examples/migration-config.json --no-ci-fail
```

Generate CI-native outputs:

```bash
python -m agent_model_migration_planner plan -c examples/migration-config.json --format sarif --no-ci-fail
python -m agent_model_migration_planner plan -c examples/migration-config.json --format pr-comment --no-ci-fail
```

Print the built-in model catalog:

```bash
python -m agent_model_migration_planner catalog --json
```

Exit codes:

- `0`: migration gate passed.
- `2`: risk threshold, blocking risk, or eval regression failed the gate.
- `3`: invalid config or input data.
- `1`: internal error.

### API

```python
from agent_model_migration_planner import load_config, plan_migration
from agent_model_migration_planner.ci import ci_exit_code
from agent_model_migration_planner.reports import write_json_report, write_markdown_report

config = load_config("examples/migration-config.json")
plan = plan_migration(config)

write_json_report(plan)
write_markdown_report(plan)
exit_code = ci_exit_code(plan)
```

`MigrationPlan.to_dict()` returns the full structured result for release dashboards, pull request bots, or internal governance systems.

### Input Format

The main config is JSON. See `examples/migration-config.json`.

Required fields:

- `project`: project name.
- `source_model`: current model.
- `target_model`: target model.
- `prompts`: list of prompt files or directories.
- `evals.baseline`: baseline eval JSON/CSV.
- `evals.candidate`: candidate eval JSON/CSV.

Optional fields include `budget`, `price_table`, `model_catalog`, `output_dir`, `risk_threshold`, `fail_on_risk`, and `fail_on_eval_regression`.

Prompt files support `.txt`, `.md`, `.prompt`, `.json`, `.yaml`, and `.yml`.

Eval files can be JSON arrays, JSON objects with `results` or `rows`, or CSV files. Recommended columns are `id`, `score`, `passed`, `latency_ms`, `cost_usd`, `input_tokens`, and `output_tokens`.

### Migration Rules

The planner checks model capability changes, context-window risk, prompt migration findings, eval regressions, eval coverage gaps, budget impact, and latency impact. Risk scores range from 0 to 100 and are labeled `low`, `medium`, `high`, or `critical`. Blocking risks fail CI by default.

### Reports

The planner writes reports to `output_dir`; if it is not configured, it uses `migration-report/`.

- `migration-report.md`: a human-readable review document.
- `migration-report.json`: a machine-readable report.
- `migration-report.sarif`: a SARIF 2.1.0 report for GitHub Code Scanning.
- `migration-pr-comment.md`: a concise migration gate summary for pull requests or GitHub Actions step summaries.

Reports include summary, model capability comparison, budget impact, eval comparison, risk list, prompt rewrite checklist, migration steps, rollout plan, rollback checks, and CI gate settings. SARIF output points prompt findings at exact files and lines.

### CI Integration

This repository includes `.github/workflows/ci.yml`. A minimal job step is:

```yaml
- name: Plan model migration
  run: python -m agent_model_migration_planner plan -c migration-config.json --format both --print-summary
```

Use `--no-ci-fail` during audit-only runs.

Use `--format sarif` with `github/codeql-action/upload-sarif@v3` to surface migration risks in Code Scanning. Use `--format pr-comment` when you want a concise PR comment or `$GITHUB_STEP_SUMMARY` artifact. Pass `-o migration-report` in CI when you want stable artifact paths regardless of the config file's `output_dir`.

### Limitations

- Built-in model prices and capabilities are planning defaults, not live provider data. Production teams should provide their own catalog and price table.
- Token estimation is heuristic and does not replace provider tokenizers.
- The tool does not call real models, use API tokens, upload data, or publish to GitHub.
- Eval quality depends on the supplied baseline and candidate files.

### Development

Run tests:

```bash
python -m unittest discover -v
```

Run the example:

```bash
python -m agent_model_migration_planner validate -c examples/migration-config.json
python -m agent_model_migration_planner plan -c examples/migration-config.json --no-ci-fail --print-summary
```
