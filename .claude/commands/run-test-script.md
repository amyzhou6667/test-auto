---
description: 执行 scripts/ 下的 YAML 测试脚本，支持 data_setup 数据构造、steps 逐条执行、API 校验、失败截图与报告。
---

# /run-test-script — 执行持久化测试脚本

从 `scripts/` 目录读取 `.yaml` 格式的测试脚本，逐条执行。

## 自动生成脚本

```bash
# 从需求文档自动生成测试脚本
python yaml_generator.py docs/需求文档.md --output scripts/xxx.yaml

# 生成后直接执行
python yaml_generator.py docs/需求文档.md --run
```

直接执行脚本时可用参数：

```bash
python script_runner.py scripts/xxx.yaml --url http://目标地址 \
  --api-base http://api.目标地址 --retries 1 \
  --project cb-workbench
#   --api-base  API 基站地址(默认取环境变量 TEST_API_BASE,再回退 YAML params.api_base)
#   --retries   每条步骤最多尝试次数,默认 1(失败不重试)
#   --project   产物归属项目(projects/<名>/), 截图/报告/history 写入该项目 out/ 下;
#               缺省读脚本 metadata.project 兜底; 都没有则用仓库根 reports/ 旧路径
```

脚本也可在 `metadata` 里声明归属（CLI `--project` 优先于它）：

```yaml
metadata:
  id: SCRIPT-xxx
  name: 脚本名称
  req: REQ-xxx
  project: cb-workbench   # 可选: 输出归属项目, 不传 --project 时生效
  version: 1.0
```

## 脚本格式

### 数据构造（data_setup）

在测试执行前，先准备所需测试数据。支持两种方式：

```yaml
data_setup:
  # 方式一：通过浏览器 fetch 调用后端 API
  - id: SETUP-001
    name: 创建测试数据
    type: api_call
    request:
      method: POST
      url: "/api/xxx"
      headers:
        Content-Type: application/json
      body: { "key": "value" }
    verify:
      - path: code
        expect: 0

  # 方式二：通过页面操作创建数据
  - id: SETUP-002
    name: 注册新账号
    type: browser_action
    actions:
      - type: navigate
        url: "{base_url}/register"
      - type: fill
        target: "#phone"
        value: "{test_phone}"
      - type: click
        target: button "注册"
```

### 测试步骤（steps）

```yaml
metadata:
  id: SCRIPT-xxx
  name: 脚本名称
  req: REQ-xxx
  version: 1.0

params:
  base_url: http://xxx
  test_amounts:
    - { value: "999", expected_disabled: true }

data_setup:
  - id: SETUP-001
    name: 准备测试账号
    type: api_call
    request:
      method: POST
      url: "/api/auth/register"
      body: { "phone": "{test_phone}" }

steps:
  - id: STEP-001
    name: 步骤名称
    actions:
      - type: navigate
        url: "{base_url}/xxx"
      - type: click
        target: button "xxx"
      - type: fill
        target: "#xxx"
        value: "xxx"
    api_check:
      - url: /api/xxx
        method: GET
        expected_code: 200
        verify:
          - path: code
            expect: 0
```

## 数据构造规则

### api_call 的数据构造

通过 `browser_evaluate` 在浏览器环境执行 `fetch()`，自动携带当前登录态的 token：

```yaml
type: api_call
request:
  method: POST / PUT / DELETE
  url: "/api/xxx"                    # 相对于 API 基站的路径
  headers:                           # 可选，自动带 authorization
    X-Custom: value
  body:                              # 可选
    field1: value1
    field2: value2
```

`api_call` 会自动从页面已有的请求中获取 `authorization` token，注入到请求头。

### browser_action 的数据构造

通过 MCP 浏览器工具完成数据准备，适用于需要登录态或复杂交互的场景。

## 执行流程

```
1. 读取 scripts/*.yaml
2. 解析 metadata 和 params
3. 执行 data_setup（准备测试数据）
4. 逐条执行 steps
5. 输出执行报告
```

## 执行规则

| action type | MCP / 方式 | 说明 |
|------------|------------|------|
| navigate | browser_navigate | 打开页面（可带 wait_until） |
| click | browser_click | 点击元素（可带 wait_for / expect_url） |
| fill | browser_type | 输入文字 |
| assert_text | browser_find | 断言文本存在(支持 `selector`/`target` 字段、`heading "…"` 风格) |
| wait | sleep | 等待（可带 ms） |
| evaluate | browser_evaluate | 执行 JS，返回值可用 path 风格校验 |

## verify 断言块（步骤级，由 script_runner 执行）

每个 step 可带 `verify:` 列表，执行顺序为 **actions → verify → api_check**：

| 字段 | 取值 | 说明 |
|------|------|------|
| element | 元素名 / CSS 选择器 / `heading "…"` / `getByRole(...)` / `getByText(...)` | 定位目标；纯文本自动回退 button role → text |
| should_be | disabled / enabled | 控件状态断言，`expect()` 自动等待 5s（替代固定 sleep） |
| should_exist | true / false | true=可见（自动等待）；false=立即检查不存在（隔离负断言，不等待） |
| text_contains | 文本子串 | 三层回退：真实元素 → 页面级别名（错误提示/toast）→ body |
| condition | 表达式 | 不满足则该项跳过（如 `condition: account_verified == true`） |
| optional | true | 断言失败仅记警告，不判步骤失败 |

```yaml
verify:
  - element: 提交按钮
    should_be: disabled
  - element: 错误提示
    text_contains: "格式不正确"
    optional: true
```

evaluate 动作的 JS 返回值可用 step verify 的 **path 风格**校验：

```yaml
actions:
  - type: evaluate
    code: |
      return { hasVerified: document.body.innerText.includes('已认证') };
verify:
  - path: hasVerified
    expect: true
    condition: account_verified == true
```

## 参数替换

- `{param_name}` → 替换为 params.param_name
- `{index}` → 在 params_ref 循环中替换为当前索引
- 嵌套路径: `{test_account.phone}` → params.test_account.phone

## 报告格式

每条步骤输出：

```
SETUP-001  准备测试账号  ✅
  POST /api/auth/register → 200 OK

STEP-001  步骤名称  ✅ / ❌
  API: /api/xxx → 200 OK ✓
  UI: 元素可见 ✓
```
