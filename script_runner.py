#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
YAML 测试脚本自动执行器

读取 scripts/ 下的 .yaml 文件，自动执行所有测试步骤。
登录由用户手动完成，其余全部自动化。

用法:
    python script_runner.py scripts/withdrawal_test.yaml
    python script_runner.py scripts/auth_realname_test.yaml --url http://目标地址
"""
import asyncio
import json
import sys
import os
import re
import time
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

if sys.platform == "win32":
    import io
    # 注意: sys.stdout 包装移入 __main__ 块,避免在 import 时替换导致 pytest capture 失效
    _io = io
else:
    _io = None

try:
    import yaml
except ImportError:
    os.system("pip install pyyaml -q")
    import yaml

from playwright.async_api import async_playwright, expect

LOGIN_TIMEOUT = 180
LOCATOR_TIMEOUT = 5000

# ─────────────────────────────────────────────────────────
# 模块级纯函数(可独立单测,不触碰 playwright)
# ─────────────────────────────────────────────────────────

def _flatten_params(params, prefix=""):
    """把嵌套 params 拍平成 {a.b.c: value} 形式,长 key 优先(避免子串误替换)。"""
    out = {}
    for k, v in params.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten_params(v, key))
        else:
            out[key] = v
    return out


def _params_sorted(params):
    return sorted(_flatten_params(params).items(), key=lambda kv: len(kv[0]), reverse=True)


def get_nested(obj, path):
    """从嵌套字典/对象中获取路径值。
    path 为空或 "result" 时返回原值(兼容 evaluate 标量返回值,修复 P0-4)。"""
    if not path or path == "result":
        return obj
    parts = path.split(".")
    for part in parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def resolve_template(text, params):
    """替换 {param} 占位符,支持嵌套路径 {a.b.c} 与值内嵌套 {x}={other}。非字符串原样返回。"""
    if not isinstance(text, str):
        return text
    result = text
    pairs = list(_params_sorted(params))
    # 迭代解析至多 5 轮,支持 params 值内部再嵌套占位符
    for _ in range(5):
        new = result
        for key, val in pairs:
            if isinstance(val, (str, int, float, bool)):
                new = new.replace(f"{{{key}}}", str(val))
        if new == result:
            break
        result = new
    return result


def eval_condition(condition, params):
    """安全评估条件表达式(布尔/数值参数替换)。未知变量或异常默认返回 True。"""
    if not condition:
        return True
    try:
        expr = str(condition)
        for key, val in _params_sorted(params):
            if isinstance(val, bool):
                expr = expr.replace(key, str(val).lower())
            elif isinstance(val, (int, float)):
                expr = expr.replace(key, str(val))
            elif isinstance(val, str):
                expr = expr.replace(key, f"'{val}'")
        return bool(eval(expr, {"__builtins__": {}}, {"true": True, "false": False, "True": True, "False": False}))
    except Exception:
        return True


def _dequote(s):
    """只剥掉首尾成对的引号(不影响值内部引号,如 button "注册")。"""
    s = (s or "").strip()
    while len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1].strip()
    return s


def parse_locator(spec):
    """把元素说明解析为 locator 描述。
    返回 {"kind": "css"|"heading"|"role"|"text"|"auto", "name": str, "role": str|None}
    优先级: CSS(#/.) → heading "…" → button "…" → getByRole(...) → getByText(...) → auto(纯文本)
    """
    s = _dequote(spec)
    if not s:
        return {"kind": "auto", "name": ""}
    if s.startswith("#") or s.startswith("."):
        return {"kind": "css", "name": s}
    m = re.fullmatch(r'heading\s+"([^"]+)"', s)
    if m:
        return {"kind": "heading", "name": m.group(1)}
    m = re.fullmatch(r'button\s+"([^"]+)"', s)
    if m:
        return {"kind": "role", "role": "button", "name": m.group(1)}
    m = re.fullmatch(r"getByRole\('(\w+)',\s*\{?\s*name:\s*'([^']+)'?\s*\}?\)", s)
    if m:
        return {"kind": "role", "role": m.group(1), "name": m.group(2)}
    m = re.fullmatch(r"getByText\('([^']+)'\)", s)
    if m:
        return {"kind": "text", "name": m.group(1)}
    return {"kind": "auto", "name": s}


def parse_click_target(target):
    """解析 click 目标。返回 {"kind": "role"|"text"|"css", "role": str|None, "name": str}"""
    s = _dequote(target)
    parsed = parse_locator(s)
    if parsed["kind"] == "role":
        return {"kind": "role", "role": parsed["role"], "name": parsed["name"]}
    if parsed["kind"] == "text":
        return {"kind": "text", "role": None, "name": parsed["name"]}
    if parsed["kind"] == "heading":
        return {"kind": "role", "role": "heading", "name": parsed["name"]}
    return {"kind": "css", "role": None, "name": s}


# 页面级标签别名: 用于 text_contains 断言的区域回退
PAGE_REGION_ALIASES = {
    "错误提示": "body", "错误信息": "body", "提示": "body",
    "toast": ".ant-message, .el-message, .el-notification, .toast",
    "message": ".ant-message, .el-message",
}


def interpret_verify_item(item):
    """把 step.verify 的一项归一化,返回 {"spec", "checks", "optional", "condition"}。
    checks: [(assertion, expected)] — disabled/enabled/exist/not_exist/text_contains,可组合。"""
    item = item or {}
    spec = str(item.get("element") or item.get("selector") or item.get("target") or "")
    checks = []
    should_be = item.get("should_be")
    if should_be in ("disabled", "enabled"):
        checks.append((should_be, True))
    if "should_exist" in item:
        exist = bool(item.get("should_exist"))
        checks.append(("exist" if exist else "not_exist", exist))
    if item.get("text_contains") is not None:
        checks.append(("text_contains", item.get("text_contains")))
    if not checks:
        checks.append(("exist", True))
    return {"spec": spec, "checks": checks,
            "optional": bool(item.get("optional", False)), "condition": item.get("condition")}


def evaluate_verify_result(result, verify_list, params):
    """评估 evaluate action 的 verify 列表(纯函数)。
    修复: path 为空或 result 且结果是标量 → 直接比较 result。
    每条 verify 先判断 condition,false 则跳过。返回 (all_ok, first_failure_msg)。"""
    if not verify_list:
        return True, ""
    for item in verify_list:
        cond = item.get("condition")
        if cond and not eval_condition(cond, params):
            continue
        path = item.get("path", "") or "result"
        expect_val = item.get("expect")
        expect_gt = item.get("expect_gt")
        expect_not = item.get("expect_not")
        expect_not_empty = item.get("expect_not_empty", False)
        actual = get_nested(result, path)
        if expect_val is not None and actual != expect_val:
            return False, f"{path}={actual!r} (期望 {expect_val!r})"
        if expect_gt is not None and (actual is None or not isinstance(actual, (int, float)) or actual <= expect_gt):
            return False, f"{path}={actual!r} (期望 > {expect_gt})"
        if expect_not is not None and actual == expect_not:
            return False, f"{path}={actual!r} (不应等于 {expect_not!r})"
        if expect_not_empty and not actual:
            return False, f"{path} 为空"
    return True, ""


def _stringify(obj):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (list, dict)):
        return json.dumps(obj, ensure_ascii=False)
    return "" if obj is None else str(obj)


def verify_api_field(body, item):
    """验证 API 响应字段(纯函数)。
    支持 expect / expect_gt / expect_not / expect_not_empty / expect_contain / expect_not_contain。"""
    item = item or {}
    path = item.get("path", "")
    actual = get_nested(body, path)
    expect_val = item.get("expect")
    expect_gt = item.get("expect_gt")
    expect_not = item.get("expect_not")
    expect_not_empty = item.get("expect_not_empty", False)
    expect_contain = item.get("expect_contain")
    expect_not_contain = item.get("expect_not_contain")

    if expect_val is not None and actual != expect_val:
        return False, f"{path}={actual!r} (期望 {expect_val!r})"
    if expect_gt is not None and (actual is None or not isinstance(actual, (int, float)) or actual <= expect_gt):
        return False, f"{path}={actual!r} (期望 > {expect_gt})"
    if expect_not is not None and actual == expect_not:
        return False, f"{path}={actual!r} (不应等于 {expect_not!r})"
    if expect_not_empty and not actual:
        return False, f"{path} 为空"
    if expect_contain is not None:
        if expect_contain not in _stringify(actual):
            return False, f"{path} 不包含 {expect_contain!r}"
    if expect_not_contain is not None:
        if expect_not_contain in _stringify(actual):
            return False, f"{path} 不应包含 {expect_not_contain!r}"
    return True, ""


def find_api_match(api_responses, url_pattern):
    """在捕获的响应字典中按子串匹配 URL,返回首个命中响应或 None。"""
    if not url_pattern:
        return None
    for api_url, resp in api_responses.items():
        if url_pattern in api_url:
            return resp
    return None


class ScriptRunner:
    def __init__(self, script_path: str, base_url: str = None, api_base: str = None, retries: int = 1):
        self.script_path = Path(script_path)
        self.base_url = base_url
        self.api_base_cli = api_base
        self.retries = max(1, int(retries))
        self.script = None
        self.params = {}
        self.page = None
        self.browser = None
        self.context = None
        self.results = []
        self.setup_results = []
        self.failed_screenshots = []
        self.api_responses = {}
        self.auth_token = None
        self.api_base = None
        self._screenshotted_steps = set()
        self._last_evaluate_result = None
        self.screenshot_dir = Path(__file__).parent / "screenshots"

    def load_script(self):
        with open(self.script_path, encoding="utf-8") as f:
            self.script = yaml.safe_load(f)
        self.params = self.script.get("params", {})
        if self.base_url:
            self.params["base_url"] = self.base_url
        # api_base 优先级: CLI --api-base > 环境变量 TEST_API_BASE > YAML params.api_base > 从 base_url 推导 > 无默认
        api_base = self.api_base_cli
        if not api_base:
            api_base = os.environ.get("TEST_API_BASE", "").strip()
        if not api_base:
            api_base = str(self.params.get("api_base", "")).strip()
        if not api_base:
            parsed = urlparse(str(self.params.get("base_url", "")))
            if parsed.scheme and parsed.netloc:
                api_base = f"{parsed.scheme}://{parsed.netloc}"
        if api_base:
            self.params["api_base"] = api_base
        else:
            print("  [WARN] 未配置 api_base(可用 --api-base 或环境变量 TEST_API_BASE 指定)")
        meta = self.script.get("metadata", {})
        print(f"\n{'='*60}")
        print(f"  脚本: {meta.get('name', self.script_path.name)}")
        print(f"  需求: {meta.get('req', 'N/A')}")
        print(f"  版本: {meta.get('version', '1.0')}")
        print(f"{'='*60}")

    def _resolve(self, text: str) -> str:
        """替换 {param} 占位符(支持嵌套路径,委托模块级 resolve_template)"""
        return resolve_template(text, self.params)

    def _resolve_dict(self, d: dict) -> dict:
        """递归替换字典中的占位符"""
        if isinstance(d, dict):
            return {k: self._resolve_dict(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [self._resolve_dict(i) for i in d]
        elif isinstance(d, str):
            return self._resolve(d)
        return d

    async def start_browser(self):
        p = await async_playwright().start()
        self.browser = await p.chromium.launch(headless=False, channel="chrome")
        self.context = await self.browser.new_context(viewport={"width": 1920, "height": 1080})
        self.page = await self.context.new_page()

        # 监听网络请求，自动捕获 API 响应
        self.page.on("response", self._capture_response)
        print("[OK] 浏览器已启动")

    async def _capture_response(self, response):
        """捕获 API 响应(JSON 优先,text 兜底,非 JSON 响应不丢失)"""
        url = response.url
        if "/api/" not in url:
            return
        entry = {"status": response.status, "content_type": response.headers.get("content-type", "")}
        try:
            entry["body"] = await response.json()
        except Exception:
            try:
                entry["body"] = await response.text()
            except Exception:
                entry["body"] = None
        self.api_responses[url] = entry

    async def manual_login(self):
        """等待用户手动登录。
        判定: params.login_success_text 命中页面文本,或 URL 不再包含 params.login_skip_fragment(默认 "login")。"""
        print(f"\n{'='*60}")
        print(f"  [登录] 请在浏览器中完成登录")
        print(f"{'='*60}")

        url = self._resolve(self.params.get("base_url", ""))
        if url:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(2000)

        login_frag = str(self.params.get("login_skip_fragment", "login"))
        success_text = str(self.params.get("login_success_text", ""))

        start = time.monotonic()
        while time.monotonic() - start < LOGIN_TIMEOUT:
            if self._is_logged_in(login_frag, success_text):
                print(f"  [OK] 已登录: {self.page.url}")
                # 捕获 auth token
                await self._capture_auth_token()
                return True
            await asyncio.sleep(2)

        print("  [WARN] 登录超时")
        return False

    def _is_logged_in(self, login_frag: str, success_text: str) -> bool:
        """登录判定: success_text 命中页面文本优先,否则按 URL 是否含 login 片段。"""
        if success_text:
            try:
                if success_text in self.page.content()[:20000]:
                    return True
            except Exception:
                pass
        if not login_frag:
            return False
        return login_frag not in self.page.url.lower()

    async def _capture_auth_token(self):
        """从页面 localStorage 或 cookie 中捕获 auth token"""
        for key in ["access_token", "token", "auth_token", "jwt", "authorization"]:
            try:
                token = await self.page.evaluate(f"localStorage.getItem('{key}')")
                if token:
                    self.auth_token = token
                    print(f"  [token] 已捕获 (key={key})")
                    return
            except:
                pass
        # 从 cookie 尝试
        try:
            cookies = await self.context.cookies()
            for c in cookies:
                if "token" in c["name"].lower() or "auth" in c["name"].lower():
                    self.auth_token = c["value"]
                    print(f"  [token] 已从 cookie 捕获")
                    return
        except:
            pass

    async def execute_data_setup(self):
        """执行数据构造步骤"""
        setups = self.script.get("data_setup", [])
        if not setups:
            return

        print(f"\n{'='*60}")
        print(f"  数据构造")
        print(f"{'='*60}")

        for setup in setups:
            if setup.get("enabled") == False:
                print(f"  [跳过] {setup.get('name')} (已禁用)")
                continue

            condition = setup.get("condition", "")
            if condition and not self._eval_condition(condition):
                print(f"  [跳过] {setup.get('name')} (条件不满足)")
                continue

            setup_type = setup.get("type")
            setup_id = setup.get("id", "?")
            setup_name = setup.get("name", "")

            if setup_type == "api_call":
                await self._execute_api_call(setup, setup_id, setup_name)
            elif setup_type == "browser_action":
                await self._execute_browser_action(setup, setup_id, setup_name)

    async def _execute_api_call(self, setup, sid, name):
        """通过 Playwright 内置请求调用 API（自动带登录态）"""
        req = setup.get("request", {})
        method = req.get("method", "GET")
        url_path = req.get("url", "")
        headers = req.get("headers", {})
        body = req.get("body")

        api_base = self.params.get("api_base", "")
        full_url = f"{api_base}{url_path}"

        try:
            # 使用 Playwright 内置请求（自动带 cookie/session,共享单例,不可 dispose）
            resp = await self.page.request.fetch(full_url, method=method, headers=headers,
                                   data=json.dumps(self._resolve_dict(body)) if body else None)
            status = resp.status
            try:
                resp_body = await resp.json()
            except Exception:
                text = await resp.text()
                try:
                    resp_body = json.loads(text)
                except Exception:
                    resp_body = {"raw": text[:500]}

            verified = True
            for check in setup.get("verify", []):
                ok, msg = verify_api_field(resp_body, check)
                if not ok:
                    verified = False
                    print(f"     ⚠️ {url_path} {msg}")

            icon = "✅" if verified and status == 200 else "❌"
            print(f"  {icon} {sid} {name}")
            if isinstance(resp_body, dict) and resp_body.get("message"):
                msg = resp_body.get("message")
                print(f"     {method} {url_path} → {status} {msg}")
            else:
                print(f"     {method} {url_path} → {status}")

            # 将 API 响应加入捕获列表，供后续步骤使用
            self.api_responses[full_url] = {"status": status, "body": resp_body}
            status_text = "通过" if verified else "失败"
            self.setup_results.append({"id": sid, "name": name, "status": status_text})

        except Exception as e:
            print(f"  ❌ {sid} {name} — {str(e)[:80]}")
            self.setup_results.append({"id": sid, "name": name, "status": "异常"})

    async def _execute_browser_action(self, setup, sid, name):
        """通过页面操作构造测试数据(复用 _execute_action 执行 actions 列表)"""
        print(f"  ⏳ {sid} {name}...")
        ok = True
        for action in setup.get("actions", []):
            if not await self._execute_action(action):
                ok = False
                await self._record_failure(sid)
        if ok and setup.get("verify"):
            ok, _ = await self._verify_step(setup["verify"], sid)
        icon = "✅" if ok else "❌"
        print(f"  {icon} {sid} {name}")
        self.setup_results.append({"id": sid, "name": name, "status": "通过" if ok else "失败"})

    async def execute_steps(self):
        """执行测试步骤,返回 (passed, failed, skipped)。skipped 真实计数。"""
        steps = self.script.get("steps", [])
        total = len(steps)
        passed = 0
        failed = 0
        skipped = 0

        print(f"\n{'='*60}")
        print(f"  执行测试 ({total} 条)")
        print(f"{'='*60}")

        for i, step in enumerate(steps, 1):
            step_id = step.get("id", f"STEP-{i}")
            step_name = self._resolve(step.get("name", ""))
            status = await self._run_single_step(step, step_id, i, total)
            if status == "通过":
                passed += 1
            elif status == "失败":
                failed += 1
            else:
                skipped += 1
            self.results.append({"id": step_id, "name": step_name, "status": status})

        return passed, failed, skipped

    async def _run_single_step(self, step, step_id, i, total):
        """执行单条 step,返回 "通过"|"失败"|"跳过"。含 step 级 condition、actions、verify、api_check、重试。"""
        step_name = self._resolve(step.get("name", ""))

        condition = step.get("condition", "")
        if condition and not self._eval_condition(condition):
            print(f"  ⏭️ [{i}/{total}] {step_id} {step_name} (跳过)")
            return "跳过"

        print(f"\n  [{i}/{total}] {step_id} {step_name}")

        # 每步重置 evaluate 结果缓存,path 风格 verify 只引用本步的 evaluate
        self._last_evaluate_result = None

        attempts = 0
        while attempts < self.retries:
            attempts += 1
            if await self._run_step_once(step, step_id):
                print(f"  ✅ {step_id} 通过")
                return "通过"
            if attempts < self.retries:
                print(f"  🔄 [{i}/{total}] {step_id} 失败,重试 {attempts}/{self.retries}...")
                await self.page.wait_for_timeout(500)

        print(f"  ❌ {step_id} 失败")
        return "失败"

    async def _run_step_once(self, step, step_id):
        """单次执行: actions → verify(UI 断言) → api_check(API 校验)。任一失败即步骤失败。"""
        step_ok = True

        # 1. actions(页面操作)
        for action in step.get("actions", []):
            if not await self._execute_action(action):
                step_ok = False
                await self._record_failure(step_id)

        # 2. verify(UI 状态断言,接入 step["verify"] 修复死代码问题)
        if step.get("verify"):
            verify_ok, _ = await self._verify_step(step["verify"], step_id)
            if not verify_ok:
                step_ok = False
                await self._record_failure(step_id)

        # 3. api_check(异步网络副作用,轮询等待响应)
        if step.get("api_check"):
            if not await self._verify_api(step["api_check"], step_id):
                step_ok = False
                await self._record_failure(step_id)

        return step_ok

    async def _verify_step(self, verify_list, step_id):
        """执行 step 级 verify 断言,返回 (all_ok, first_failure_msg)。
        支持两种风格: element 风格(元素/文本/按钮)与 path 风格(校验本步 evaluate 的 JS 结果)。
        每项支持 condition(不满足跳过)/ optional(失败仅警告)。"""
        all_ok = True
        first_fail = ""
        for raw_item in verify_list:
            item = self._resolve_dict(raw_item) if isinstance(raw_item, dict) else raw_item
            # path 风格: 校验最近一次 evaluate 的返回值(如 auth UI-002)
            if isinstance(item, dict) and item.get("path") is not None:
                ok, msg = evaluate_verify_result(self._last_evaluate_result, [item], self.params)
                if not ok:
                    if item.get("optional"):
                        print(f"     ⚠️ (可选) {msg}")
                    else:
                        print(f"     ⚠️ {msg}")
                        all_ok = False
                        if not first_fail:
                            first_fail = msg
                continue
            parsed = interpret_verify_item(item)
            if parsed["condition"] is not None and not self._eval_condition(parsed["condition"]):
                print(f"     ⏭️ verify 跳过(条件不满足): {parsed['spec'] or ''}")
                continue
            for assertion, expected in parsed["checks"]:
                ok, msg = await self._assert_verify_item(parsed["spec"], assertion, expected)
                if not ok:
                    if parsed["optional"]:
                        print(f"     ⚠️ (可选) {msg}")
                    else:
                        print(f"     ⚠️ {msg}")
                        all_ok = False
                        if not first_fail:
                            first_fail = msg
        return all_ok, first_fail

    async def _assert_verify_item(self, spec, assertion, expected):
        """对单个 verify 断言执行,返回 (ok, message)。用 expect() 自动等待替代固定 sleep。"""
        alias_key = (spec or "").strip()
        try:
            if assertion == "text_contains":
                return await self._assert_text_contains(spec, expected)
            # 页面级别名(错误提示/toast 等)的"存在"语义含糊,真正的断言是 text_contains,直接跳过
            if assertion == "exist" and alias_key in PAGE_REGION_ALIASES:
                return True, ""
            locators = await self._locator_candidates(parse_locator(spec))
            if assertion == "disabled":
                loc = await self._first_present(locators)
                if loc is None:
                    return False, f"元素未找到: {spec}"
                await expect(loc).to_be_disabled(timeout=LOCATOR_TIMEOUT)
                return True, ""
            if assertion == "enabled":
                loc = await self._first_present(locators)
                if loc is None:
                    return False, f"元素未找到: {spec}"
                await expect(loc).to_be_enabled(timeout=LOCATOR_TIMEOUT)
                return True, ""
            if assertion == "exist":
                loc = await self._first_present(locators)
                if loc is None:
                    return False, f"元素未找到: {spec}"
                await expect(loc).to_be_visible(timeout=LOCATOR_TIMEOUT)
                return True, ""
            if assertion == "not_exist":
                # 负断言立即检查(不等待),契合"B 租户看不到 A 数据"的隔离语义
                total = 0
                for loc in locators:
                    total += await loc.count()
                if total > 0:
                    return False, f"元素不应存在: {spec}"
                return True, ""
        except Exception as e:
            return False, f"断言失败 {spec}: {str(e)[:80]}"
        return True, ""

    async def _assert_text_contains(self, spec, substring):
        """text_contains 三层回退: 真实元素 → 页面级别名区域 → body。"""
        if not substring:
            return True, ""
        alias_key = (spec or "").strip()
        parsed = parse_locator(spec)
        # 1) 真实元素(含 auto 的 text 候选,用 .first 规避 strict 多匹配)
        for loc in await self._locator_candidates(parsed):
            try:
                if await loc.count() > 0:
                    await expect(loc.first).to_contain_text(substring, timeout=LOCATOR_TIMEOUT)
                    return True, ""
            except Exception:
                continue
        # 2) 页面级别名区域
        if alias_key in PAGE_REGION_ALIASES:
            await expect(self.page.locator(PAGE_REGION_ALIASES[alias_key])).to_contain_text(substring, timeout=LOCATOR_TIMEOUT)
            return True, ""
        # 3) 兜底 body
        await expect(self.page.locator("body")).to_contain_text(substring, timeout=LOCATOR_TIMEOUT)
        return True, ""

    async def _locator_candidates(self, parsed):
        """按解析结果构造候选 locator 列表。auto 类型回退: button role → text。"""
        kind = parsed["kind"]
        name = parsed["name"]
        if kind == "css":
            return [self.page.locator(name)]
        if kind == "heading":
            return [self.page.get_by_role("heading", name=name)]
        if kind == "role":
            return [self.page.get_by_role(parsed["role"], name=name)]
        if kind == "text":
            return [self.page.get_by_text(name, exact=False)]
        return [self.page.get_by_role("button", name=name), self.page.get_by_text(name, exact=False)]

    async def _first_present(self, locators):
        """返回候选 locator 中第一个存在(count>0)的(取 .first 规避 strict 多匹配),否则 None。"""
        for loc in locators:
            try:
                if await loc.count() > 0:
                    return loc.first
            except Exception:
                pass
        return None

    async def _record_failure(self, step_id):
        """同一步骤内首个失败点截图一次(去重)。"""
        if step_id in self._screenshotted_steps:
            return
        self._screenshotted_steps.add(step_id)
        ss_path = await self.take_screenshot(f"FAIL_{step_id}")
        if ss_path:
            self.failed_screenshots.append(ss_path)
            print(f"     📸 截图已保存: {ss_path}")

    async def _execute_action(self, action):
        """执行单个动作。fill/navigate 依赖 Playwright 自带 actionability,不再固定 sleep。"""
        action_type = action.get("type", "")
        target = str(action.get("target", ""))
        value = self._resolve(str(action.get("value", "")))
        url = self._resolve(str(action.get("url", "")))
        code = action.get("code", "")
        ms = action.get("ms", 0)

        try:
            if action_type == "navigate":
                wait_until = action.get("wait_until", "domcontentloaded")
                await self.page.goto(url, wait_until=wait_until, timeout=30000)

            elif action_type == "click":
                await self._smart_click(target)
                wait_for = action.get("wait_for")
                expect_url = action.get("expect_url")
                if wait_for:
                    await self.page.locator(wait_for).first.wait_for(state="visible", timeout=LOCATOR_TIMEOUT)
                elif expect_url:
                    await expect(self.page).to_have_url(re.compile(expect_url), timeout=LOCATOR_TIMEOUT)
                else:
                    await self.page.wait_for_timeout(200)

            elif action_type == "fill":
                selector = _dequote(target)
                await self.page.locator(selector).fill(value)

            elif action_type == "wait":
                await self.page.wait_for_timeout(ms)

            elif action_type == "assert_text":
                return await self._action_assert_text(action)

            elif action_type == "evaluate":
                return await self._action_evaluate(action, code)

            return True

        except Exception as e:
            print(f"     ⚠️ action 失败: {action_type} → {str(e)[:80]}")
            return False

    async def _action_assert_text(self, action):
        """assert_text: 兼容 selector 与 target 字段,支持 heading "…" 等 parse_locator 风格。"""
        spec = _dequote(str(action.get("selector") or action.get("target") or ""))
        parsed = parse_locator(spec)
        should_exist = action.get("should_exist", True)
        locators = await self._locator_candidates(parsed)
        if should_exist is False:
            total = 0
            for loc in locators:
                total += await loc.count()
            return total == 0
        loc = await self._first_present(locators)
        if loc is None:
            return False
        await expect(loc).to_be_visible(timeout=LOCATOR_TIMEOUT)
        return True

    async def _action_evaluate(self, action, code):
        """evaluate: 走 evaluate_verify_result,修复标量 path:result,honor 每条 verify 的 condition。"""
        result = await self.page.evaluate(code)
        self._last_evaluate_result = result
        verify = action.get("verify", [])
        if not verify:
            return True
        ok, msg = evaluate_verify_result(result, verify, self.params)
        if not ok:
            print(f"     ⚠️ evaluate 校验失败: {msg}")
            return False
        return True

    async def _smart_click(self, target: str):
        """智能点击: 支持 getByRole / getByText / heading / button "…" / CSS(委托 parse_click_target)"""
        parsed = parse_click_target(target)
        if parsed["kind"] == "role":
            await self.page.get_by_role(parsed["role"], name=parsed["name"]).click(timeout=5000)
            return
        if parsed["kind"] == "text":
            await self.page.get_by_text(parsed["name"], exact=True).first.click(timeout=5000)
            return
        # 普通 CSS / XPath 选择器
        await self.page.locator(parsed["name"]).first.click(timeout=5000)

    async def _verify_api(self, checks, step_id=""):
        """验证 API 响应: 逐 check 轮询等待响应出现(替代固定 sleep),字段断言走 verify_api_field。"""
        all_ok = True
        for raw_check in checks:
            check = self._resolve_dict(raw_check) if isinstance(raw_check, dict) else raw_check
            url_pattern = check.get("url", "")
            expected_code = check.get("expected_code", 200)

            resp = await self._wait_for_api(url_pattern)
            if resp is None:
                print(f"     ⚠️ API {url_pattern} 未捕获到请求")
                all_ok = False
                continue

            status = resp.get("status")
            body = resp.get("body", {})

            if status != expected_code:
                print(f"     ⚠️ API {url_pattern} → {status} (期望 {expected_code})")
                all_ok = False
                continue

            check_ok = True
            for verify in check.get("verify", []):
                ok, msg = verify_api_field(body, verify)
                if not ok:
                    print(f"     ⚠️ {url_pattern} {msg}")
                    check_ok = False
                    all_ok = False

            if check_ok:
                print(f"     ✅ API {url_pattern} → {status}")

        return all_ok

    async def _wait_for_api(self, url_pattern, timeout_ms=5000):
        """轮询 self.api_responses 直到出现匹配响应或超时(替代固定 sleep)。"""
        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < deadline:
            resp = find_api_match(self.api_responses, url_pattern)
            if resp is not None:
                return resp
            await asyncio.sleep(0.1)
        return None

    def _eval_condition(self, condition: str) -> bool:
        """评估条件表达式(委托模块级 eval_condition)"""
        return eval_condition(condition, self.params)

    def _get_nested(self, obj, path):
        """从嵌套字典中获取路径值(委托模块级 get_nested,兼容 evaluate 标量)"""
        return get_nested(obj, path)

    def print_report(self, passed, failed, skipped=0):
        meta = self.script.get("metadata", {})
        req = meta.get("req", "N/A")
        script_name = meta.get("name", self.script_path.name)
        total = passed + failed + skipped
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S%f")

        # 终端输出
        print(f"\n{'='*60}")
        print(f"  测试报告 — {req}")
        print(f"{'='*60}")
        print(f"  时间: {now}")
        print(f"  总计: {total}  |  通过: {passed}  |  失败: {failed}  |  跳过: {skipped}")
        if self.setup_results:
            setup_fail = sum(1 for r in self.setup_results if r["status"] != "通过")
            print(f"  数据构造: {len(self.setup_results)} 条 (失败 {setup_fail})")
        print(f"{'='*60}")

        for r in self.results:
            icon = {"通过": "✅", "失败": "❌", "跳过": "⏭️", "异常": "⚠️"}
            print(f"  {icon.get(r['status'], '❓')} {r['id']} {r['name']}")

        # 保存结构化报告
        report_dir = Path(__file__).parent / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{timestamp}_{req}.md"

        lines = [
            f"# 测试报告 — {req}",
            f"",
            f"**脚本:** {script_name}",
            f"**时间:** {now}",
            f"**总计:** {total}  |  **通过:** {passed}  |  **失败:** {failed}  |  **跳过:** {skipped}",
            f"",
            f"## 逐条结果",
            f"",
            f"| 编号 | 名称 | 结果 |",
            f"|------|------|------|",
        ]
        for r in self.results:
            icon_map = {"通过": "✅", "失败": "❌", "跳过": "⏭️", "异常": "⚠️"}
            icon = icon_map.get(r["status"], "❓")
            lines.append(f"| {r['id']} | {r['name']} | {icon} {r['status']} |")

        lines.extend(["", "---", f"*由 script_runner.py 自动生成 | {now}*", ""])

        # 追加失败截图
        if self.failed_screenshots:
            lines.extend(["", "## 失败截图", ""])
            for ss in self.failed_screenshots:
                lines.append(f"![]({ss})")
            lines.append("")

        report_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n  📄 报告已保存: {report_path}")

        # 失败截图统计
        if self.failed_screenshots:
            print(f"  📸 失败截图: {len(self.failed_screenshots)} 张")

        # 汇总追加到历史记录
        history_path = report_dir / "_history.csv"
        if not history_path.exists():
            history_path.write_text("时间,需求,脚本,总计,通过,失败,跳过\n", encoding="utf-8")
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(f"{now},{req},{script_name},{total},{passed},{failed},{skipped}\n")

    async def take_screenshot(self, name: str) -> str:
        """截图保存，返回文件路径"""
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%H%M%S")
        filename = f"{name}_{ts}.png"
        path = self.screenshot_dir / filename
        try:
            await self.page.screenshot(path=str(path))
            return str(path)
        except:
            return ""

    async def close(self):
        if self.browser:
            await self.browser.close()


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="YAML 测试脚本自动执行器")
    parser.add_argument("script", help="测试脚本路径 (scripts/xxx.yaml)")
    parser.add_argument("--url", help="目标地址，覆盖 params.base_url")
    parser.add_argument("--api-base", help="API 基站地址，覆盖 params.api_base(默认取环境变量 TEST_API_BASE)")
    parser.add_argument("--retries", type=int, default=1, help="每条步骤最多尝试次数(默认 1,即失败不重试)")
    args = parser.parse_args()

    runner = ScriptRunner(args.script, args.url, args.api_base, args.retries)
    runner.load_script()

    try:
        await runner.start_browser()

        # 手动登录
        if not await runner.manual_login():
            print("[FAIL] 未登录，退出")
            return

        # 数据构造
        await runner.execute_data_setup()

        # 执行测试
        passed, failed, skipped = await runner.execute_steps()

        # 报告
        runner.print_report(passed, failed, skipped)

    finally:
        await runner.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    asyncio.run(main())
