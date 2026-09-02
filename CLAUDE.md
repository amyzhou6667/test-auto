# CLAUDE.md — 本仓库工作指引（优先省 token）

基于 Playwright + Python 的 Web UI 自动化测试框架，**一套引擎可复测多项目**。两条管线：

- **管线1（需求驱动）**：`yaml_generator.py` + `script_runner.py`（已通用，不用改）
- **管线2（用例驱动）**：`run_project.py` + `framework/` 引擎 + `projects/<名称>/` 项目配置（核心）

## ⚠️ 省 token 铁律（先读这个）

以下内容**不要通读**，会白白烧 token：

| 不要读 | 原因 | 替代做法 |
|---|---|---|
| `projects/corebridge/hooks/modules/*.py`（15 个文件 ~1650 行） | 是 execute_test_cases v1 的 1:1 迁移，行为等价 | 要看模块清单：`python run_project.py --project corebridge --list`；要看配置：读 `projects/corebridge/project.yaml` |
| `legacy/` | 通用化前单体备份（gitignore，含明文 ID），仅供比对参考 | 不需要看 |
| `projects/*/out/`、`results/`、`reports/`、`screenshots/`、`.playwright-mcp/` | 每次运行的产物/截图 | 不读，除非用户要看具体截图 |
| `probe_*.py` | 一次性探针（gitignore） | 不读 |
| `docs/CoreBridge_...md` 全文 | 账号已迁 .env，文档是脱敏后的用例说明 | 按需读，不整篇加载 |

**默认工作方式**：
- 项目相关配置 → 读 `projects/<名称>/project.yaml`（单一事实源）
- 模块/用例信息 → 跑 `--list`，不要读 hooks 源码
- 验证改动 → 跑 `python -m pytest tests/ -q`（72 个单测，纯函数无浏览器），不要逐个读测试文件
- CoreBridge 专属细节 → 查记忆文件 `corebridge-testing-notes.md` / `corebridge-test-url.md`（紧凑）

## 快速导航

```
framework/       通用引擎（config/engine/registry/report/consolidate/loader/cli/util）
run_project.py   管线2入口: --project <名> [模块...] / --list / --all
run_consolidate.py  汇总入口: --project <名> [results_dir]
projects/
  corebridge/    第一个项目（project.yaml + hooks/ + fixtures/ + .env.example）
  demo/          最小假项目（零浏览器依赖，验证引擎通用性）
execute_test_cases.py / consolidate_report.py   兼容壳(deprecated, 转调 run_project/run_consolidate)
yaml_generator.py / script_runner.py  管线1（已通用, 勿改纯函数签名——会打破 15 个单测）
tests/           72 个单测（29 旧 + 43 新），不依赖浏览器
```

## 常用命令

```bash
python -m pytest tests/ -q                          # 单测（唯一推荐的验证方式）
python run_project.py --project corebridge --list   # 看模块清单（省 token 首选）
python run_project.py --project corebridge TC-I     # 跑单模块（真实浏览器, 需 .env 有账号）
python run_project.py --project corebridge --smoke  # 只跑冒烟集 (modules.smoke)
python run_consolidate.py --project corebridge      # 汇总报告
python run_project.py --project demo                # demo 假项目（不碰浏览器, 验证引擎）
```

## 新增项目怎么做

复制 `projects/demo/` → 改 `project.yaml`（项目名/地址/账号/模块顺序/报告）→ 在 `hooks/` 写 `@module` 模块。
全程不改 `framework/` 与 `run_project.py`。详见 README「新增项目指南」；需要时让 Claude 搭骨架，不要自己读全部 hooks 参考。

## 安全约定

- 账号 hex ID 只在 `projects/<名>/.env`（gitignore），仓库与 git 历史零明文；project.yaml 用 `${ENV_VAR}`
- 不要打印 `.env` 内容或把账号值写入任何文件/回复
