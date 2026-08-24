---
description: 从 docs/ 需求文档自动生成 YAML 测试脚本（scripts/*.yaml），识别输入框校验规则、API、MUST/NOT 约束。用法: /export-test-cases docs/需求文档.md
---

# /export-test-cases — 生成测试脚本

从 `docs/` 下的需求文档自动生成可直接执行的 YAML 测试脚本，输出到 `scripts/` 目录。

## 用法

```bash
# 从需求文档生成测试脚本（默认输出到 scripts/<文档名>.yaml）
python yaml_generator.py docs/需求文档.md

# 指定输出路径
python yaml_generator.py docs/需求文档.md --output scripts/xxx.yaml

# 生成后直接执行（自动打开浏览器，手动登录后逐条运行）
python yaml_generator.py docs/需求文档.md --run
```

## 自动识别内容

解析需求文档后自动提取：

| 内容 | 说明 |
|------|------|
| 需求编号/标题 | `REQ-xxx` + 标题 |
| 输入框及校验规则 | 姓名长度、身份证位数、金额倍数等，自动生成边界值/空值/非法值用例 |
| 按钮与操作 | 提交/保存/确认等操作流程 |
| API 端点 | `/api/...` 接口列表，生成 data_setup 与 api_check |
| MUST/NOT 约束 | 必须/不应 条件，生成负面用例 |

## 生成脚本结构

```
metadata:  脚本 ID / 名称 / 需求编号 / 版本
params:    base_url / api_base 等参数
data_setup: 测试数据构造（api_call / browser_action）
steps:    逐条测试步骤（navigate / fill / click / wait / evaluate + verify）
```

生成后可直接用 `/run-test-script` 或 `python script_runner.py scripts/xxx.yaml` 执行。
