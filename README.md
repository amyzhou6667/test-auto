# AI 自动化测试框架

基于 **Playwright + Python** 的 Web UI 自动化测试框架，支持**需求文档驱动的测试管线**：
Markdown 需求文档 → 自动生成 YAML 测试脚本 → Playwright 执行 → 截图留证 → 失败报告

## 架构

```
test-auto/
├── yaml_generator.py          # 🎯 Step 1: Markdown 需求 → YAML 测试脚本
├── script_runner.py           # 🎯 Step 2: Playwright 执行 YAML 脚本（不熔断）
├── scripts/                   # 📋 测试脚本（可自动生成或手写）
│   ├── withdrawal_test.yaml
│   └── auth_realname_test.yaml
│
├── docs/                      # 📥 输入：需求文档（Markdown）
│   ├── REQ-078-对话模块优化.md
│   └── REQ-079-备案信息显示.md
│
├── screenshots/               # 📤 输出：失败截图
├── reports/                   # 📤 输出：执行报告（Markdown + _history.csv）
│
└── .claude/                   # 🤖 Claude Code 集成
    └── commands/              # 斜杠命令（在 Claude Code 里直接 /命令名 调用）
        ├── run-test.md            # /run-test            自然语言全流程测试
        ├── execute-test-cases.md  # /execute-test-cases  测试用例驱动执行
        ├── export-test-cases.md   # /export-test-cases   需求 → 生成测试脚本
        └── run-test-script.md     # /run-test-script     执行 scripts/*.yaml
```

## 快速开始

### 方式一：Claude Code 斜杠命令（推荐）

```bash
# 在 Claude Code 中直接输入：
/run-test 测试一下 http://目标地址，需要手动登录
```

| 命令 | 说明 |
|------|------|
| `/run-test` | 自然语言全流程测试：读取 docs/ 需求 → 测试矩阵 → 浏览器执行 → 报告 |
| `/execute-test-cases` | 测试用例驱动：逐条用例执行并记录通过/失败 |
| `/export-test-cases` | 从需求文档生成测试脚本（scripts/*.yaml） |
| `/run-test-script` | 执行 scripts/ 下的 YAML 测试脚本 |

### 方式二：命令行执行

```powershell
# Step 1: 从需求文档生成 YAML 测试脚本
python yaml_generator.py docs/需求文档.md --output scripts/xxx.yaml

# Step 2: 执行测试脚本（自动打开浏览器，手动登录后逐条运行）
python script_runner.py scripts/xxx.yaml --url http://目标地址

# 一步完成：生成后直接执行
python yaml_generator.py docs/需求文档.md --run
```

## 核心特性

| 特性 | 说明 |
|------|------|
| **需求驱动** | 解析 Markdown 需求文档，自动识别输入框/校验规则/API/MUST-NOT 并生成脚本 |
| **不熔断** | 单条用例失败不会中断后续执行，每个步骤独立 try/except |
| **边界自动生成** | 每个输入框自动生成 正常值/边界值/异常值/空值 用例 |
| **失败截图** | 失败时自动截图，写入报告 |
| **自动报告** | 执行结果生成 reports/*.md，并追加 _history.csv 历史 |
| **手动登录** | 浏览器打开后由用户完成登录，自动捕获登录态/token |

## 测试脚本 YAML 格式

`scripts/*.yaml` 由 `metadata` / `params` / `data_setup` / `steps` 组成：

- **metadata**：脚本 ID、名称、关联需求（REQ-xxx）、版本
- **params**：`base_url`、`api_base` 等参数，步骤中通过 `{param_name}` 引用
- **data_setup**：测试数据构造（`api_call` 自动携带登录态调后端 / `browser_action` 页面操作造数）
- **steps**：逐条测试步骤，每步含 actions 与可选 verify / api_check

完整格式说明见 `.claude/commands/run-test-script.md`。

## 环境要求

- **Python 3.10+**
- **Playwright**（安装：`pip install playwright && playwright install chromium`）
- **Chrome 浏览器**（Playwright 驱动）

## 注意事项

- 登录由用户手动完成，`script_runner.py` 内置登录等待（最长 180 秒）
- `api_base` 默认值在 `script_runner.py` 中硬编码，可通过 YAML 的 `params.api_base` 或按需修改
- 本框架聚焦 E2E 浏览器测试，不涉及 Python 单元测试 pytest/unittest
