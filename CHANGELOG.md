# 功能变动记录

> 每次框架/项目的功能变动都在此记录，由 `/record-change` 命令自动维护。
> 格式：倒序（最新在前），每条含日期、类型、影响范围、详细说明。

---

<!-- 变动记录从这里开始，新条目插入到本行下方 -->

## 2026-09-04 — 新增功能变动记录 skill (`/record-change`)

- **类型**: feat
- **范围**: commands / docs
- **改动文件**:
  - `.claude/commands/record-change.md` — 新建斜杠命令，5 步流程：分析变动→写入 CHANGELOG→识别文档→同步更新→汇总报告
  - `CHANGELOG.md` — 新建功能变动专属文档，倒序记录，含日期/类型/范围/文件/详情
  - `CLAUDE.md` — 快速导航增加 CHANGELOG.md、常用命令增加 /record-change、默认工作方式增加查 CHANGELOG 指引
- **详情**: 创建了 `/record-change` 斜杠命令，每次功能改动后执行该命令即可自动将变动记录到 CHANGELOG.md，并根据影响范围同步更新 CLAUDE.md、USAGE.md、project.yaml 注释等相关文档
- **关联文档**: `CLAUDE.md`（已同步）、`USAGE.md`（需检查）
