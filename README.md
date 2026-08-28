# AI 自动化测试框架

基于 **Playwright + Python** 的 Web UI 自动化测试框架，支持两条测试管线：

1. **需求驱动管线**：Markdown 需求文档 → 自动生成 YAML 测试脚本 → Playwright 执行 → 截图留证 → 失败报告
2. **用例驱动管线**：测试用例文档 → 逐条用例浏览器执行 → 记录结果 → 自动汇总最终报告

## 架构

```
test-auto/
├── yaml_generator.py          # 🎯 管线1: Markdown 需求 → YAML 测试脚本
├── script_runner.py           # 🎯 管线1: Playwright 执行 YAML 脚本（不熔断）
├── execute_test_cases.py      # 🎯 管线2: 测试用例驱动执行（逐条用例跑并记录结果）
├── consolidate_report.py      # 🎯 管线2: 自动发现各模块最新结果 → 合并为最终报告
│
├── scripts/                   # 📋 测试脚本（可自动生成或手写）
│   ├── withdrawal_test.yaml
│   └── auth_realname_test.yaml
│
├── script_templates/          # 📋 测试脚本模板（含多租户隔离模板）
│
├── docs/                      # 📥 输入：需求文档 / 测试用例文档 / 测试夹具
│   ├── CoreBridge_多租户前端工作台测试用例.md
│   ├── test_sales.xlsx        # 上传用例测试数据
│   └── upload-test.txt        # 上传用例测试数据
│
├── screenshots/               # 📤 输出：失败截图
├── reports/                   # 📤 输出：管线1 执行报告 + 管线2 汇总报告
├── results/                   # 📤 输出：管线2 逐用例结果（results_*.json）
│
├── tests/                     # 🧪 框架自身单测（pytest，不依赖浏览器）
│
├── requirements.txt           # 运行依赖（playwright）
├── requirements-dev.txt       # 开发依赖（pytest）
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

#### 管线1：需求 → YAML 测试脚本 → 执行

```powershell
# Step 1: 从需求文档生成 YAML 测试脚本
python yaml_generator.py docs/需求文档.md --output scripts/xxx.yaml

# Step 2: 执行测试脚本（自动打开浏览器，手动登录后逐条运行）
python script_runner.py scripts/xxx.yaml --url http://目标地址 --api-base http://api.目标地址 --retries 1
#   --api-base  API 基站地址(默认取环境变量 TEST_API_BASE,再回退 YAML params.api_base)
#   --retries   每条步骤最多尝试次数,默认 1(失败不重试)

# 一步完成：生成后直接执行
python yaml_generator.py docs/需求文档.md --run
```

#### 管线2：测试用例驱动执行

```powershell
# 执行全部用例（默认所有模块）
python execute_test_cases.py

# 只执行指定模块（TC-I TC-B TC-N TC-ISO TC-UIOP TC-SUPP TC-FAV TC-UPLOAD
#                  TC-RES TC-UX TC-UIOP2 TC-UIOP3 FILEDL FILEDL2 UXFILE）
python execute_test_cases.py TC-I TC-B

# 合并各模块最新运行结果为一份最终报告（自动发现 results/ 下最新结果文件，无需改路径）
python consolidate_report.py
```

`consolidate_report.py` 默认读取 `results/`，也支持 `python consolidate_report.py <results_dir>`。运行结束会打印「结果文件解析」清单，展示每个模块自动发现到了哪个运行文件，便于核对；异常运行（如误报失败的调试运行）可加入脚本顶部的 `BAD_RUNS` 排除。

## 核心特性

| 特性 | 说明 |
|------|------|
| **需求驱动** | 解析 Markdown 需求文档，自动识别输入框/校验规则/API/MUST-NOT 并生成脚本 |
| **用例驱动** | 逐条执行测试用例文档中的用例（TC-I/TC-B/...），结果写入 results/，失败自动截图 |
| **结果自动合并** | `consolidate_report.py` 自动发现各模块最新运行结果，合并为一份汇总报告 |
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
- **运行依赖**（playwright）：`pip install -r requirements.txt`
- **浏览器内核**：`playwright install chromium`（默认驱动系统 Chrome 时无需此步）
- **开发/自测依赖**（跑框架自身单测）：`pip install -r requirements-dev.txt`

## 框架自身单测

框架的纯函数（解析器、选择器解析、断言归一化、条件求值等）有 pytest 单测，不依赖浏览器：

```powershell
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

## 注意事项

- 登录由用户手动完成，`script_runner.py` 内置登录等待（最长 180 秒）；可通过 `params.login_skip_fragment` / `params.login_success_text` 自定义登录判定
- `api_base` 优先级：`--api-base` > 环境变量 `TEST_API_BASE` > YAML `params.api_base` > 从 `base_url` 推导；不推荐硬编码到 YAML
- `--retries N` 可让单条步骤失败后自动重试（默认 1，即不重试）
- 本框架聚焦 E2E 浏览器测试；pytest 单测只覆盖框架自身的纯函数逻辑
