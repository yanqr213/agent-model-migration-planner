# Changelog

## 0.2.0 - 2026-06-09

- 新增 `plan --format sarif`，可把模型迁移风险上传到 GitHub Code Scanning。
- 新增 `plan --format pr-comment`，可生成适合 Pull Request 评论或 GitHub Actions step summary 的迁移门禁摘要。
- SARIF 输出会把 prompt finding 定位到具体文件和行号，并把 eval 覆盖、质量、预算、延迟、能力差异风险作为迁移结果记录。
- 补充 CLI、渲染器和 CI smoke 测试。
- 更新中英文 README，加入 SARIF、PR comment 和 GitHub Actions 示例。

## 0.1.0 - 2026-06-08

- Initial public release.
- Added config validation, model catalog and price overrides, prompt scanning, eval comparison, budget impact, risk scoring, rollout steps, rollback checks, Markdown/JSON reports, and CI exit codes.
