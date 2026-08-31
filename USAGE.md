# 测试使用说明

## 启动新需求测试

只需要 3 步：

```
1. 将需求文档 (.md) 放入 docs/
2. 告诉我：测试新需求，地址 http://目标地址，手动登录
3. 浏览器打开后完成登录
```

剩下全部自动完成。

> 管线1（需求驱动）已通用，可复测不同项目。管线2（用例驱动）按项目配置执行：
> `python run_project.py --project <名称> [模块...]`，配置在 `projects/<名称>/project.yaml`。

## 测试覆盖范围

每次测试自动包含：

| 类型 | 内容 |
|------|------|
| 功能验证 | 需求文档列出的所有功能点 |
| 边界测试 | 输入框最小值/最大值/临界值 |
| 异常测试 | 格式错误、超限、空值、特殊字符 |
| API 验证 | 请求参数、响应数据、UI/API 一致性 |
| 状态验证 | 操作前后的数据对比 |
| 负面约束 | NOT 条件 |

## 测试流程

```
需求文档 → 提取测试矩阵 → 浏览器操作 → 捕获 API → 验证结果 → 输出报告
```

## 项目结构

```
├── framework/                     # 通用引擎包（无项目假设）
├── run_project.py                 # 管线2入口: --project <名称> [模块...] / --list / --all
├── run_consolidate.py             # 管线2汇总: --project <名称> [results_dir]
├── yaml_generator.py              # 管线1: 需求文档 → YAML 脚本
├── script_runner.py               # 管线1: 执行 YAML 脚本
├── projects/<名称>/               # 项目目录
│   ├── project.yaml               # 项目配置（账号/选择器/API/模块顺序/报告）
│   ├── hooks/                     # 项目适配层（Runner 子类 + @module 用例模块）
│   ├── fixtures/                  # 测试夹具
│   └── out/                       # 运行产物（results/screenshots/reports）
├── docs/                          # 需求文档
└── .claude/commands/              # Claude Code 斜杠命令（/run-test 等）
```
