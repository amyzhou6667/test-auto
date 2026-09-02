---
description: 测试用例驱动执行（管线2）。从项目配置读取模块，逐条浏览器执行，逐条记录结果，汇总报告。用法: /execute-test-cases
---

# /execute-test-cases — 测试用例驱动执行（管线2）

## 流程

```
项目配置(projects/<名称>/project.yaml) → hooks 模块(15 个 run_TC_*) → 逐模块浏览器执行 → results JSON + 单次报告 → consolidate 汇总报告
```

## 使用

框架已通用化：`python run_project.py --project <项目名> [模块...]`。

```
# 列出项目已注册模块（不执行）
python run_project.py --project corebridge --list

# 执行全部模块（--project 必填, 缺省时列出可用项目）
python run_project.py --project corebridge

# 只执行指定模块（大小写不敏感）
python run_project.py --project corebridge TC-I TC-UIOP3

# 汇总合并报告
python run_consolidate.py --project corebridge
```

旧入口仍可用（等价于 --project corebridge）：`python execute_test_cases.py TC-I`

## 模块与用例编号（CoreBridge 实际实现，与 TC-001/TC-FUNC 分类无关）

| 模块 | 用例范围 | 说明 |
|------|---------|------|
| TC-I | TC-I-01~07 | 登录弹窗与账号绑定 |
| TC-B | TC-B-01~06 | 登录回填/信息完整性/退出 |
| TC-N | TC-N-01~03 | 数据隔离与权限 |
| TC-ISO | TC-ISO-01~24 | 数据隔离（会话/收藏/文件/资源） |
| TC-UIOP | TC-UIOP-01~17 | 统一 UI 操作流 |
| TC-SUPP / TC-FAV / TC-UPLOAD / TC-RES / TC-UX / TC-UIOP2 / TC-UIOP3 / FILEDL / FILEDL2 / UXFILE | 补跑与专项 | 见 project.yaml modules.order |

**执行顺序即覆盖顺序**：`modules.order` 决定报告内容（后执行模块覆盖同 id 的先执行结果），
如 TC-UIOP-08/04/05 由 TC-UIOP3 后覆盖真实结果。跨模块覆盖意图在 project.yaml 有注释文档化。

## 账号与环境变量

- 账号 hex ID 不存仓库：复制 `projects/corebridge/.env.example` 为 `.env` 填入真实值
- 缺失变量启动时会一次性报错列出，不会静默留空
- 依赖浏览器：`playwright install chromium`（headless 由 project.yaml browser 控制）

## 输出

- 单次结果：`projects/<项目名>/out/results/results_{时间戳}.json` + `report_{时间戳}.md`
- 汇总报告：`projects/<项目名>/out/reports/<项目名>_测试报告汇总_*.md`（consolidate 按 BASE/SUPPLEMENTS/DOC_ORDER 自动合并多模块权威结果）
