# AI 自动化测试框架

基于 **Playwright + Python** 的 Web UI 自动化测试框架，支持两条测试管线，**一套框架可复测不同项目**：

1. **需求驱动管线**：Markdown 需求文档 → 自动生成 YAML 测试脚本 → Playwright 执行 → 截图留证 → 失败报告（已通用）
2. **用例驱动管线**：项目配置 + 用例模块 → 逐条用例浏览器执行 → 记录结果 → 自动汇总最终报告（**通用引擎 + 项目配置，`--project` 切换**）

## 架构

```
test-auto/
├── framework/                   # 🎯 通用引擎包（无项目假设）
│   ├── config.py                #    project.yaml 加载 / ${ENV} 注入 / 路径解析
│   ├── engine.py                #    Result + Runner 基座 + run_case_table 调度
│   ├── registry.py              #    @module 装饰器注册
│   ├── report.py                #    save_report / build_markdown
│   ├── consolidate.py           #    汇总报告算法骨架（读项目配置）
│   ├── loader.py / cli.py / util.py
│
├── run_project.py               # 🎯 管线2入口: python run_project.py --project <名> [模块...] / --list / --all
├── run_consolidate.py           # 🎯 管线2汇总: python run_consolidate.py --project <名> [results_dir]
│
├── yaml_generator.py            # 🎯 管线1: Markdown 需求 → YAML 测试脚本
├── script_runner.py             # 🎯 管线1: Playwright 执行 YAML 脚本（不熔断）
│
├── projects/                    # 📂 项目目录（每项目一份配置 + 专属 hooks）
│   ├── corebridge/              #    第一个项目: project.yaml + hooks/ + fixtures/ + out/
│   │   ├── project.yaml         #    全部抽配置项(账号/选择器/API/模块顺序/报告)
│   │   ├── hooks/               #    Python 适配层(专属 DOM + 15 个用例模块)
│   │   ├── fixtures/            #    测试夹具(upload-test.txt / test_sales.xlsx)
│   │   └── out/                 #    运行产物(results/screenshots/reports, gitignore)
│   └── demo/                    #    最小假项目(验证引擎通用接入, 不碰浏览器)
│
├── legacy/                      # 📦 通用化前单体版备份(execute_test_cases_v1.py 等, 备查)
│
├── execute_test_cases.py        # 🚫 兼容壳(deprecated, 转调 run_project.py)
├── consolidate_report.py        # 🚫 兼容壳(deprecated, 转调 run_consolidate.py)
│
├── scripts/                     # 📋 管线1测试脚本（可自动生成或手写）
├── script_templates/            # 📋 测试脚本模板（含多租户隔离模板）
├── docs/                        # 📥 输入：需求文档 / 测试用例文档（夹具已迁 projects/*/fixtures/）
│
├── tests/                       # 🧪 框架自身单测（pytest，不依赖浏览器）
│
├── requirements.txt             # 运行依赖（playwright）
├── requirements-dev.txt         # 开发依赖（pytest）
│
└── .claude/                     # 🤖 Claude Code 集成
    └── commands/                # 斜杠命令（在 Claude Code 里直接 /命令名 调用）
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

#### 管线2：测试用例驱动执行（通用引擎 + 项目配置）

```powershell
# 列出项目已注册模块（不执行）
python run_project.py --project corebridge --list

# 执行全部模块（--project 缺省 corebridge）
python run_project.py --project corebridge

# 只执行指定模块（大小写不敏感）
python run_project.py --project corebridge TC-I TC-UIOP3

# 合并各模块最新运行结果为一份最终报告（自动发现 out/results/ 下最新结果文件）
python run_consolidate.py --project corebridge
```

旧入口兼容：`python execute_test_cases.py TC-I` / `python consolidate_report.py` 仍可用（等价 `--project corebridge`）。

**新增项目**：复制 `projects/demo/` 或 `projects/corebridge/` 目录 → 改 `project.yaml`（账号/选择器/API/模块顺序/报告配置）+ 写 `hooks/modules/*.py`（`@module` 注册）→ `python run_project.py --project <名称> --list` 验证 → 执行。无需改 Python 引擎。

`consolidate` 按项目配置的 BASE/SUPPLEMENTS/DOC_ORDER 自动发现各模块权威运行并合并；异常运行（如误报失败的调试运行）加入配置 `report.bad_runs` 排除。运行结束打印「结果文件解析」清单便于核对。

## 核心特性

| 特性 | 说明 |
|------|------|
| **需求驱动** | 解析 Markdown 需求文档，自动识别输入框/校验规则/API/MUST-NOT 并生成脚本 |
| **用例驱动** | 逐条执行项目配置的用例模块（TC-I/TC-ISO/...），结果写入 out/results/，失败自动截图 |
| **多项目复用** | 通用引擎 + `projects/<名称>/project.yaml` + hooks，`--project` 切换，新增项目不改 Python |
| **账号安全** | 账号 hex ID 经 `${ENV_VAR}` 注入，仓库不存真实账号（复制 `.env.example` 为 `.env`） |
| **结果自动合并** | `run_consolidate.py` 按项目配置自动发现各模块最新运行结果，合并为一份汇总报告 |
| **不熔断** | 单条用例/单模块失败不中断后续执行（per-case / per-module try/except） |
| **边界自动生成** | 每个输入框自动生成 正常值/边界值/异常值/空值 用例（管线1） |
| **失败截图** | 失败时自动截图，写入报告（文件名含序号防同秒覆盖） |
| **手动登录** | 浏览器打开后由用户完成登录，自动捕获登录态/token |

## 项目配置与环境变量

`projects/<名称>/project.yaml` 集中管理全部抽配置项：

- **project**：名称/标题/adapter 类（`hooks.adapter.<Runner子类>`）
- **paths**：cases/fixtures/results/screenshots/reports（相对项目根）
- **browser**：headless/channel/viewport
- **base_url / api_base**：支持 `${ENV_VAR}` 注入，可带默认值 `${VAR:-默认}`
- **accounts**：账号结构（标量 tenant / u-X 用 tenants 列表），hex ID 走 `${ENV}`，不存仓库
- **api**：token 键 / 请求计数前缀 / 响应嗅探规则表 / 上传响应路径 / API 路径模板 / 上传关键词
- **modules.order**：执行顺序即覆盖顺序（后执行模块覆盖同 id 先执行结果）
- **report / consolidate / status**：标题/地址/结论/DOC_ORDER/BASE/SUPPLEMENTS/状态枚举图标与统计口径

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
