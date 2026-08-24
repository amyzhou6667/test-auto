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

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import yaml
except ImportError:
    os.system("pip install pyyaml -q")
    import yaml

from playwright.async_api import async_playwright

LOGIN_TIMEOUT = 180

class ScriptRunner:
    def __init__(self, script_path: str, base_url: str = None):
        self.script_path = Path(script_path)
        self.base_url = base_url
        self.script = None
        self.params = {}
        self.page = None
        self.browser = None
        self.context = None
        self.results = []
        self.failed_screenshots = []
        self.api_responses = {}
        self.auth_token = None
        self.api_base = None
        self.screenshot_dir = Path(__file__).parent / "screenshots"

    def load_script(self):
        with open(self.script_path, encoding="utf-8") as f:
            self.script = yaml.safe_load(f)
        self.params = self.script.get("params", {})
        if self.base_url:
            self.params["base_url"] = self.base_url
        if "api_base" not in self.params:
            # 从 base_url 推导 api_base
            self.params["api_base"] = "http://nlb-krnq68w0wqo9hkhbtp.cn-hangzhou.nlb.aliyuncsslb.com"
        meta = self.script.get("metadata", {})
        print(f"\n{'='*60}")
        print(f"  脚本: {meta.get('name', self.script_path.name)}")
        print(f"  需求: {meta.get('req', 'N/A')}")
        print(f"  版本: {meta.get('version', '1.0')}")
        print(f"{'='*60}")

    def _resolve(self, text: str) -> str:
        """替换 {param} 占位符"""
        if not isinstance(text, str):
            return text
        result = text
        for key, val in self.params.items():
            if isinstance(val, (str, int, float, bool)):
                result = result.replace(f"{{{key}}}", str(val))
        return result

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
        """捕获 API 响应"""
        url = response.url
        if "/api/" in url:
            try:
                body = await response.json()
                self.api_responses[url] = {
                    "status": response.status,
                    "body": body,
                }
            except:
                pass

    async def manual_login(self):
        """等待用户手动登录"""
        print(f"\n{'='*60}")
        print(f"  [登录] 请在浏览器中完成登录")
        print(f"{'='*60}")

        url = self._resolve(self.params.get("base_url", ""))
        if url:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(2000)

        start = time.monotonic()
        while time.monotonic() - start < LOGIN_TIMEOUT:
            if "login" not in self.page.url.lower():
                print(f"  [OK] 已登录: {self.page.url}")
                # 捕获 auth token
                await self._capture_auth_token()
                return True
            await asyncio.sleep(2)

        print("  [WARN] 登录超时")
        return False

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

        full_url = f"{self.params.get('api_base')}{url_path}"

        try:
            # 使用 Playwright 内置请求（自动带 cookie/session）
            resp = await self.page.request.fetch(full_url, method=method, headers=headers,
                                   data=json.dumps(self._resolve_dict(body)) if body else None)
            status = resp.status
            resp_body = await resp.json()
            await api_context.dispose()

            verified = True
            for check in setup.get("verify", []):
                path = check.get("path", "")
                expect = check.get("expect")
                expect_gt = check.get("expect_gt")
                actual = self._get_nested(resp_body, path)
                if expect is not None and actual != expect:
                    verified = False
                if expect_gt is not None and (actual is None or actual <= expect_gt):
                    verified = False

            icon = "✅" if verified and status == 200 else "❌"
            print(f"  {icon} {sid} {name}")
            if resp_body:
                msg = resp_body.get("message", "")
                print(f"     {method} {url_path} → {status} {msg}")
            else:
                print(f"     {method} {url_path} → {status}")

            # 将 API 响应加入捕获列表，供后续步骤使用
            self.api_responses[full_url] = {"status": status, "body": resp_body}
            status_text = "通过" if verified else "失败"
            self.results.append({"id": sid, "name": name, "status": status_text})

        except Exception as e:
            print(f"  ❌ {sid} {name} — {str(e)[:80]}")
            self.results.append({"id": sid, "name": name, "status": "异常"})

    async def _execute_browser_action(self, setup, sid, name):
        print(f"  ⏳ {sid} {name}...")

    async def execute_steps(self):
        """执行测试步骤"""
        steps = self.script.get("steps", [])
        total = len(steps)
        passed = 0
        failed = 0

        print(f"\n{'='*60}")
        print(f"  执行测试 ({total} 条)")
        print(f"{'='*60}")

        for i, step in enumerate(steps, 1):
            step_id = step.get("id", f"STEP-{i}")
            step_name = self._resolve(step.get("name", ""))
            condition = step.get("condition", "")

            # 检查条件
            if condition:
                try:
                    if not self._eval_condition(condition):
                        print(f"  ⏭️ [{i}/{total}] {step_id} {step_name} (跳过)")
                        self.results.append({"id": step_id, "name": step_name, "status": "跳过"})
                        continue
                except:
                    pass

            print(f"\n  [{i}/{total}] {step_id} {step_name}")

            step_ok = True
            actions = step.get("actions", [])

            for action in actions:
                action_ok = await self._execute_action(action)
                if not action_ok:
                    step_ok = False
                    # 失败时自动截图
                    ss_path = await self.take_screenshot(f"FAIL_{step_id}")
                    if ss_path:
                        print(f"     📸 截图已保存: {ss_path}")
                        self.failed_screenshots.append(ss_path)

            # API 校验
            api_checks = step.get("api_check", [])
            if api_checks:
                await self.page.wait_for_timeout(500)
                api_ok = await self._verify_api(api_checks)
                if not api_ok:
                    step_ok = False

            # 结果
            if step_ok:
                passed += 1
                print(f"  ✅ {step_id} 通过")
                self.results.append({"id": step_id, "name": step_name, "status": "通过"})
            else:
                failed += 1
                print(f"  ❌ {step_id} 失败")
                self.results.append({"id": step_id, "name": step_name, "status": "失败"})

        return passed, failed

    async def _execute_action(self, action):
        """执行单个动作"""
        action_type = action.get("type", "")
        target = str(action.get("target", ""))
        value = self._resolve(str(action.get("value", "")))
        url = self._resolve(str(action.get("url", "")))
        code = action.get("code", "")
        ms = action.get("ms", 0)

        try:
            if action_type == "navigate":
                await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await self.page.wait_for_timeout(1000)

            elif action_type == "click":
                # 解析 Playwright 风格选择器
                target_clean = target.strip('"').strip("'")
                await self._smart_click(target_clean)

            elif action_type == "fill":
                selector = target.strip('"').strip("'")
                await self.page.locator(selector).fill(value)
                await self.page.wait_for_timeout(200)

            elif action_type == "wait":
                await self.page.wait_for_timeout(ms)

            elif action_type == "assert_text":
                text = target.strip('"').strip("'")
                try:
                    await self.page.get_by_text(text).first.wait_for(timeout=5000)
                except:
                    # 尝试用 locator 查找
                    try:
                        await self.page.locator(f"text={text}").first.wait_for(timeout=3000)
                    except:
                        return False

            elif action_type == "evaluate":
                result = await self.page.evaluate(code)
                verify = action.get("verify", {})
                if verify:
                    expect = verify.get("expect")
                    path_gen = verify.get("path", "")
                    actual = self._get_nested(result, path_gen) if path_gen else result
                    if expect is not None and actual != expect:
                        return False

            return True

        except Exception as e:
            print(f"     ⚠️ action 失败: {action_type} → {str(e)[:80]}")
            return False

    async def _smart_click(self, target: str):
        """智能点击：支持 getByRole、getByText、CSS 选择器"""
        # getByRole
        import re
        role_match = re.match(r"getByRole\('button',\s*\{?\s*name:\s*'([^']+)'?\s*}?\)", target)
        if role_match:
            name = role_match.group(1)
            await self.page.get_by_role("button", name=name).click(timeout=5000)
            return

        # getByText
        text_match = re.match(r"getByText\('([^']+)'\)", target)
        if text_match:
            text = text_match.group(1)
            await self.page.get_by_text(text, exact=True).first.click(timeout=5000)
            return

        # 普通 CSS / XPath 选择器
        await self.page.locator(target).first.click(timeout=5000)

    async def _verify_api(self, checks):
        """验证 API 响应"""
        all_ok = True
        await self.page.wait_for_timeout(300)

        for check in checks:
            url_pattern = check.get("url", "")
            expected_code = check.get("expected_code", 200)
            expected_method = check.get("method", "GET")

            # 在捕获的响应中查找匹配
            matched = False
            for api_url, resp in self.api_responses.items():
                if url_pattern in api_url:
                    matched = True
                    status = resp.get("status")
                    body = resp.get("body", {})

                    if status != expected_code:
                        print(f"     ⚠️ API {url_pattern} → {status} (期望 {expected_code})")
                        all_ok = False
                        continue

                    # 验证具体字段
                    for verify in check.get("verify", []):
                        path = verify.get("path", "")
                        expect = verify.get("expect")
                        expect_gt = verify.get("expect_gt")
                        expect_not_empty = verify.get("expect_not_empty", False)
                        actual = self._get_nested(body, path)

                        if expect is not None and actual != expect:
                            print(f"     ⚠️ {url_pattern} {path}={actual} (期望 {expect})")
                            all_ok = False
                        if expect_gt is not None and (actual is None or actual <= expect_gt):
                            all_ok = False
                        if expect_not_empty and not actual:
                            all_ok = False

                    if all_ok:
                        print(f"     ✅ API {url_pattern} → {status}")
                    break

            if not matched:
                print(f"     ⚠️ API {url_pattern} 未捕获到请求")
                all_ok = False

        return all_ok

    def _eval_condition(self, condition: str) -> bool:
        """评估条件表达式"""
        try:
            # 替换变量
            expr = condition
            for key, val in self.params.items():
                if isinstance(val, bool):
                    expr = expr.replace(key, str(val).lower())
                elif isinstance(val, (int, float)):
                    expr = expr.replace(key, str(val))
            # 安全评估
            return eval(expr, {"__builtins__": {}}, {"true": True, "false": False, "True": True, "False": False})
        except:
            return True

    def _get_nested(self, obj, path):
        """从嵌套字典中获取路径值"""
        if not path:
            return obj
        parts = path.split(".")
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return None
        return obj

    def print_report(self, passed, failed, skipped=0):
        meta = self.script.get("metadata", {})
        req = meta.get("req", "N/A")
        script_name = meta.get("name", self.script_path.name)
        total = passed + failed + skipped
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 终端输出
        print(f"\n{'='*60}")
        print(f"  测试报告 — {req}")
        print(f"{'='*60}")
        print(f"  时间: {now}")
        print(f"  总计: {total}  |  通过: {passed}  |  失败: {failed}  |  跳过: {skipped}")
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
    args = parser.parse_args()

    runner = ScriptRunner(args.script, args.url)
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
        passed, failed = await runner.execute_steps()

        # 报告
        runner.print_report(passed, failed)

    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
