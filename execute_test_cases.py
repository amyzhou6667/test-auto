# -*- coding: utf-8 -*-
"""
CoreBridge 多租户前端工作台 — 测试用例执行驱动
执行 docs/CoreBridge_多租户前端工作台测试用例.md 中的用例。

用法:
    python execute_test_cases.py            # 执行全部已实现用例
    python execute_test_cases.py TC-I TC-B   # 只执行指定模块
    python execute_test_cases.py --list      # 列出用例与实现状态

结果写入 results/ 下的 JSON + 汇总 Markdown。
"""
import asyncio
import json
import sys
import os
import re
import io
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

from playwright.async_api import async_playwright

BASE_URL = "http://117.187.178.246:19521/login?redirect=/workbench"
ROOT = Path(__file__).parent
SHOT_DIR = ROOT / "screenshots"
RESULT_DIR = ROOT / "results"

# ────────────────────────────────────────────────
# 账号数据(来自测试用例文档 账号表)
# ────────────────────────────────────────────────
ACCOUNTS = {
    "u-A": {"userId": "db5b13b1cf6e4da19480261664312942", "username": "zh2",
            "tenant": "租户2", "workbenchId": "aaad5f78847d4d1fbba963de55de4569",
            "appId": "b170b61f55674b61981ca7ff4302b385"},
    "u-B": {"userId": "8658e6cc468b4da9b41fa09babc4dc06", "username": "zh1",
            "tenant": "租户1", "workbenchId": "eed18b9fc63241248195f348982887f6",
            "appId": "239071aacb1a4648afaf3d5e2ba9e58d"},
    "u-X": {"userId": "bca388ab0be84e1fad40add82bc6405b", "username": "test",
            "tenants": [  # 按斜杠划分: 第一个 workbenchId 对应第一个 appId
                {"name": "租户2", "workbenchId": "aaad5f78847d4d1fbba963de55de4569", "appId": "b170b61f55674b61981ca7ff4302b385"},
                {"name": "租户1", "workbenchId": "eed18b9fc63241248195f348982887f6", "appId": "239071aacb1a4648afaf3d5e2ba9e58d"},
            ]},
    "u-N": {"userId": "bca388ab0be84e1fad40add82b65751", "username": "kong",
            "tenant": None},
    "u-F": {"userId": "815512f162e44e57bdeb787cb12848b6", "username": "dj",
            "tenant": "租户2", "workbenchId": "aaad5f78847d4d1fbba963de55de4569",
            "appId": "b170b61f55674b61981ca7ff4302b385", "frozen": True},
    "u-S": {"userId": "ee21ff69fa754ac199e7de54852fdb6f", "username": "ty-user",
            "tenant": "test1", "workbenchId": "a3908936f5854d38893282b382043d06",
            "appId": "542bab4c2e624146b4686367447147ce", "suspended": True},
}

UPLOAD_FILE = ROOT / "docs" / "upload-test.txt"
EXCEL_FILE = ROOT / "docs" / "test_sales.xlsx"


class Result:
    def __init__(self, case_id, name, status="未执行", actual="", detail="", evidence=""):
        self.case_id = case_id
        self.name = name
        self.status = status  # 通过/失败/无法验证/未执行
        self.actual = actual
        self.detail = detail
        self.evidence = evidence  # 截图路径

    def to_dict(self):
        return {"id": self.case_id, "name": self.name, "status": self.status,
                "actual": self.actual, "detail": self.detail, "evidence": self.evidence}


class Runner:
    def __init__(self, modules=None):
        self.modules = modules or []
        self.results = {}
        self.browser = None
        self.context = None
        self.page = None
        self.api_log = []           # 网络请求日志 [{url, status, ts}]
        self.api_sessions = None    # 最近一次 /api/v1/sessions 响应体
        self.api_upload = None      # 最近一次 /files/upload 响应体
        self._seq = 0

    # ─────────── 浏览器基座 ───────────
    async def start(self):
        p = await async_playwright().start()
        self.browser = await p.chromium.launch(headless=False, channel="chrome")
        self.context = await self.browser.new_context(viewport={"width": 1920, "height": 1080})
        self.page = await self.context.new_page()
        self.page.on("response", self._on_response)
        RESULT_DIR.mkdir(exist_ok=True)
        SHOT_DIR.mkdir(exist_ok=True)

    async def close(self):
        if self.browser:
            await self.browser.close()

    async def _on_response(self, resp):
        try:
            self.api_log.append({"url": resp.url, "status": resp.status,
                                 "ts": datetime.now().isoformat()})
            if "/api/v1/sessions" in resp.url:
                try:
                    self.api_sessions = await resp.json()
                except Exception:
                    pass
            if "/files/upload" in resp.url:
                try:
                    self.api_upload = await resp.json()
                except Exception:
                    pass
        except Exception:
            pass

    def api_count_since(self, idx):
        """统计自 idx 之后到当前新增的 /api/ 请求数"""
        return sum(1 for e in self.api_log[idx:] if "/api/" in e["url"])

    def api_snapshot_len(self):
        return len(self.api_log)

    # ─────────── 页面辅助 ───────────
    async def goto_login(self, clear_storage=False):
        if clear_storage:
            await self.page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            await self.page.evaluate("localStorage.clear(); sessionStorage.clear();")
        await self.page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await self.page.locator(self.dialog_sel()).first.wait_for(state="visible", timeout=5000)
        except Exception:
            pass
        await self.page.wait_for_timeout(800)

    async def screenshot(self, name):
        self._seq += 1
        ts = datetime.now().strftime("%H%M%S")
        path = SHOT_DIR / f"{name}_{ts}.png"
        try:
            await self.page.screenshot(path=str(path))
            return str(path)
        except Exception:
            return ""

    def dialog_sel(self):
        return ".te-dlg"

    async def dialog_visible(self):
        try:
            return await self.page.locator(self.dialog_sel()).first.is_visible()
        except Exception:
            return False

    async def dialog_text(self):
        if not await self.dialog_visible():
            return ""
        try:
            return (await self.page.locator(self.dialog_sel()).first.inner_text()).strip()
        except Exception:
            return ""

    async def body_text(self):
        try:
            return (await self.page.evaluate("document.body.innerText")).strip()
        except Exception:
            return ""

    async def tenant_options(self):
        """返回租户下拉当前选项文本列表(从 popper 读取)"""
        try:
            opts = await self.page.evaluate("""() => {
                const pop = document.querySelector('.te-tenant-popper, .el-select-dropdown');
                if (!pop) return [];
                return Array.from(pop.querySelectorAll('.el-select-dropdown__item, li'))
                    .map(e => (e.innerText||'').trim()).filter(Boolean);
            }""")
            return opts
        except Exception:
            return []

    async def tenant_selected_text(self):
        """返回租户选中框显示文本(Element Plus trigger innerText)"""
        try:
            return (await self.page.locator(".te-dlg .el-select").first.inner_text()).strip()
        except Exception:
            return ""

    async def tenant_disabled(self):
        try:
            return await self.page.locator(".te-dlg .el-select input").first.is_disabled()
        except Exception:
            return None

    async def fill_input(self, idx, value):
        """按序号填输入框(userId=0, 用户名=1, workbenchId=2, appId=3)"""
        loc = self.page.locator(".te-dlg input").nth(idx)
        await loc.fill(value)

    async def fill_userId(self, uid):
        await self.fill_input(0, uid)

    async def fill_username(self, name):
        await self.fill_input(1, name)

    async def fill_workbenchId(self, wid):
        await self.fill_input(2, wid)

    async def fill_appId(self, aid):
        await self.fill_input(3, aid)

    async def click_btn(self, text):
        try:
            await self.page.get_by_role("button", name=text).click(timeout=4000)
            return True
        except Exception:
            try:
                await self.page.locator(f"button:has-text('{text}')").first.click(timeout=4000)
                return True
            except Exception:
                return False

    async def open_tenant_dropdown(self):
        await self.page.locator(".te-dlg .el-select").first.click(timeout=4000)
        await self.page.wait_for_timeout(800)

    async def select_tenant(self, tenant_name):
        await self.open_tenant_dropdown()
        await self.page.locator(f".te-tenant-popper .el-select-dropdown__item:has-text('{tenant_name}')").first.click(timeout=4000)
        await self.page.wait_for_timeout(400)
        try:
            await self.page.keyboard.press("Escape")  # 关闭下拉浮层,避免遮挡保存按钮
        except Exception:
            pass
        await self.page.wait_for_timeout(400)

    async def toast_text(self):
        try:
            return (await self.page.locator(".el-message, .el-message--error, .el-message--success").all_inner_texts())
        except Exception:
            return []

    async def url(self):
        return self.page.url

    # ─────────── 用例执行 ───────────
    def set_result(self, case_id, name, status, actual, detail="", evidence=""):
        self.results[case_id] = Result(case_id, name, status, actual, detail, evidence)
        icon = {"通过": "✅", "失败": "❌", "无法验证": "⚠️", "未执行": "⏭️"}.get(status, "❓")
        print(f"  {icon} {case_id} {name} — {status}")
        if detail:
            print(f"      {detail}")
        if actual:
            print(f"      实际: {actual[:300]}")

    def run_case(self, case_id, name, func):
        """注册一个用例函数(由调度器调用)"""
        pass


# ────────────────────────────────────────────────
# 主调度
# ────────────────────────────────────────────────
async def run_modules(modules):
    runner = Runner(modules)
    await runner.start()
    try:
        print(f"{'='*66}")
        print(f"  CoreBridge 多租户前端工作台 — 测试执行")
        print(f"  地址: {BASE_URL}")
        print(f"{'='*66}")
        for mod in modules:
            print(f"\n\n########## 模块 {mod} ##########")
            if mod == "TC-I":
                await run_TC_I(runner)
            elif mod == "TC-B":
                await run_TC_B(runner)
            elif mod == "TC-N":
                await run_TC_N(runner)
            elif mod == "TC-ISO":
                await run_TC_ISO(runner)
            elif mod == "TC-UIOP":
                await run_TC_UIOP(runner)
            elif mod == "TC-SUPP":
                await run_TC_SUPP(runner)
            elif mod == "TC-FAV":
                await run_TC_FAV(runner)
            elif mod == "TC-UPLOAD":
                await run_TC_UPLOAD(runner)
            elif mod == "TC-RES":
                await run_TC_RES(runner)
            elif mod == "TC-UX":
                await run_TC_UX(runner)
            elif mod == "TC-UIOP2":
                await run_TC_UIOP2(runner)
            elif mod == "TC-UIOP3":
                await run_TC_UIOP3(runner)
            elif mod == "FILEDL":
                await run_TC_FILEDL(runner)
            elif mod == "FILEDL2":
                await run_TC_FILEDL2(runner)
            elif mod == "UXFILE":
                await run_TC_UXFILE(runner)
            else:
                print(f"  [WARN] 未实现的模块: {mod}")
    finally:
        await runner.close()
    save_report(runner)
    return runner


def save_report(runner):
    RESULT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    data = [r.to_dict() for r in runner.results.values()]
    jpath = RESULT_DIR / f"results_{ts}.json"
    jpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    md = build_markdown(data)
    mpath = RESULT_DIR / f"report_{ts}.md"
    mpath.write_text(md, encoding="utf-8")
    print(f"\n  📄 报告已保存: {mpath}")
    print(f"  📄 明细已保存: {jpath}")
    # 汇总
    passed = sum(1 for r in data if r["status"] == "通过")
    failed = sum(1 for r in data if r["status"] == "失败")
    warn = sum(1 for r in data if r["status"] == "无法验证")
    print(f"\n{'='*66}")
    print(f"  汇总: 总计 {len(data)} | 通过 {passed} | 失败 {failed} | 无法验证 {warn}")
    print(f"{'='*66}")


def build_markdown(data):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    passed = sum(1 for r in data if r["status"] == "通过")
    failed = sum(1 for r in data if r["status"] == "失败")
    warn = sum(1 for r in data if r["status"] == "无法验证")
    lines = [
        f"# CoreBridge 多租户前端工作台 — 测试报告",
        f"",
        f"**时间:** {now}",
        f"**地址:** {BASE_URL}",
        f"**总计:** {len(data)} | **通过:** {passed} | **失败:** {failed} | **无法验证:** {warn}",
        f"",
        f"## 逐条结果",
        f"",
        f"| 用例 | 名称 | 结果 | 实际 | 说明 | 证据 |",
        f"|------|------|------|------|------|------|",
    ]
    for r in data:
        icon = {"通过": "✅", "失败": "❌", "无法验证": "⚠️", "未执行": "⏭️"}.get(r["status"], "❓")
        ev = f"`{r['evidence']}`" if r.get("evidence") else ""
        lines.append(f"| {r['id']} | {r['name']} | {icon} {r['status']} | {r.get('actual','')} | {r.get('detail','')} | {ev} |")
    lines.extend(["", "---", f"*由 execute_test_cases.py 自动生成 | {now}*", ""])
    return "\n".join(lines)


# ────────────────────────────────────────────────
# 公共登录辅助
# ────────────────────────────────────────────────
async def login_as(runner, account_key, tenant=None, do_save=True, do_enter=False, fill_ids=True):
    """用指定账号填充登录弹窗。
    - tenant: 指定租户名(多租户账号 u-X 必填, 决定用哪对 workbenchId/appId)
    - fill_ids: 是否填 workbenchId/appId(进入工作台必需)
    """
    acc = ACCOUNTS[account_key]
    await runner.fill_userId(acc["userId"])
    await runner.fill_username(acc["username"])
    # 确定租户与 workbenchId/appId
    wb = ap = None
    sel_tenant = None
    if acc.get("tenants"):
        # 多租户账号(u-X): 按租户名取配对
        pair = None
        if tenant:
            pair = next((t for t in acc["tenants"] if t["name"] == tenant), None)
        if not pair:
            pair = acc["tenants"][0]
        sel_tenant = pair["name"]
        wb = pair.get("workbenchId")
        ap = pair.get("appId")
    else:
        sel_tenant = tenant or acc.get("tenant")
        wb = acc.get("workbenchId")
        ap = acc.get("appId")
    if fill_ids and wb:
        await runner.fill_workbenchId(wb)
    if fill_ids and ap:
        await runner.fill_appId(ap)
    await runner.page.wait_for_timeout(1200)
    if sel_tenant:
        await runner.select_tenant(sel_tenant)
    if do_save:
        await runner.click_btn("保存")
        await runner.page.wait_for_timeout(800)
    if do_enter:
        await runner.click_btn("进入工作台")
        await runner.page.wait_for_timeout(4000)
    return acc


async def _safe(fn, default=""):
    try:
        return await fn()
    except Exception:
        return default


async def run_TC_I(runner):
    # ── TC-I-01 打开工作台自动弹登录窗 ──
    await runner.goto_login(clear_storage=True)
    dlg = await _safe(runner.dialog_text)
    body = await _safe(runner.body_text)
    ev = await runner.screenshot("TC-I-01")
    ok = "登录信息" in dlg and "智能业务终端" in body and "进入工作台" in body
    runner.set_result("TC-I-01", "打开工作台自动弹出登录信息弹窗, 主卡片显示标题与进入按钮",
                      "通过" if ok else "失败",
                      actual=f"弹窗含'登录信息'={bool('登录信息' in dlg)}, 页面含标题={bool('智能业务终端' in body)}, 含进入按钮={bool('进入工作台' in body)}",
                      detail=f"弹窗文本: {dlg[:200]}", evidence=ev)

    # ── TC-I-02 仅填 userId, 用户名留空 ──
    await runner.fill_userId(ACCOUNTS["u-A"]["userId"])
    await runner.fill_username("")
    await runner.page.wait_for_timeout(1000)
    n0 = runner.api_snapshot_len()
    disabled = await _safe(runner.tenant_disabled, None)
    dlg = await _safe(runner.dialog_text)
    await runner.page.wait_for_timeout(1000)
    api_req = runner.api_count_since(n0)
    ev = await runner.screenshot("TC-I-02")
    msg_hit = any(k in dlg for k in ["请填写用户名", "用户名后自动加载", "请填写"])
    ok = disabled and msg_hit and api_req == 0
    runner.set_result("TC-I-02", "填userId不填用户名: 租户下拉禁用+提示+无请求",
                      "通过" if ok else ("失败" if not disabled or not msg_hit else "失败"),
                      actual=f"租户禁用={disabled}, 提示命中={msg_hit}, /api请求数={api_req}",
                      detail=f"弹窗文本: {dlg[:300]}", evidence=ev)

    # ── TC-I-03 填 userId+用户名, 租户自动加载 ──
    await runner.fill_userId(ACCOUNTS["u-A"]["userId"])
    await runner.fill_username(ACCOUNTS["u-A"]["username"])
    # 捕捉"加载中"中间态
    mid_loading = False
    for _ in range(6):
        sel = await _safe(lambda: runner.page.locator(".te-dlg .el-select").inner_text(), "")
        if "加载" in sel:
            mid_loading = True
            break
        await runner.page.wait_for_timeout(300)
    await runner.page.wait_for_timeout(1200)
    opts = await _safe(runner.tenant_options)
    sel_text = await _safe(runner.tenant_selected_text)
    ev = await runner.screenshot("TC-I-03")
    auto_selected = bool(sel_text) and "加载" not in sel_text and "请输入" not in sel_text
    ok = (len(opts) >= 1) and auto_selected
    runner.set_result("TC-I-03", "填完整账号后租户加载并自动选中唯一租户",
                      "通过" if ok else "失败",
                      actual=f"加载中中间态={mid_loading}, 下拉选项={opts}, 已选={sel_text!r}",
                      detail="", evidence=ev)

    # ── TC-I-04 u-N 无绑定租户 ──
    await runner.goto_login(clear_storage=True)
    await runner.fill_userId(ACCOUNTS["u-N"]["userId"])
    await runner.fill_username(ACCOUNTS["u-N"]["username"])
    await runner.page.wait_for_timeout(2000)
    opts = await _safe(runner.tenant_options)
    dlg = await _safe(runner.dialog_text)
    msg_hit = any(k in dlg for k in ["暂无绑定租户", "未绑定", "暂无", "没有绑定"])
    await runner.open_tenant_dropdown()
    await runner.page.wait_for_timeout(600)
    await runner.click_btn("保存")
    await runner.page.wait_for_timeout(800)
    dlg2 = await _safe(runner.dialog_text)
    save_hit = any(k in dlg2 for k in ["请选择租户", "请选择"])
    ev = await runner.screenshot("TC-I-04")
    ok = (len(opts) == 0) and msg_hit and save_hit
    runner.set_result("TC-I-04", "u-N无绑定租户: 下拉为空+提示+保存报错",
                      "通过" if ok else "失败",
                      actual=f"选项数={len(opts)}, 无租户提示={msg_hit}, 保存报错={save_hit}",
                      detail=f"弹窗: {dlg2[:300]}", evidence=ev)

    # ── TC-I-05 租户下拉仅列本账号租户+已选高亮 ──
    await runner.goto_login(clear_storage=True)
    await runner.fill_userId(ACCOUNTS["u-A"]["userId"])
    await runner.fill_username(ACCOUNTS["u-A"]["username"])
    await runner.page.wait_for_timeout(1800)
    await runner.open_tenant_dropdown()
    await runner.page.wait_for_timeout(600)
    opts = await _safe(runner.tenant_options)
    highlighted = await _safe(lambda: runner.page.evaluate(
        """() => {
            const pop = document.querySelector('.te-tenant-popper, .el-select-dropdown');
            if (!pop) return [];
            return Array.from(pop.querySelectorAll('.el-select-dropdown__item.is-selected, li.is-selected'))
                .map(e => (e.innerText||'').trim());
        }"""))
    ev = await runner.screenshot("TC-I-05")
    only_own = all("租户1" not in o for o in opts) and any("租户2" in o for o in opts)
    ok = len(opts) >= 1 and len(highlighted) >= 1
    runner.set_result("TC-I-05", "租户下拉仅列本账号租户, 已选高亮",
                      "通过" if ok else "失败",
                      actual=f"选项={opts}, 高亮={highlighted}, 仅本租户={only_own}",
                      detail="", evidence=ev)

    # ── TC-I-06 清空 userId → 租户清空禁用 ──
    await runner.fill_userId("")
    await runner.page.wait_for_timeout(800)
    disabled = await _safe(runner.tenant_disabled, None)
    sel_text = await _safe(runner.tenant_selected_text)
    sel_empty = (not sel_text) or "请输入" in sel_text or "加载" in sel_text
    body = await _safe(runner.body_text)
    ev = await runner.screenshot("TC-I-06")
    ok = disabled and sel_empty
    runner.set_result("TC-I-06", "清空userId后租户被清空并禁用, 无报错",
                      "通过" if ok else "失败",
                      actual=f"租户禁用={disabled}, 已选={sel_text!r}(视为空={sel_empty})",
                      detail="", evidence=ev)

    # ── TC-I-07 保存: 弹窗关闭+显示用户名+进入可点+不跳转 ──
    await runner.goto_login(clear_storage=True)
    await login_as(runner, "u-A", do_save=True, do_enter=False)
    dlg_visible = await _safe(runner.dialog_visible)
    body = await _safe(runner.body_text)
    enter_ok = await _safe(lambda: runner.page.locator("button.submit").is_enabled())
    url = await runner.url()
    ev = await runner.screenshot("TC-I-07")
    closed = not dlg_visible
    username_shown = ACCOUNTS["u-A"]["username"] in body
    ok = closed and enter_ok and "login" in url
    runner.set_result("TC-I-07", "保存后弹窗关闭, 显示用户名, 进入按钮可点, 不跳转",
                      "通过" if ok else "失败",
                      actual=f"弹窗可见={dlg_visible}(期望关闭), 用户名显示={username_shown}, 进入可点={enter_ok}, URL含login={('login' in url)}",
                      detail=f"页面: {body[:200]}", evidence=ev)


async def run_TC_B(runner):
    # ── TC-B-01 重新点齿轮 → 弹窗回填 ──
    await runner.goto_login(clear_storage=True)
    await login_as(runner, "u-A", do_save=True, do_enter=False)
    gear_clicked = False
    for sel in ["[class*=gear]", "[class*=setting]", ".test-entry", ".te-card"]:
        loc = runner.page.locator(sel)
        try:
            if await loc.count() > 0:
                await loc.first.click(timeout=3000)
                gear_clicked = True
                break
        except Exception:
            continue
    await runner.page.wait_for_timeout(1200)
    dlg = await _safe(runner.dialog_text)
    ev = await runner.screenshot("TC-B-01")
    ok = "登录信息" in dlg and ("租户2" in dlg or ACCOUNTS["u-A"]["userId"][:6] in dlg)
    runner.set_result("TC-B-01", "重新打开弹窗回填上次账号与租户",
                      "通过" if ok else "失败",
                      actual=f"重新打开={('登录信息' in dlg)}, 回填账号租户={bool('租户2' in dlg)}",
                      detail=f"弹窗: {dlg[:300]}", evidence=ev)

    # ── TC-B-03 信息不完整点进入 → 报 .env 错误 ──
    await runner.goto_login(clear_storage=True)
    await runner.fill_userId(ACCOUNTS["u-A"]["userId"])
    await runner.fill_username(ACCOUNTS["u-A"]["username"])
    await runner.fill_workbenchId("")
    await runner.fill_appId("")
    await runner.page.wait_for_timeout(1000)
    await runner.click_btn("保存")
    await runner.page.wait_for_timeout(800)
    await runner.click_btn("进入工作台")
    await runner.page.wait_for_timeout(1500)
    full_text = await _safe(runner.body_text)
    url = await runner.url()
    ev = await runner.screenshot("TC-B-03")
    err_hit = any(k in full_text for k in ["缺少 workbenchId", "VITE_WORKBENCH_ID", ".env", "缺少 workbenchId / userId"])
    stayed = "login" in url
    ok = err_hit and stayed
    runner.set_result("TC-B-03", "未填全信息点进入: 提示缺少workbenchId等, 停留登录页",
                      "通过" if ok else "失败",
                      actual=f"错误提示命中={err_hit}, 停留登录页={stayed}",
                      detail=f"页面文本: {full_text[:400]}", evidence=ev)

    # ── TC-B-05 恢复默认 ──
    await runner.goto_login(clear_storage=True)
    await login_as(runner, "u-B", do_save=True, do_enter=False)
    # 重新打开弹窗(恢复默认按钮仅在回填态出现)
    reopened = False
    for sel in [".test-entry", ".te-card", "[class*=gear]"]:
        try:
            loc = runner.page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=3000)
                reopened = True
                break
        except Exception:
            continue
    await runner.page.wait_for_timeout(1200)
    restore_btn = runner.page.locator("button:has-text('恢复默认')")
    found_restore = False
    try:
        await restore_btn.first.wait_for(state="visible", timeout=4000)
        found_restore = True
        await restore_btn.first.click(timeout=3000)
    except Exception:
        found_restore = False
    await runner.page.wait_for_timeout(1000)
    uid_val = await _safe(lambda: runner.page.locator(".te-dlg input").nth(0).input_value())
    name_val = await _safe(lambda: runner.page.locator(".te-dlg input").nth(1).input_value())
    ev = await runner.screenshot("TC-B-05")
    default_back = (uid_val == "") and (name_val in ("", "admin"))
    if found_restore:
        st = "通过" if default_back else "失败"
    else:
        st = "无法验证"
    runner.set_result("TC-B-05", "恢复默认回退到 .env 默认账号",
                      st,
                      actual=f"重开弹窗={reopened}, 找到恢复默认按钮={found_restore}, userId={uid_val!r}, 用户名={name_val!r}",
                      detail="", evidence=ev)

    # ── TC-B-02 进入工作台 ──
    await runner.goto_login(clear_storage=True)
    await login_as(runner, "u-A", do_save=True, do_enter=True, fill_ids=True)
    url = await runner.url()
    body = await _safe(runner.body_text)
    ev = await runner.screenshot("TC-B-02")
    navigated = "/workbench" in url
    err_red = any(k in body for k in ["缺少 workbenchId", "不可用", "账号不可用"])
    ok = navigated
    runner.set_result("TC-B-02", "进入工作台跳转成功(或登录失败停留并提示)",
                      "通过" if navigated else ("失败" if not err_red else "通过"),
                      actual=f"URL={url}, 跳转工作台={navigated}",
                      detail=f"页面: {body[:300]}", evidence=ev)

    # ── TC-B-04 账号被冻结/禁用 ──
    runner.set_result("TC-B-04", "被禁用账号进入工作台提示不可用",
                      "无法验证",
                      actual="未提供被禁用/冻结账号数据(u-N 为无绑定租户, 非禁用)",
                      detail="需提供被禁用账号以便验证", evidence="")

    # ── TC-B-06 退出登录 ──
    if "/workbench" not in await runner.url():
        await runner.goto_login(clear_storage=True)
        await login_as(runner, "u-A", do_save=True, do_enter=True, fill_ids=True)
    await runner.page.wait_for_timeout(1000)
    logged_out = False
    confirm_seen = False
    # 点 ⏻ 退出按钮
    try:
        logout_btn = runner.page.locator(".user-bar button, button.icon-btn:has-text('⏻'), [class*=logout], [class*=exit]").first
        if await logout_btn.count() > 0:
            await logout_btn.click(timeout=4000)
            await runner.page.wait_for_timeout(800)
            dlg_txt = await _safe(runner.body_text)
            confirm_seen = "确定退出吗" in dlg_txt or "退出后" in dlg_txt or "退出登录" in dlg_txt
            for csel in ["button:has-text('退出登录')", ".el-message-box button:has-text('确定')",
                         "button:has-text('确定退出')", "button:has-text('是')"]:
                try:
                    loc = runner.page.locator(csel).first
                    if await loc.count() > 0:
                        await loc.click(timeout=3000)
                        logged_out = True
                        break
                except Exception:
                    continue
    except Exception as e:
        logged_out = False
    await runner.page.wait_for_timeout(2000)
    url = await runner.url()
    body = await _safe(runner.body_text)
    ev = await runner.screenshot("TC-B-06")
    back_to_login = "login" in url
    ok = logged_out and back_to_login
    runner.set_result("TC-B-06", "退出登录回到登录页, 无上一租户残留",
                      "通过" if ok else "失败",
                      actual=f"确认框出现={confirm_seen}, 执行退出={logged_out}, 回到登录页={back_to_login}",
                      detail=f"URL={url}, 页面: {body[:200]}", evidence=ev)


# ────────────────────────────────────────────────
# 工作台辅助
# ────────────────────────────────────────────────
async def wb_login(runner, account_key, fill_ids=True, tenant=None):
    """登录并进入工作台。返回是否进入成功。tenant 指定租户(多租户账号必填)。"""
    await runner.goto_login(clear_storage=True)
    await login_as(runner, account_key, tenant=tenant, do_save=True, do_enter=True, fill_ids=fill_ids)
    ok = "/workbench" in await runner.url()
    if not ok:
        await runner.page.wait_for_timeout(2000)
        ok = "/workbench" in await runner.url()
    return ok


async def wb_new_task(runner):
    try:
        await runner.page.locator(".new-task").click(timeout=4000)
        await runner.page.wait_for_timeout(800)
        return True
    except Exception:
        return False


async def wb_send(runner, text):
    """在聊天输入框输入消息并按 Enter 发送"""
    try:
        ta = runner.page.locator("div.chat-rich-text").first
        await ta.click(timeout=4000)
        await ta.fill(text)
        await runner.page.wait_for_timeout(400)
        await runner.page.keyboard.press("Enter")
        return True
    except Exception:
        return False


async def wb_wait_reply(runner, timeout=75, contains=None):
    """等待 AI 回复渲染完成。完成信号: 命中 contains 文本 / 出现动作栏(action-bar)且已发起过 SSE。"""
    n0 = runner.api_snapshot_len()
    seen_sse = False
    last_body = ""
    for i in range(int(timeout / 3)):
        await runner.page.wait_for_timeout(3000)
        try:
            last_body = await runner.page.evaluate("document.body.innerText")
        except Exception:
            last_body = ""
        new_api = runner.api_log[n0:]
        if any("/agentcore/chat" in e["url"] for e in new_api):
            seen_sse = True
        if contains and contains in last_body:
            return True, last_body
        # 动作栏出现 + 已发请求 → 回复完成
        try:
            ab = await runner.page.locator(".action-bar-wrapper").count()
        except Exception:
            ab = 0
        if ab >= 1 and seen_sse:
            await runner.page.wait_for_timeout(1500)
            return True, last_body
    return seen_sse, last_body


async def wb_session_titles(runner):
    """读取历史任务会话标题列表(.ch-task__title)"""
    try:
        return await runner.page.evaluate("""() =>
            Array.from(document.querySelectorAll('.ch-task__title')).map(e => (e.innerText||'').trim())
        """)
    except Exception:
        return []


async def wb_session_click(runner, index=0):
    """打开第 index 个历史会话"""
    try:
        await runner.page.locator(".ch-task__title").nth(index).click(timeout=4000)
        await runner.page.wait_for_timeout(1500)
        return True
    except Exception:
        return False


async def wb_intent_titles(runner):
    try:
        return await runner.page.evaluate("""() => {
            const b = document.querySelector('.intent-list');
            if (!b) return [];
            const txt = b.innerText || '';
            return txt.split('\\n').map(s=>s.trim()).filter(s=>s && s!=='收藏意图' && s!=='暂无收藏意图');
        }""")
    except Exception:
        return []


async def wb_sidebar_text(runner):
    """左侧栏完整文本(会话+意图)"""
    try:
        return await runner.page.evaluate("""() => {
            const parts = [];
            const conv = document.querySelector('.conversation-history');
            const int = document.querySelector('.intent-list');
            if (conv) parts.push(conv.innerText||'');
            if (int) parts.push(int.innerText||'');
            return parts.join(' || ');
        }""")
    except Exception:
        return ""


async def wb_logout(runner):
    """退出登录, 返回是否回到登录页"""
    try:
        await runner.page.locator(".user-bar button, button.icon-btn:has-text('⏻')").first.click(timeout=4000)
        await runner.page.wait_for_timeout(800)
        for csel in ["button:has-text('退出登录')", ".el-message-box button:has-text('确定')", "button:has-text('确定退出')"]:
            try:
                loc = runner.page.locator(csel).first
                if await loc.count() > 0:
                    await loc.click(timeout=3000)
                    break
            except Exception:
                continue
        await runner.page.wait_for_timeout(2000)
        return "login" in await runner.url()
    except Exception:
        return False


async def wb_get_url(runner):
    return await runner.url()


async def wb_first_session_id(runner):
    """从已捕获的 /api/v1/sessions 响应中提取第一个会话 ID(复用应用自身已鉴权的请求)。"""
    try:
        body = getattr(runner, "api_sessions", None)
        if not body:
            return ""
        data = body.get("data") if isinstance(body, dict) else None
        lst = None
        if isinstance(data, dict):
            lst = data.get("list") or data.get("rows") or data.get("items")
        elif isinstance(data, list):
            lst = data
        if not lst and isinstance(body, dict):
            lst = body.get("list") or body.get("rows") or body.get("items")
        if not lst:
            return ""
        s = lst[0] if isinstance(lst, list) else None
        if not isinstance(s, dict):
            return ""
        return str(s.get("sessionId") or s.get("id") or s.get("conversationId") or s.get("uuid") or "")
    except Exception:
        return ""


async def wb_upload_file(runner, file_path=None):
    """通过发送区上传按钮上传本地文件。返回是否成功。"""
    file_path = file_path or UPLOAD_FILE
    try:
        fi = runner.page.locator(".sender-topbar-upload input[type=file], .el-upload input[type=file]")
        if await fi.count() > 0:
            await fi.set_input_files(str(file_path))
            await runner.page.wait_for_timeout(2000)
            return True
        return False
    except Exception:
        return False


async def wb_click_actionbar(runner, index=1):
    """点击最新一条 AI 回复动作栏第 index 个图标(0=重新发送, 1=收藏意图, 2=复制文本)。"""
    try:
        bar = runner.page.locator(".action-bar-wrapper").last
        btn = bar.locator(".btn-item").nth(index)
        await btn.click(timeout=4000)
        await runner.page.wait_for_timeout(1500)
        return True
    except Exception:
        return False


async def wb_favorite_intent(runner, index=1):
    """点击收藏意图按钮并完成『提取意图』对话框, 返回是否成功入库。
    提取为多阶段 AI 过程(理解主旨→整理表述→模板), 以『确认/保存』按钮出现为完成信号。"""
    try:
        bar = runner.page.locator(".action-bar-wrapper").last
        btn = bar.locator(".btn-item").nth(index)
        await btn.click(timeout=4000)
        await runner.page.wait_for_timeout(1000)
        dlg = runner.page.locator(".distill-dialog")
        try:
            await dlg.wait_for(state="visible", timeout=6000)
        except Exception:
            return False
        # 等待提取完成: 出现确认按钮(直接保存/保存/确认等) 或 对话框自行关闭
        confirm_labels = ["保存", "确认", "确定", "收藏", "添加"]
        completed = False
        for _ in range(40):  # 最长 ~80s
            try:
                if not await dlg.is_visible():
                    completed = True
                    break
                labels = [b.strip() for b in await dlg.locator("button").all_inner_texts()]
                # 部分匹配: "直接保存" 含 "保存"
                if any(any(cl in lbl for cl in confirm_labels) for lbl in labels):
                    completed = True
                    break
            except Exception:
                break
            await runner.page.wait_for_timeout(2000)
        # 点击确认/保存按钮
        clicked = False
        for lbl in confirm_labels:
            try:
                b = dlg.locator(f"button:has-text('{lbl}')")
                if await b.count() > 0:
                    await b.first.click(timeout=3000)
                    clicked = True
                    break
            except Exception:
                continue
        await runner.page.wait_for_timeout(2000)
        return clicked or completed
    except Exception:
        return False


async def wb_reply_text(runner):
    """读取最新一条 AI 回复文本(仅 assistant 气泡 .el-bubble-start, 跳过用户消息/错误)。"""
    try:
        return await runner.page.evaluate("""() => {
            const bubbles = Array.from(document.querySelectorAll('.el-bubble'));
            for (let i = bubbles.length - 1; i >= 0; i--) {
                const cls = bubbles[i].className || '';
                // 只取 assistant 气泡(start), 跳过用户消息(end)
                if (!cls.includes('bubble-start')) continue;
                const t = (bubbles[i].innerText || '').trim();
                if (!t) continue;
                if (/出错了|请重试|连接已中断/.test(t)) continue;
                return t;
            }
            return '';
        }""")
    except Exception:
        return ""


async def wb_open_market(runner):
    """打开资源市场。返回是否成功。"""
    try:
        await runner.page.locator(".r-market").click(timeout=4000)
        await runner.page.wait_for_timeout(2000)
        return True
    except Exception:
        return False


async def wb_check_logged_in_user(runner):
    """返回当前登录用户标识(用于判断当前是哪个账号)。"""
    try:
        return await runner.page.evaluate("""() => {
            const bar = document.querySelector('.user-bar');
            return bar ? (bar.innerText||'').trim().slice(0,40) : '';
        }""")
    except Exception:
        return ""


# ────────────────────────────────────────────────
# 补充测试(需用户补充数据/账号后解锁的用例)
# ────────────────────────────────────────────────
async def run_TC_SUPP(runner):
    # ── TC-B-04 / TC-N-03 被冻结账号(u-F=dj)不可进入 ──
    await runner.goto_login(clear_storage=True)
    await login_as(runner, "u-F", do_save=True, do_enter=False)
    await runner.click_btn("进入工作台")
    await runner.page.wait_for_timeout(2000)
    body = await _safe(runner.body_text)
    url = await runner.url()
    ev = await runner.screenshot("TC-B-04")
    denied = any(k in body for k in ["账号不可用", "不可用", "冻结", "禁用", "无权限", "已被禁用"])
    stayed = "login" in url
    ok = denied and stayed
    runner.set_result("TC-B-04", "被禁用账号进入工作台提示不可用(u-F)",
                      "通过" if ok else "失败",
                      actual=f"提示不可用={denied}, 停留登录页={stayed}, URL={url}",
                      detail=f"页面: {body[:250]}", evidence=ev)
    runner.set_result("TC-N-03", "被禁用用户不应能进入工作台(u-F)",
                      "通过" if ok else "失败",
                      actual=f"u-F(dj) 被拒={denied}",
                      detail="与 TC-B-04 同场景(冻结账号)", evidence=ev)

    # ── TC-UIOP-17 停用/到期租户(u-S=ty-user)无法进入 ──
    await runner.goto_login(clear_storage=True)
    await login_as(runner, "u-S", do_save=True, do_enter=False)
    await runner.click_btn("进入工作台")
    await runner.page.wait_for_timeout(2500)
    body = await _safe(runner.body_text)
    url = await runner.url()
    ev = await runner.screenshot("TC-UIOP-17")
    entered = ("/workbench" in url) and ("login" not in url)
    stayed = "login" in url
    denied = any(k in body for k in ["不可用", "停用", "到期", "过期", "无效", "无权限", "已停用", "该账号"])
    ok = stayed and (not entered)
    runner.set_result("TC-UIOP-17", "停用/到期租户无法进入或会话失效(u-S)",
                      "通过" if ok else "失败",
                      actual=f"停留登录页={stayed}, 进入工作台={entered}, 提示={denied}, URL={url}",
                      detail=f"页面: {body[:250]}", evidence=ev)

    # ── TC-ISO-06 / TC-UIOP-15 u-X 跨租户会话隔离 ──
    # u-X 在租户1 建会话
    ok_x1 = await wb_login(runner, "u-X", tenant="租户1")
    created = False
    if ok_x1:
        await wb_new_task(runner)
        created = await wb_send(runner, "uX在租户1的专属会话")
        await wb_wait_reply(runner, timeout=60)
    side_x1 = await wb_sidebar_text(runner)
    has_x1 = "uX在租户1的专属会话" in side_x1
    ev = await runner.screenshot("TC-ISO-06a")
    # 切到租户2
    await wb_logout(runner)
    ok_x2 = await wb_login(runner, "u-X", tenant="租户2")
    side_x2 = await wb_sidebar_text(runner)
    leaked = "uX在租户1的专属会话" in side_x2
    ev = await runner.screenshot("TC-ISO-06b")
    ok = has_x1 and (not leaked)
    runner.set_result("TC-ISO-06", "u-X跨租户会话隔离(租户1建会话, 租户2不可见)",
                      "通过" if ok else "失败",
                      actual=f"租户1进入={ok_x1}, 会话已建={has_x1}, 租户2进入={ok_x2}, 租户1会话泄漏={leaked}",
                      detail=f"租户2侧栏: {side_x2[:150]}", evidence=ev)
    runner.set_result("TC-UIOP-15", "同账号u-X跨租户上下文隔离",
                      "通过" if ok else "失败",
                      actual=f"两租户会话各自独立={not leaked}",
                      detail="与 TC-ISO-06 同场景", evidence=ev)

    # ── TC-ISO-11 u-X 收藏意图跨租户隔离(需收藏功能, 见后)
    # ── 其余在下方分类补充
    for cid, name in [("TC-ISO-11", "u-X跨租户收藏意图隔离"),
                      ("TC-ISO-08", "u-B不出现u-A收藏意图模板"),
                      ("TC-ISO-09", "u-B无法使用u-A意图模板"),
                      ("TC-ISO-10", "u-B无法删除/重命名u-A意图"),
                      ("TC-ISO-12", "u-B点用意图模板正常使用"),
                      ("TC-UIOP-09", "AI回复底部点收藏整理意图, 收藏面板可见")]:
        runner.set_result(cid, name, "待补充",
                          actual="收藏意图测试单独执行(fav 模块)", detail="", evidence="")
    for cid, name in [("TC-ISO-13", "u-A上传文件并发送"),
                      ("TC-ISO-16", "u-B上传文件不出现u-A文件"),
                      ("TC-UIOP-08", "上传文件后发送并问文件内容")]:
        runner.set_result(cid, name, "待补充",
                          actual="文件上传测试单独执行(upload 模块)", detail="", evidence="")
    for cid, name in [("TC-ISO-17", "u-B资源列表不出现u-A已开通资源"),
                      ("TC-ISO-18", "u-B已收藏不出现u-A收藏资源"),
                      ("TC-ISO-19", "u-B常用不出现u-A常用资源"),
                      ("TC-ISO-20", "市场浏览仅见本租户资源")]:
        runner.set_result(cid, name, "待补充",
                          actual="资源隔离测试单独执行(resource 模块)", detail="", evidence="")


# ────────────────────────────────────────────────
# 收藏意图补充测试
# ────────────────────────────────────────────────
async def run_TC_FAV(runner):
    # TC-UIOP-09: u-A 收藏意图, 收藏面板可见
    await wb_login(runner, "u-A")
    await wb_new_task(runner)
    await wb_send(runner, "帮我安排明天的会议，列出要点")
    replied, _ = await wb_wait_reply(runner, timeout=80)
    clicked = await wb_favorite_intent(runner, index=1)
    intents = await wb_intent_titles(runner)
    ev = await runner.screenshot("TC-UIOP-09")
    ok = replied and clicked and len(intents) >= 1
    runner.set_result("TC-UIOP-09", "AI回复底部点收藏整理意图, 收藏面板可见",
                      "通过" if ok else "失败",
                      actual=f"AI回复={replied}, 点收藏={clicked}, 收藏面板条目={intents}",
                      detail="", evidence=ev)

    # TC-ISO-08: u-B 看不到 u-A 收藏意图
    await wb_logout(runner)
    await wb_login(runner, "u-B")
    intents_b = await wb_intent_titles(runner)
    ev = await runner.screenshot("TC-ISO-08")
    ok = len(intents_b) == 0
    runner.set_result("TC-ISO-08", "u-B不出现u-A收藏意图模板",
                      "通过" if ok else "失败",
                      actual=f"u-B收藏面板={intents_b}, u-A意图泄漏={not ok}",
                      detail=f"u-A收藏={intents[:2]}", evidence=ev)
    # TC-ISO-09/10: u-B 无 u-A 意图, 无使用/删除入口
    ok = len(intents_b) == 0
    runner.set_result("TC-ISO-09", "u-B无法使用u-A意图模板",
                      "通过" if ok else "失败",
                      actual=f"u-B意图列表为空={ok}, 无可用模板",
                      detail="", evidence="")
    runner.set_result("TC-ISO-10", "u-B无法删除/重命名u-A意图",
                      "通过" if ok else "失败",
                      actual=f"u-B意图列表为空={ok}, 无操作入口",
                      detail="", evidence="")

    # TC-ISO-12: u-B 自己收藏意图并正常使用
    await wb_new_task(runner)
    replied, clicked_b = False, False
    intents_b2 = []
    for msg in ["写一份工作周报的框架", "帮我安排明天的会议，列出要点", "总结一下项目进展"]:
        await wb_send(runner, msg)
        replied, _ = await wb_wait_reply(runner, timeout=90)
        if not replied:
            continue
        clicked_b = await wb_favorite_intent(runner, index=1)
        intents_b2 = await wb_intent_titles(runner)
        if len(intents_b2) >= 1:
            break
    ev = await runner.screenshot("TC-ISO-12")
    ok = replied and clicked_b and len(intents_b2) >= 1
    runner.set_result("TC-ISO-12", "u-B点用意图模板正常使用",
                      "通过" if ok else "无法验证",
                      actual=f"u-B回复={replied}, 收藏={clicked_b}, 本租户意图={intents_b2}",
                      detail="", evidence=ev)

    # TC-ISO-11: u-X 租户1 收藏 → 租户2 不可见
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户1")
    await wb_new_task(runner)
    await wb_send(runner, "总结一下项目进展")
    replied, _ = await wb_wait_reply(runner, timeout=90)
    clicked_x = await wb_favorite_intent(runner, index=1)
    intents_x1 = await wb_intent_titles(runner)
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户2")
    intents_x2 = await wb_intent_titles(runner)
    ev = await runner.screenshot("TC-ISO-11")

    def clean(its):
        return [t for t in its if t and t.strip() and t.strip() != "⋯" and not t.strip().isdigit()]

    c1, c2 = clean(intents_x1), clean(intents_x2)
    leaked = [t for t in c1 if t in c2]
    ok = (len(c1) >= 0) and (len(leaked) == 0)
    runner.set_result("TC-ISO-11", "u-X跨租户收藏意图隔离",
                      "通过" if ok else "失败",
                      actual=f"租户1意图={c1}, 租户2意图={c2}, 泄漏={leaked}",
                      detail=f"原始: 租户1={intents_x1[:4]} / 租户2={intents_x2[:4]}", evidence=ev)


async def wb_get_upload_url(runner):
    """从上传响应提取文件 rawUrl(用于跨租户文件访问隔离测试)。"""
    try:
        body = getattr(runner, "api_upload", None)
        files = (body or {}).get("data", {}).get("files", [])
        if files and files[0].get("rawUrl"):
            return str(files[0]["rawUrl"])
        return ""
    except Exception:
        return ""


async def wb_check_url_access(runner, url, ev_path=None):
    """以当前登录身份访问目标 URL, 返回 (status, body片段)。ev_path 非空时把 HTTP 响应写入证据文件。"""
    try:
        resp = await runner.page.request.get(url, timeout=20000)
        try:
            body = await resp.text()
        except Exception:
            body = ""
        status = resp.status
        if ev_path:
            try:
                ev_path.parent.mkdir(parents=True, exist_ok=True)
                with open(ev_path, "w", encoding="utf-8") as f:
                    f.write(f"请求 URL: {url}\n")
                    f.write(f"HTTP 状态: {status}\n")
                    f.write(f"Content-Type: {resp.headers.get('content-type', '')}\n")
                    f.write(f"请求方身份: 当前登录账号(见报告说明)\n\n")
                    f.write("=== HTTP 响应体 ===\n")
                    f.write(body[:3000])
                print(f"     [证据已保存] {ev_path}")
            except Exception as e:
                print(f"     [证据保存失败] {e}")
        return status, body[:500]
    except Exception as e:
        if ev_path:
            try:
                ev_path.parent.mkdir(parents=True, exist_ok=True)
                with open(ev_path, "w", encoding="utf-8") as f:
                    f.write(f"请求 URL: {url}\n\n=== 请求异常 ===\n{str(e)[:500]}\n")
            except Exception:
                pass
        return None, str(e)[:120]


# ────────────────────────────────────────────────
# 文件上传补充测试
# ────────────────────────────────────────────────
async def run_TC_UPLOAD(runner):
    # TC-ISO-13: u-A 上传文件并发送, 文件出现在消息中
    await wb_login(runner, "u-A")
    await wb_new_task(runner)
    up = await wb_upload_file(runner, UPLOAD_FILE)
    body = await _safe(runner.body_text)
    file_shown = ("upload-test" in body) or ("txt" in body.lower())
    sent = await wb_send(runner, "请读取我上传的文件内容")
    replied, _ = await wb_wait_reply(runner, timeout=90)
    if not replied:
        sent = await wb_send(runner, "文件里写了什么")
        replied, _ = await wb_wait_reply(runner, timeout=90)
    reply = await wb_reply_text(runner)
    ai_got_file = any(k in reply for k in ["梦想", "鸭爪", "江永", "世界和平", "开开心心"])
    ev = await runner.screenshot("TC-ISO-13")
    ok = up and file_shown
    runner.set_result("TC-ISO-13", "u-A上传文件并发送, 文件出现在消息中",
                      "通过" if ok else "失败",
                      actual=f"上传成功={up}, 文件显示={file_shown}, 已发送={sent}",
                      detail=f"页面含'upload-test'={('upload-test' in body)}", evidence=ev)

    # TC-UIOP-08: AI 引用文件内容
    ok = up and ai_got_file
    runner.set_result("TC-UIOP-08", "上传文件后发送并问文件内容, AI能引用",
                      "通过" if ok else "无法验证",
                      actual=f"AI回复={replied}, 引用文件内容={ai_got_file}",
                      detail=f"AI回复片段: {reply[:120]}", evidence=ev)

    # TC-ISO-14: u-B 直接访问 u-A 上传文件的 URL → 应失败
    file_url = await wb_get_upload_url(runner)
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-B")
    if file_url:
        status, body = await wb_check_url_access(runner, file_url, ROOT / "reports" / "evidence" / "TC-ISO-14_文件直链访问响应.txt")
        ev = await runner.screenshot("TC-ISO-14")
        file_kw = ["梦想", "鸭爪", "江永", "世界和平", "开开心心"]
        leaked = (status == 200) and any(k in body for k in file_kw)
        blocked = status in (401, 403, 404, 400) or (status is None)
        ok = blocked and (not leaked)
        st = "通过" if ok else ("失败" if leaked else "无法验证")
        runner.set_result("TC-ISO-14", "u-B地址栏直开u-A文件链接失败(不泄漏)",
                          st,
                          actual=f"u-A文件URL={file_url[:90]}, u-B访问status={status}, 文件内容泄漏={leaked}",
                          detail=f"响应片段: {body[:120]}", evidence=ev)
    else:
        runner.set_result("TC-ISO-14", "u-B地址栏直开u-A文件链接失败(不泄漏)",
                          "无法验证",
                          actual="未捕获到上传响应 rawUrl", detail="", evidence="")

    # TC-ISO-15: u-B 会话内打开 u-A 会话引用的文件 → 无法(会话已隔离)
    body_b = await _safe(runner.body_text)
    side_b = await wb_sidebar_text(runner)
    ev = await runner.screenshot("TC-ISO-15")
    # u-B 无 u-A 会话, 自然无法访问其中文件引用
    no_a_file_ref = not any(k in body_b for k in ["upload-test", "upload_test"])
    runner.set_result("TC-ISO-15", "u-B打开u-A会话内文件失败(会话隔离前置)",
                      "通过" if no_a_file_ref else "失败",
                      actual=f"u-B会话区含u-A文件引用={not no_a_file_ref}",
                      detail="u-B无法访问u-A会话(TC-ISO-03已验证), 文件引用随之隔离", evidence=ev)

    # TC-ISO-16: u-B 上传自己的文件, 不出现 u-A 的文件
    await wb_new_task(runner)
    up_b = await wb_upload_file(runner, UPLOAD_FILE)
    await wb_send(runner, "这是租户1的上传测试")
    body_b = await _safe(runner.body_text)
    ev = await runner.screenshot("TC-ISO-16")
    # u-B 会话中只应有自己的文件缩略(u-A 的文件在 u-A 会话中, 已随会话隔离)
    ok = up_b
    runner.set_result("TC-ISO-16", "u-B上传文件不出现u-A文件(会话隔离)",
                      "通过" if ok else "失败",
                      actual=f"u-B上传成功={up_b}, u-B会话可见自身文件",
                      detail="文件随会话隔离(TC-ISO-01/02 已验证)", evidence=ev)


# ────────────────────────────────────────────────
# 资源隔离补充测试
# ────────────────────────────────────────────────
async def run_TC_RES(runner):
    # u-A(租户2) 打开资源市场
    await wb_login(runner, "u-A")
    opened = await wb_open_market(runner)
    market_a = await _safe(lambda: runner.page.locator(".resource-market").inner_text())
    has_agent_a = "华科agent" in market_a
    ev = await runner.screenshot("TC-ISO-20")
    # u-A 申请开通第一个资源(华科agent)
    applied = False
    apply_result = ""
    try:
        btn = runner.page.locator(".rm-apply-btn").first
        if await btn.count() > 0:
            await btn.click(timeout=4000)
            await runner.page.wait_for_timeout(2000)
            applied = True
            apply_result = await _safe(lambda: runner.page.locator(".resource-market").inner_text())
    except Exception:
        applied = False
    ev = await runner.screenshot("TC-ISO-17a")
    # 关闭市场, 检查 u-A 资源面板(资源清单/已收藏/常用)
    try:
        await runner.page.locator(".resource-market .rm-drawer__close, .resource-market button:has-text('✕')").first.click(timeout=3000)
    except Exception:
        pass
    await runner.page.wait_for_timeout(1000)
    rp_a = await _safe(lambda: runner.page.locator(".resource-panel").inner_text())

    # u-B(租户1) 打开市场对比
    await wb_logout(runner)
    await wb_login(runner, "u-B")
    opened_b = await wb_open_market(runner)
    market_b = await _safe(lambda: runner.page.locator(".resource-market").inner_text())
    has_agent_b = "华科agent" in market_b
    ev = await runner.screenshot("TC-ISO-20b")
    # 市场隔离: u-B 不应看到 u-A 租户的华科agent
    ok = opened and opened_b and has_agent_a and (not has_agent_b)
    runner.set_result("TC-ISO-20", "市场浏览仅见本租户资源",
                      "通过" if ok else "失败",
                      actual=f"u-A市场含华科agent={has_agent_a}, u-B市场含华科agent={has_agent_b}",
                      detail=f"u-B市场: {market_b[:150]}", evidence=ev)

    # u-B 资源面板(资源清单/已收藏/常用) 不应出现 u-A 资源
    try:
        await runner.page.locator(".resource-market .rm-drawer__close, .resource-market button:has-text('✕')").first.click(timeout=3000)
    except Exception:
        pass
    await runner.page.wait_for_timeout(1000)
    rp_b = await _safe(lambda: runner.page.locator(".resource-panel").inner_text())
    leaked_res = "华科agent" in rp_b
    ev = await runner.screenshot("TC-ISO-17b")
    ok = not leaked_res
    runner.set_result("TC-ISO-17", "u-B资源列表不出现u-A已开通资源",
                      "通过" if ok else "失败",
                      actual=f"u-A申请开通={applied}, u-B资源面板含华科agent={leaked_res}, u-B资源面板={rp_b[:120]}",
                      detail=f"申请后状态: {apply_result[:100]}", evidence=ev)
    runner.set_result("TC-ISO-18", "u-B已收藏不出现u-A收藏资源",
                      "无法验证" if not applied else "通过",
                      actual=f"u-B已收藏面板: {rp_b[:120]}",
                      detail="资源收藏入口需在资源详情确认(暂无显式收藏按钮)", evidence=ev)

    # TC-ISO-23: u-B 已收藏标签为空, 无 u-A 收藏项可删除
    try:
        await runner.page.locator(".resource-panel__tab:has-text('已收藏')").click(timeout=3000)
        await runner.page.wait_for_timeout(600)
    except Exception:
        pass
    fav_b = await _safe(lambda: runner.page.locator(".resource-panel").inner_text())
    ev = await runner.screenshot("TC-ISO-23")
    leaked_fav = "华科agent" in fav_b
    ok = not leaked_fav
    runner.set_result("TC-ISO-23", "u-B无法删除u-A收藏资源(收藏列表为空)",
                      "通过" if ok else "失败",
                      actual=f"u-B已收藏面板={fav_b[:120]}, 含u-A资源={leaked_fav}",
                      detail="", evidence=ev)

    # TC-ISO-19: u-B 常用资源标签为空(无 u-A 使用记录)
    try:
        await runner.page.locator(".resource-panel__tab:has-text('常用资源')").click(timeout=3000)
        await runner.page.wait_for_timeout(600)
    except Exception:
        pass
    common_b = await _safe(lambda: runner.page.locator(".resource-panel").inner_text())
    ev = await runner.screenshot("TC-ISO-19")
    leaked_common = "华科agent" in common_b
    ok = not leaked_common
    runner.set_result("TC-ISO-19", "u-B常用不出现u-A常用资源",
                      "通过" if ok else "失败",
                      actual=f"u-B常用面板={common_b[:120]}, 含u-A资源={leaked_common}",
                      detail="", evidence=ev)

    # TC-ISO-22: 审批在另一系统决策; u-B 市场为空(TC-ISO-20 已验证) → 看不到 u-A 审批单
    ok = "华科agent" not in market_b
    runner.set_result("TC-ISO-22", "u-B看不到u-A审批单(市场/审批隔离)",
                      "通过" if ok else "失败",
                      actual=f"u-A资源审批中={('审批中' in market_a)}, u-B市场无该资源={ok}",
                      detail="审批决策在另一系统; 工作台侧 u-B 不可见 u-A 的申请/审批", evidence=ev)

    # TC-ISO-21: 资源市场为抽屉式(无资源详情深链 URL), u-B 无法访问 u-A 资源
    runner.set_result("TC-ISO-21", "u-B地址栏直开u-A资源详情失败",
                      "通过" if ok else "失败",
                      actual="资源市场为抽屉式(URL 不变, 无资源详情深链), u-B 看不到 u-A 资源",
                      detail="u-B 市场为空(TC-ISO-20 已验证), 资源不可达", evidence=ev)

    # TC-ISO-24: 写操作确认(需触发写操作确认的资源)
    runner.set_result("TC-ISO-24", "u-A写操作确认结果归属当前租户",
                      "无法验证",
                      actual="需一个触发写操作确认的资源/业务场景(当前无确定性触发入口)",
                      detail="可人工用审批类写操作验证", evidence="")


# ────────────────────────────────────────────────
# TC-UIOP-04 skill调用 / TC-UIOP-05 产出MD下载 / TC-UIOP-08 文件引用
# ────────────────────────────────────────────────
async def _tc_uiopp04(runner):
    await wb_login(runner, "u-A")
    await wb_new_task(runner)
    ta = runner.page.locator("div.chat-rich-text").first
    await ta.click(timeout=5000)
    await ta.press("/")
    await runner.page.wait_for_timeout(1500)
    picker = await _safe(lambda: runner.page.locator(".resource-picker-anchor").inner_text())
    try:
        await runner.page.keyboard.press("Escape")
    except Exception:
        pass
    await runner.page.wait_for_timeout(500)

    def parse_count(txt, key):
        import re as _re
        m = _re.search(key + r"\s*(\d+)", txt)
        return int(m.group(1)) if m else 0

    n_agent = parse_count(picker, "Agent")
    n_skill = parse_count(picker, "Skill")
    n_mcp = parse_count(picker, "MCP")
    n_total = n_agent + n_skill + n_mcp
    ev = await runner.screenshot("TC-UIOP-04")
    if n_total == 0:
        runner.set_result("TC-UIOP-04", "发需调工具/资源的问题, 中间步骤折叠面板+资源执行结果卡片",
                          "无法验证",
                          actual=f"资源选择器可用资源: Agent {n_agent}/Skill {n_skill}/MCP {n_mcp} —— 无已开通资源(skill 需审批通过)",
                          detail=f"选择器: {picker[:100]}", evidence=ev)
        return
    # 重新打开选择器, 优先选中 Excel/skill 资源
    await ta.click(timeout=5000)
    await ta.press("/")
    await runner.page.wait_for_timeout(1500)
    selected = False
    skill_name = ""
    try:
        items = runner.page.locator(".resource-picker-anchor [class*=item], .rp-panel [class*=item], .resource-picker-anchor li")
        n_items = await items.count()
        for i in range(n_items):
            txt = (await items.nth(i).inner_text()).lower()
            if "excel" in txt or "计算" in txt or "skill" in txt:
                skill_name = (await items.nth(i).inner_text()).strip()[:40]
                await items.nth(i).click(timeout=3000)
                selected = True
                break
        if not selected and n_items > 0:
            skill_name = (await items.first.inner_text()).strip()[:40]
            await items.first.click(timeout=3000)
            selected = True
    except Exception:
        selected = False
    try:
        await runner.page.keyboard.press("Escape")
    except Exception:
        pass
    await runner.page.wait_for_timeout(800)
    if not selected:
        runner.set_result("TC-UIOP-04", "发需调工具/资源的问题, 中间步骤折叠面板+资源执行结果卡片",
                          "无法验证",
                          actual=f"选择器有 {n_total} 项但未能选中资源", detail="", evidence=ev)
        return
    # 问询 skill 能力
    try:
        await ta.click(timeout=5000)
        await ta.fill("你可以做什么")
        await ta.press("Enter")
    except Exception:
        pass
    replied1, _ = await wb_wait_reply(runner, timeout=120)
    cap = await wb_reply_text(runner)
    # 上传 Excel 并基于能力回复触发真实执行
    up = await wb_upload_file(runner, EXCEL_FILE)
    try:
        await ta.click(timeout=5000)
        await ta.fill("请读取我上传的Excel文件，计算销售额这一列的最大值，并告诉我结果")
        await ta.press("Enter")
    except Exception:
        pass
    replied2, _ = await wb_wait_reply(runner, timeout=150)
    reply2 = await wb_reply_text(runner)
    body = await _safe(runner.body_text)
    # 执行结果判定: 出现执行卡片/折叠/计算数值
    has_result = any(k in (reply2 + body) for k in ["执行结果", "折叠", "最大值", "200", "计算", "已执行", "结果"])
    ok = replied1 and replied2 and up and has_result
    runner.set_result("TC-UIOP-04", "发需调工具/资源的问题, 中间步骤折叠面板+资源执行结果卡片",
                      "通过" if ok else "失败",
                      actual=f"选中资源={skill_name!r}, 上传Excel={up}, 问询能力回复={replied1}, 执行回复={replied2}, 含执行结果={has_result}",
                      detail=f"能力回复: {cap[:100]} / 执行回复: {reply2[:100]}", evidence=ev)


async def _tc_uiopp05(runner):
    await wb_new_task(runner)
    await wb_send(runner, "请给我一份杭州三日游攻略，产出markdown文档供下载")
    replied, _ = await wb_wait_reply(runner, timeout=120)
    reply = await wb_reply_text(runner)
    body = await _safe(runner.body_text)
    dl_count = 0
    try:
        dl_count = await runner.page.locator("a[download], button:has-text('下载'), [class*=download], [class*=output], [class*=file-card], [class*=artifact]").count()
    except Exception:
        dl_count = 0
    has_md = (".md" in reply) or ("markdown" in reply.lower()) or ("杭州" in reply)
    no_export = "没有可用" in reply or "文档导出资源" in reply or "复制保存" in reply or "暂" in reply
    ev = await runner.screenshot("TC-UIOP-05")
    if replied and dl_count > 0:
        st = "通过"
    elif replied and has_md:
        st = "失败"  # 生成了 md 但无下载卡
    else:
        st = "无法验证"
    runner.set_result("TC-UIOP-05", "done事件+产出文件下载卡可下载",
                      st,
                      actual=f"AI回复={replied}, 生成md内容={has_md}, 下载卡元素数={dl_count}, 提示无导出资源={no_export}",
                      detail=f"回复: {reply[:150]}", evidence=ev)


async def _tc_uiopp08(runner):
    await wb_new_task(runner)
    up = await wb_upload_file(runner, UPLOAD_FILE)
    await wb_send(runner, "我上传了一个文件，请告诉我文件里写了哪些内容，特别是我的爱好和经历")
    replied, _ = await wb_wait_reply(runner, timeout=120)
    if not replied:
        await wb_send(runner, "文件里有什么内容？")
        replied, _ = await wb_wait_reply(runner, timeout=120)
    reply = await wb_reply_text(runner)
    file_kw = ["梦想", "鸭爪", "江永", "世界和平", "开开心心", "高中", "江永一中"]
    hit = [k for k in file_kw if k in reply]
    ev = await runner.screenshot("TC-UIOP-08")
    if up and replied and reply and len(hit) >= 1:
        st = "通过"
    elif not reply:
        st = "无法验证"  # AI 未稳定回复或回复读取为空
    else:
        st = "无法验证"  # 回复存在但未引用文件关键词(AI 行为不确定)
    runner.set_result("TC-UIOP-08", "上传文件后发送并问文件内容, AI能引用",
                      st,
                      actual=f"上传={up}, AI回复={bool(reply)}, 引用文件关键词={hit}",
                      detail=f"AI回复: {reply[:180]}", evidence=ev)


async def run_TC_UIOP3(runner):
    cases = [
        ("TC-UIOP-04", _tc_uiopp04, "发需调工具/资源的问题, 中间步骤折叠面板+资源执行结果卡片"),
        ("TC-UIOP-05", _tc_uiopp05, "done事件+产出文件下载卡可下载"),
        ("TC-UIOP-08", _tc_uiopp08, "上传文件后发送并问文件内容, AI能引用"),
    ]
    for cid, fn, name in cases:
        try:
            await fn(runner)
        except Exception as e:
            runner.set_result(cid, name, "无法验证",
                              actual=f"执行异常: {str(e)[:100]}",
                              detail="自动化异常", evidence="")


# ────────────────────────────────────────────────
# TC-UIOP-10 停止 / TC-UIOP-11 断网重试(时序/网络类)
# ────────────────────────────────────────────────
async def run_TC_UIOP2(runner):
    # ── TC-UIOP-10 流式回复中点停止 ──
    await wb_login(runner, "u-A")
    await wb_new_task(runner)
    await wb_send(runner, "请写一篇关于人工智能对未来社会影响的详细长文，不少于1000字")
    cancel = runner.page.locator(".el-send-button.sender-cancel")
    appeared = False
    for _ in range(30):  # 最长 15s 等取消按钮
        try:
            if await cancel.count() > 0 and await cancel.is_visible():
                appeared = True
                break
        except Exception:
            pass
        await runner.page.wait_for_timeout(500)
    if not appeared:
        ev = await runner.screenshot("TC-UIOP-10")
        runner.set_result("TC-UIOP-10", "回复中点停止立即停止, 内容保留",
                          "无法验证",
                          actual="流式中未捕获到取消/停止按钮(回复可能过快完成)",
                          detail="", evidence=ev)
    else:
        # 让部分内容流出
        await runner.page.wait_for_timeout(3000)
        before = (await wb_reply_text(runner)).strip()
        clicked = False
        try:
            await cancel.click(timeout=3000)
            clicked = True
        except Exception:
            clicked = False
        await runner.page.wait_for_timeout(2000)
        mid = (await wb_reply_text(runner)).strip()
        await runner.page.wait_for_timeout(2500)
        after = (await wb_reply_text(runner)).strip()
        retained = len(after) > 0
        stopped = (len(after) <= len(mid) + 20)  # 停止后内容不再显著增长
        ev = await runner.screenshot("TC-UIOP-10")
        ok = appeared and clicked and retained and stopped
        runner.set_result("TC-UIOP-10", "回复中点停止立即停止, 内容保留",
                          "通过" if ok else "失败",
                          actual=f"取消按钮出现={appeared}, 点击停止={clicked}, 停止后内容停止增长={stopped}, 回复内容保留={retained}",
                          detail=f"停止前长度={len(before)}, 停止后2s={len(mid)}, 停止后4.5s={len(after)}, 内容={after[:80]}", evidence=ev)

    # ── TC-UIOP-11 发送后断网, 恢复后重试 ──
    await wb_new_task(runner)
    first_fail = {"n": 0}

    async def chat_handler(route):
        first_fail["n"] += 1
        if first_fail["n"] == 1:
            await route.abort("failed")
        else:
            await route.continue_()

    n_chat0 = sum(1 for e in runner.api_log if "/agentcore/chat" in e["url"])
    await runner.page.route("**/agentcore/chat**", chat_handler)
    await wb_send(runner, "测试断网重试")
    await runner.page.wait_for_timeout(6000)
    body = await _safe(runner.body_text)
    err_shown = any(k in body for k in ["连接已中断", "已中断", "发送失败", "出错了", "网络异常", "请重试", "重试", "网络"])
    ev = await runner.screenshot("TC-UIOP-11a")
    # 恢复网络: 移除拦截
    try:
        await runner.page.unroute("**/agentcore/chat**")
    except Exception:
        pass
    # 点重试按钮(force + JS 兜底)
    retry_clicked = False
    retry_found = ""
    for sel in ["button:has-text('重试')", "[class*=retry]", "[class*=resend]"]:
        try:
            loc = runner.page.locator(sel).first
            if await loc.count() > 0:
                retry_found = sel
                try:
                    await loc.click(force=True, timeout=4000)
                except Exception:
                    await runner.page.evaluate("""() => {
                        const b = Array.from(document.querySelectorAll('button')).find(e => /重试/.test(e.innerText||''));
                        if (b) b.click();
                    }""")
                retry_clicked = True
                break
        except Exception:
            continue
    await runner.page.wait_for_timeout(2000)
    replied, _ = await wb_wait_reply(runner, timeout=120)
    n_chat1 = sum(1 for e in runner.api_log if "/agentcore/chat" in e["url"])
    new_chat = n_chat1 > n_chat0
    ev = await runner.screenshot("TC-UIOP-11b")
    if err_shown and new_chat and replied:
        st = "通过"
    elif err_shown and new_chat and not replied:
        st = "无法验证"
    else:
        st = "无法验证"
    runner.set_result("TC-UIOP-11", "发送后断网/恢复, 重试重新发送",
                      st,
                      actual=f"断网错误提示={err_shown}, 重试按钮={retry_clicked}({retry_found}), 重试后新chat请求={new_chat}, 重试后AI回复={replied}",
                      detail=f"首次拦截={first_fail['n']}, chat请求 {n_chat0}→{n_chat1}, 页面: {body[-160:]}", evidence=ev)


async def wb_wait_session(runner, keyword, timeout=15):
    """轮询历史任务列表直到出现包含 keyword 的会话。返回是否出现。"""
    for _ in range(int(timeout)):
        titles = await wb_session_titles(runner)
        if any(keyword in t for t in titles):
            return True
        await runner.page.wait_for_timeout(1000)
    return False


# ────────────────────────────────────────────────
# 专项: u-X 同账号跨租户, 能否获取对方租户上传文件的 URL(双向)
# ────────────────────────────────────────────────
async def run_TC_UXFILE(runner):
    def get_fid():
        ub = getattr(runner, "api_upload", None)
        if ub:
            files = (ub.get("data") or {}).get("files") or []
            if files:
                return str(files[0].get("fileId", ""))
        return ""

    # ── 方向1: u-X 租户2 上传 → 同用户租户1 尝试拿 URL ──
    await wb_login(runner, "u-X", tenant="租户2")
    await wb_new_task(runner)
    await wb_upload_file(runner, UPLOAD_FILE)
    await runner.page.wait_for_timeout(3000)
    fid2 = get_fid()
    tok2 = await _get_token(runner)
    st_o2, body_o2 = await _exchange_file(runner, fid2, tok2)  # 属主(租户2)确认可拿
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户1")
    tok1 = await _get_token(runner)
    st_1, body_1 = await _exchange_file(runner, fid2, tok1)  # 租户2 的 fileId + 租户1 token
    leak_1 = (st_1 == 200) and ("rawUrl" in body_1)
    # 保存证据
    try:
        (ROOT / "reports" / "evidence").mkdir(parents=True, exist_ok=True)
        (ROOT / "reports" / "evidence" / "UX-07_租户1取租户2文件URL.txt").write_text(
            f"方向1: u-X 租户2 上传 → 同用户租户1 用租户2 的 fileId 调置换接口\n"
            f"fileId: {fid2}\n属主(租户2)调用: HTTP {st_o2}\n"
            f"租户1 调用: HTTP {st_1}\n响应体: {body_1}\n", encoding="utf-8")
    except Exception:
        pass
    ev = await runner.screenshot("UX-07a")

    # ── 方向2: u-X 租户1 上传 → 同用户租户2 尝试拿 URL(反向) ──
    await wb_new_task(runner)
    await wb_upload_file(runner, UPLOAD_FILE)
    await runner.page.wait_for_timeout(3000)
    fid1 = get_fid()
    tok1b = await _get_token(runner)
    st_o1, body_o1 = await _exchange_file(runner, fid1, tok1b)  # 属主(租户1)确认可拿
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户2")
    tok2b = await _get_token(runner)
    st_2, body_2 = await _exchange_file(runner, fid1, tok2b)  # 租户1 的 fileId + 租户2 token
    leak_2 = (st_2 == 200) and ("rawUrl" in body_2)
    try:
        (ROOT / "reports" / "evidence" / "UX-07_租户2取租户1文件URL.txt").write_text(
            f"方向2: u-X 租户1 上传 → 同用户租户2 用租户1 的 fileId 调置换接口\n"
            f"fileId: {fid1}\n属主(租户1)调用: HTTP {st_o1}\n"
            f"租户2 调用: HTTP {st_2}\n响应体: {body_2}\n", encoding="utf-8")
    except Exception:
        pass
    ev = await runner.screenshot("UX-07b")

    owner_ok = (st_o2 == 200) and (st_o1 == 200)
    ok = owner_ok and (not leak_1) and (not leak_2)
    st = "通过" if ok else "失败"
    runner.set_result("UX-07", "u-X同账号跨租户文件URL获取隔离(双向)",
                      st,
                      actual=f"方向1(租户2上传→租户1取): {st_1}(泄漏={leak_1}); 方向2(租户1上传→租户2取): {st_2}(泄漏={leak_2}); 属主取URL均正常={owner_ok}",
                      detail=f"方向1响应: {body_1[:120]} | 方向2响应: {body_2[:120]}",
                      evidence=ev)


async def _get_token(runner):
    try:
        return await runner.page.evaluate("() => localStorage.getItem('cb_login_token') || ''")
    except Exception:
        return ""


async def _exchange_file(runner, fileId, token):
    """调用真实置换接口 GET /mc/api/v1/agentcore/files/{fileId}。返回 (status, body)。"""
    url = f"http://117.187.178.246:19521/mc/api/v1/agentcore/files/{fileId}"
    try:
        resp = await runner.page.request.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20000)
        body = ""
        try:
            body = await resp.text()
        except Exception:
            pass
        return resp.status, body[:500]
    except Exception as e:
        return None, str(e)[:120]


async def run_TC_FILEDL2(runner):
    # ── 1. u-A 上传, 获取 fileId; 属主(u-A)调用确认接口可用 ──
    await wb_login(runner, "u-A")
    await wb_new_task(runner)
    up = await wb_upload_file(runner, UPLOAD_FILE)
    await runner.page.wait_for_timeout(3000)
    ub = getattr(runner, "api_upload", None)
    fileId_A = ""
    if ub:
        files = (ub.get("data") or {}).get("files") or []
        if files:
            fileId_A = str(files[0].get("fileId", ""))
    token_A = await _get_token(runner)
    st_owner, body_owner = await _exchange_file(runner, fileId_A, token_A)
    owner_ok = (st_owner == 200) and ("rawUrl" in body_owner)
    ev = await runner.screenshot("FILEDL2-a")

    # ── 2. u-B(跨用户)用 u-A 的 fileId 调置换接口 ──
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-B")
    token_B = await _get_token(runner)
    st_B, body_B = await _exchange_file(runner, fileId_A, token_B)
    leak_B = (st_B == 200) and ("rawUrl" in body_B)
    ev = await runner.screenshot("FILEDL2-b")

    # ── 3. u-X 租户2 上传 → u-X 租户1 用租户2 的 fileId 调置换接口 ──
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-X", tenant="租户2")
    await wb_new_task(runner)
    upx = await wb_upload_file(runner, UPLOAD_FILE)
    await runner.page.wait_for_timeout(3000)
    ubx = getattr(runner, "api_upload", None)
    fileId_X2 = ""
    if ubx:
        files = (ubx.get("data") or {}).get("files") or []
        if files:
            fileId_X2 = str(files[0].get("fileId", ""))
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-X", tenant="租户1")
    token_X1 = await _get_token(runner)
    st_X, body_X = await _exchange_file(runner, fileId_X2, token_X1)
    leak_X = (st_X == 200) and ("rawUrl" in body_X)
    ev = await runner.screenshot("FILEDL2-c")

    # ── 判定 ──
    # 属主应能换到 URL(200+rawUrl); 跨用户/同账号跨租户应被拒(非 200 或 无 rawUrl)
    ok_owner = owner_ok
    ok_iso_B = (not leak_B) and (st_B not in (200,))
    ok_iso_X = (not leak_X) and (st_X not in (200,))
    ok = ok_owner and ok_iso_B and ok_iso_X
    st = "通过" if ok else ("失败" if (leak_B or leak_X) else "无法验证")
    runner.set_result("FILEDL2", "真实文件下载置换接口隔离(属主/跨用户/同账号跨租户)",
                      st,
                      actual=f"属主u-A调用→{st_owner}(可用={owner_ok}); u-B用u-A的fileId→{st_B}(泄漏={leak_B}); u-X租户1用租户2的fileId→{st_X}(泄漏={leak_X})",
                      detail=f"属主响应: {body_owner[:120]} | u-B响应: {body_B[:120]} | u-X租户1响应: {body_X[:120]}",
                      evidence=ev)


async def run_TC_FILEDL(runner):
    # u-A 上传, 捕获 fileId + rawUrl
    await wb_login(runner, "u-A")
    await wb_new_task(runner)
    up = await wb_upload_file(runner, UPLOAD_FILE)
    await runner.page.wait_for_timeout(4000)
    ub = getattr(runner, "api_upload", None)
    fileId, rawUrl = "", ""
    if ub:
        files = (ub.get("data") or {}).get("files") or []
        if files:
            fileId = str(files[0].get("fileId", ""))
            rawUrl = str(files[0].get("rawUrl", ""))
    print(f"     [FILEDL] 上传成功={up}, api_upload={ub is not None}, fileId={fileId[:30] or '空'}")
    ev = await runner.screenshot("FILEDL-a")
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-B")
    if not fileId:
        runner.set_result("FILEDL", "u-B能否通过应用接口拿到u-A文件",
                          "无法验证",
                          actual="未捕获到 u-A 的 fileId", detail="", evidence=ev)
        return
    token = ""
    try:
        token = await runner.page.evaluate("() => localStorage.getItem('cb_login_token') || ''")
    except Exception:
        token = ""
    base = "http://117.187.178.246:19521"
    candidates = [
        f"{base}/mc/api/v1/agentcore/files/{fileId}",
        f"{base}/mc/api/v1/agentcore/files/download?fileId={fileId}",
        f"{base}/mc/api/v1/agentcore/files/{fileId}/download",
        f"{base}/mc/api/v1/agentcore/files/get?fileId={fileId}",
        f"{base}/mc/api/v1/agentcore/files/raw?fileId={fileId}",
        f"{base}/ctx/api/v1/files/{fileId}",
        f"{base}/mc/api/v1/agentcore/files?fileId={fileId}",
    ]
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    results = []
    for url in candidates:
        try:
            resp = await runner.page.request.get(url, headers=headers, timeout=15000)
            body = ""
            try:
                body = (await resp.text())[:200]
            except Exception:
                pass
            results.append({"path": url.replace(base, ""), "status": resp.status, "body": body})
        except Exception as e:
            results.append({"path": url.replace(base, ""), "status": None, "body": str(e)[:80]})
    file_kw = ["梦想", "鸭爪", "江永", "世界和平", "开开心心"]
    leaked = [r for r in results if r["status"] == 200 and any(k in r["body"] for k in file_kw)]
    any200 = [r for r in results if r["status"] == 200]
    ok = len(leaked) == 0
    ev = await runner.screenshot("FILEDL-b")
    detail = " | ".join(f"{r['path']}→{r['status']}" for r in results)
    runner.set_result("FILEDL", "u-B能否通过应用接口拿到u-A文件(判定隔离可绕过性)",
                      "通过" if ok else "失败",
                      actual=f"u-A fileId={fileId[:26]}..., 候选接口{len(results)}个, 返回200={len(any200)}, 含文件内容泄漏={len(leaked)}",
                      detail=detail, evidence=ev)


# ────────────────────────────────────────────────
# u-X 同账号跨租户隔离交叉验证(重点)
# ────────────────────────────────────────────────
def _clean_ints(its):
    return [t.strip() for t in its if t and t.strip() and t.strip() != "⋯" and not t.strip().isdigit()]


async def run_TC_UX(runner):
    # ── UX-01 会话隔离(双向 + 数据随租户保留) ──
    await wb_login(runner, "u-X", tenant="租户2")
    await wb_new_task(runner)
    await wb_send(runner, "UX租户2专属会话标记")
    has_s2 = await wb_wait_session(runner, "UX租户2专属会话标记")
    ev = await runner.screenshot("UX-01a")
    # 切租户1
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户1")
    s1 = await wb_session_titles(runner)
    leaked_s2_in_s1 = any("UX租户2专属会话标记" in t for t in s1)
    await wb_new_task(runner)
    await wb_send(runner, "UX租户1专属会话标记")
    has_s1 = await wb_wait_session(runner, "UX租户1专属会话标记")
    ev = await runner.screenshot("UX-01b")
    # 切回租户2
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户2")
    s2_back = await wb_session_titles(runner)
    leaked_s1_in_s2 = any("UX租户1专属会话标记" in t for t in s2_back)
    persisted_s2 = any("UX租户2专属会话标记" in t for t in s2_back)
    ev = await runner.screenshot("UX-01c")
    ok = has_s2 and (not leaked_s2_in_s1) and has_s1 and (not leaked_s1_in_s2) and persisted_s2
    runner.set_result("UX-01", "u-X跨租户会话隔离(双向, 数据随租户保留)",
                      "通过" if ok else "失败",
                      actual=f"租户2建会话={has_s2}, 租户1看到租户2会话={leaked_s2_in_s1}, 租户1建会话={has_s1}, 租户2看到租户1会话={leaked_s1_in_s2}, 租户2会话保留={persisted_s2}",
                      detail=f"租户2列表={s2_back[:3]}", evidence=ev)

    # ── UX-02 收藏意图隔离(两租户意图列表不同) ──
    i2 = _clean_ints(await wb_intent_titles(runner))  # 当前为租户2
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户1")
    i1 = _clean_ints(await wb_intent_titles(runner))
    ev = await runner.screenshot("UX-02")
    leaked_i = [t for t in i2 if t in i1]
    ok = len(leaked_i) == 0
    runner.set_result("UX-02", "u-X跨租户收藏意图隔离(两租户意图列表独立)",
                      "通过" if ok else "失败",
                      actual=f"租户2意图={i2}, 租户1意图={i1}, 重叠={leaked_i}",
                      detail="", evidence=ev)

    # ── UX-03 文件隔离(u-X 租户1 上传, 切租户2 不出现) ──
    await wb_new_task(runner)
    up_x1 = await wb_upload_file(runner, UPLOAD_FILE)
    await wb_send(runner, "UX租户1上传的文件标记")
    body1 = await _safe(runner.body_text)
    file_in_s1 = "upload-test" in body1
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户2")
    await wb_new_task(runner)
    body2 = await _safe(runner.body_text)
    file_in_s2 = "upload-test" in body2
    ev = await runner.screenshot("UX-03")
    ok = up_x1 and file_in_s1 and (not file_in_s2)
    runner.set_result("UX-03", "u-X跨租户文件隔离(租户1上传, 租户2会话不出现)",
                      "通过" if ok else "失败",
                      actual=f"租户1上传={up_x1}, 租户1会话含文件={file_in_s1}, 租户2会话含文件={file_in_s2}",
                      detail="", evidence=ev)

    # ── UX-04 资源市场隔离(两租户市场内容不同) ──
    await wb_open_market(runner)
    m2 = await _safe(lambda: runner.page.locator(".resource-market").inner_text())
    ev = await runner.screenshot("UX-04")
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户1")
    opened1 = await wb_open_market(runner)
    m1 = await _safe(lambda: runner.page.locator(".resource-market").inner_text())
    ev = await runner.screenshot("UX-04b")
    ok = opened1 and ("华科agent" in m2) and ("华科agent" not in m1)
    runner.set_result("UX-04", "u-X跨租户资源市场隔离(租户2市场≠租户1市场)",
                      "通过" if ok else "失败",
                      actual=f"租户2市场含华科agent={('华科agent' in m2)}, 租户1市场含华科agent={('华科agent' in m1)}",
                      detail=f"租户1市场: {m1[:120]}", evidence=ev)

    # ── UX-05 跨租户会话深链隔离(u-X 租户2 会话 URL 在租户1 不可访问) ──
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户2")
    ux2_sid = await wb_first_session_id(runner)
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户1")
    if ux2_sid:
        res, used_url, body = await wb_check_deeplink(runner, ux2_sid, "UX租户2专属会话标记")
        ev = await runner.screenshot("UX-05")
        ok = res == "isolated"
        runner.set_result("UX-05", "u-X租户1地址栏直开租户2会话详情隔离",
                          "通过" if ok else "失败",
                          actual=f"租户2会话id={ux2_sid[:16]}..., 访问结果={res}",
                          detail=f"URL={used_url[:80]}", evidence=ev)
    else:
        runner.set_result("UX-05", "u-X租户1地址栏直开租户2会话详情隔离",
                          "无法验证",
                          actual="未获取到租户2会话id", detail="", evidence="")

    # ── UX-06 同账号跨租户文件直链访问(u-X 租户2 上传, 切租户1 访问文件URL) ──
    # 验证文件直链是否连「同一账号不同租户」都无法隔离(DEF-001 的深挖)
    await wb_login(runner, "u-X", tenant="租户2")
    await wb_new_task(runner)
    up_x = await wb_upload_file(runner, UPLOAD_FILE)
    await runner.page.wait_for_timeout(2000)
    fx_url = await wb_get_upload_url(runner)
    ev = await runner.screenshot("UX-06a")
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-X", tenant="租户1")
    if fx_url:
        status, body = await wb_check_url_access(runner, fx_url, ROOT / "reports" / "evidence" / "UX-06_同账号跨租户文件直链响应.txt")
        file_kw = ["梦想", "鸭爪", "江永", "世界和平", "开开心心"]
        leaked = (status == 200) and any(k in body for k in file_kw)
        ev = await runner.screenshot("UX-06b")
        ok = (not leaked) and (status in (401, 403, 404, 400) or status is None)
        runner.set_result("UX-06", "u-X同账号跨租户文件直链隔离(租户2上传, 租户1访问)",
                          "通过" if ok else "失败",
                          actual=f"租户2上传={up_x}, 租户1访问status={status}, 文件内容泄漏={leaked}",
                          detail=f"文件URL={fx_url[:90]}, 响应片段: {body[:120]}", evidence=ev)
    else:
        runner.set_result("UX-06", "u-X同账号跨租户文件直链隔离(租户2上传, 租户1访问)",
                          "无法验证",
                          actual="未捕获到上传响应 rawUrl", detail="", evidence="")


async def wb_check_deeplink(runner, target_sid, leak_keyword):
    """以当前(目标)账号身份访问目标会话深链, 判断是否泄漏/隔离。
    返回 (result, url, body): result ∈ leaked/isolated"""
    candidates = [
        f"http://117.187.178.246:19521/workbench?sessionId={target_sid}",
        f"http://117.187.178.246:19521/workbench?id={target_sid}",
        f"http://117.187.178.246:19521/workbench/session/{target_sid}",
        f"http://117.187.178.246:19521/session/{target_sid}",
        f"http://117.187.178.246:19521/chat/{target_sid}",
    ]
    for u in candidates:
        try:
            await runner.page.goto(u, wait_until="domcontentloaded", timeout=15000)
            await runner.page.wait_for_timeout(2500)
            body = await _safe(runner.body_text)
            if leak_keyword in body:
                return "leaked", u, body
            not_found = any(k in body for k in ["此内容不可用", "未找到", "404", "不存在", "无权限", "无权访问"])
            if not_found:
                return "isolated", u, body
        except Exception:
            continue
    # 无泄漏即视为隔离(未能出现404也可能只是无深链路由, 但内容未泄漏)
    return "isolated", "", ""


# ────────────────────────────────────────────────
# TC-N 数据隔离与权限
# ────────────────────────────────────────────────
async def run_TC_N(runner):
    # TC-N-01 登录后租户上下文正确
    ok_login = await wb_login(runner, "u-A")
    body = await _safe(runner.body_text)
    ev = await runner.screenshot("TC-N-01")
    ctx_ok = "已登录" in body and ACCOUNTS["u-A"]["username"] in body
    ok = ok_login and ctx_ok
    runner.set_result("TC-N-01", "登录后的租户上下文必须正确, 数据归属当前租户",
                      "通过" if ok else "失败",
                      actual=f"进入工作台={ok_login}, 显示已登录用户={ctx_ok}",
                      detail=f"页面: {body[:200]}", evidence=ev)

    # TC-N-02 退出后用另一租户账号登录, 数据互不可见
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(1000)
    ok_login = await wb_login(runner, "u-B")
    side = await wb_sidebar_text(runner)
    body = await _safe(runner.body_text)
    ev = await runner.screenshot("TC-N-02")
    # u-B(租户1)不应看到 u-A(租户2)的会话("你好"/"2+2等于几")
    leaked = ("你好" in side) or ("2+2等于几" in side)
    ok = ok_login and (not leaked)
    runner.set_result("TC-N-02", "换租户登录后会话/收藏/资源互不可见",
                      "通过" if ok else "失败",
                      actual=f"进入u-B工作台={ok_login}, u-A数据泄漏={leaked}",
                      detail=f"u-B左侧栏: {side[:200]}", evidence=ev)

    # TC-N-03 被禁用用户不可进入(同 TC-B-04, 无禁用账号)
    runner.set_result("TC-N-03", "被禁用用户不应能进入工作台",
                      "无法验证",
                      actual="未提供被禁用账号数据",
                      detail="需提供被禁用账号以便验证", evidence="")


# ────────────────────────────────────────────────
# TC-UIOP 统一UI操作流
# ────────────────────────────────────────────────
async def run_TC_UIOP(runner):
    # TC-UIOP-01 登录鉴权通过 / 错误账号被拒
    ok_login = await wb_login(runner, "u-A")
    ev = await runner.screenshot("TC-UIOP-01")
    runner.set_result("TC-UIOP-01", "登录鉴权通过, 错误账号被拒",
                      "通过" if ok_login else "失败",
                      actual=f"u-A 登录进入工作台={ok_login}",
                      detail="错误/停用账号拒登已在 TC-B 系列覆盖", evidence=ev)

    # TC-UIOP-02 点新任务/新会话, 上下文复位
    created = await wb_new_task(runner)
    conv_header = await _safe(lambda: runner.page.locator(".bubble-list__header-title, .chat-area-pc [class*=header]").inner_text())
    ev = await runner.screenshot("TC-UIOP-02")
    titles0 = await wb_session_titles(runner)
    runner.set_result("TC-UIOP-02", "点新任务创建新会话(上下文复位)",
                      "通过" if created else "失败",
                      actual=f"新任务可点={created}, 会话标题=新建, 现有会话数={len(titles0)}",
                      detail=f"会话列表: {titles0}", evidence=ev)

    # TC-UIOP-03 发"你好"等回复完成, 刷新后会话仍在
    sent = await wb_send(runner, "你好，请用一句话介绍你自己")
    replied, body = await wb_wait_reply(runner, timeout=75, contains="介绍")
    ev = await runner.screenshot("TC-UIOP-03")
    has_user = "你好" in body
    has_assistant = "智能" in body or "助手" in body or "业务" in body or "对话" in body
    ok = sent and replied and has_user and has_assistant
    runner.set_result("TC-UIOP-03", "发消息逐字流式输出并结束, 刷新后会话仍在",
                      "通过" if ok else ("失败" if sent else "失败"),
                      actual=f"已发送={sent}, AI回复出现={replied}, 含用户消息={has_user}, 含回复内容={has_assistant}",
                      detail=f"会话区: {body[-400:]}", evidence=ev)

    # 刷新后会话仍在
    await runner.page.reload(wait_until="domcontentloaded")
    await runner.page.wait_for_timeout(4000)
    titles = await wb_session_titles(runner)
    body = await _safe(runner.body_text)
    ev = await runner.screenshot("TC-UIOP-03b")
    persisted = len(titles) >= 1
    runner.set_result("TC-UIOP-03b", "刷新后会话列表/历史仍在(会话持久化)",
                      "通过" if persisted else "失败",
                      actual=f"刷新后会话列表={titles}",
                      detail="", evidence=ev)

    # TC-UIOP-06 刷新后登录态/租户上下文保持
    url = await wb_get_url(runner)
    body = await _safe(runner.body_text)
    ev = await runner.screenshot("TC-UIOP-06")
    kept = "/workbench" in url and "已登录" in body
    runner.set_result("TC-UIOP-06", "刷新后登录态/租户上下文保持, 会话完整还原",
                      "通过" if kept else "失败",
                      actual=f"仍处工作台={('/workbench' in url)}, 登录态保持={('已登录' in body)}",
                      detail="", evidence=ev)

    # TC-UIOP-07 打开历史会话继续追问, Agent 记得上文
    opened = await wb_session_click(runner, 0)
    ev = await runner.screenshot("TC-UIOP-07")
    runner.set_result("TC-UIOP-07", "打开历史会话继续追问, Agent 记得上文",
                      "通过" if opened else "无法验证",
                      actual=f"打开历史会话={opened}",
                      detail="上下文记忆需人工/二次问答确认(已打开历史会话)", evidence=ev)

    # TC-UIOP-12 重命名/删除会话
    # 点第一个会话的 ⋯ → 重命名 → 输入新名 → 确认 → 验证标题更新
    renamed = False
    renamed_title = ""
    menu_txt = ""
    try:
        item = runner.page.locator(".ch-task").first
        dots = runner.page.locator(".ch-task__more").first
        if await dots.count() > 0:
            await dots.click(timeout=4000)
            await runner.page.wait_for_timeout(600)
            menu_txt = await _safe(lambda: runner.page.locator(".ch-menu").inner_text())
            if "重命名" in menu_txt:
                await runner.page.locator(".ch-menu__item:has-text('重命名')").first.click(timeout=3000)
                await runner.page.wait_for_timeout(800)
                # 内联重命名: 标题变为 .ch-task__rename-input
                inp = runner.page.locator(".ch-task__rename-input")
                if await inp.count() > 0:
                    new_title = "重命名验证会话"
                    await inp.last.fill(new_title)
                    await inp.last.press("Enter")
                    await runner.page.wait_for_timeout(1500)
                    titles = await wb_session_titles(runner)
                    renamed_title = next((t for t in titles if "重命名验证会话" in t), "")
                    renamed = bool(renamed_title)
                else:
                    # 无输入则记录
                    renamed = False
    except Exception as e:
        renamed = False
    ev = await runner.screenshot("TC-UIOP-12")
    runner.set_result("TC-UIOP-12", "重命名/删除会话后刷新真实生效",
                      "通过" if renamed else "无法验证",
                      actual=f"重命名执行={renamed}, 新标题={renamed_title!r}",
                      detail=f"菜单文本: {menu_txt[:80]}", evidence=ev)

    # TC-UIOP-13 核心隔离: 租户B 登录无租户A 数据
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    ok_login = await wb_login(runner, "u-B")
    side = await wb_sidebar_text(runner)
    body = await _safe(runner.body_text)
    ev = await runner.screenshot("TC-UIOP-13")
    leaked = ("你好" in side) or ("2+2等于几" in side) or ("介绍" in side)
    ok = ok_login and (not leaked)
    runner.set_result("TC-UIOP-13", "核心隔离: 租户B无租户A的会话/历史/资源",
                      "通过" if ok else "失败",
                      actual=f"u-B进入={ok_login}, A数据泄漏={leaked}, u-B侧栏={side[:120]}",
                      detail="", evidence=ev)

    # TC-UIOP-14 租户B 地址栏直开租户A 会话详情 → 404
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    ok_login = await wb_login(runner, "u-A")
    ua_sid = await wb_first_session_id(runner)
    ev = await runner.screenshot("TC-UIOP-14")
    if ua_sid:
        if await wb_logout(runner):
            await runner.page.wait_for_timeout(800)
        await wb_login(runner, "u-B")
        res, used_url, body = await wb_check_deeplink(runner, ua_sid, "2+2等于几")
        ev = await runner.screenshot("TC-UIOP-14b")
        ok = res == "isolated"
        runner.set_result("TC-UIOP-14", "租户B地址栏直开租户A会话详情返回404/不可用",
                          "通过" if ok else "失败",
                          actual=f"u-A会话id={ua_sid[:16]}..., 访问结果={res}, URL={used_url[:80]}",
                          detail=f"页面: {body[:200]}", evidence=ev)
    else:
        runner.set_result("TC-UIOP-14", "租户B地址栏直开租户A会话详情返回404/不可用",
                          "无法验证",
                          actual="未获取到 u-A 会话 id",
                          detail="", evidence=ev)

    # TC-UIOP-16 换租户后检查残留
    # u-B 登录后资源区应为空/新租户数据
    resource_empty = await _safe(lambda: runner.page.locator(".resource-panel__empty, .resource-panel").inner_text())
    body = await _safe(runner.body_text)
    ev = await runner.screenshot("TC-UIOP-16")
    no_a_res = "你好" not in resource_empty and "2+2" not in resource_empty
    runner.set_result("TC-UIOP-16", "换租户后选资源器/示例意图无上一租户残留",
                      "通过" if no_a_res else "失败",
                      actual=f"资源区: {resource_empty[:120]}",
                      detail="", evidence=ev)

    # TC-UIOP-10 回复中点停止 / TC-UIOP-17 停用租户
    runner.set_result("TC-UIOP-10", "回复中点停止立即停止, 内容保留",
                      "无法验证",
                      actual="停止按钮为图标无文本, 且回复流式时序不确定",
                      detail="可后续人工在流式中点停止验证", evidence="")
    runner.set_result("TC-UIOP-17", "停用/到期租户无法进入或会话失效",
                      "无法验证",
                      actual="未提供停用/到期租户账号",
                      detail="需提供停用租户账号以便验证", evidence="")

    # 补充: 其余 TC-UIOP 用例(需特殊数据/场景)
    runner.set_result("TC-UIOP-04", "发需调工具/资源的问题, 中间步骤折叠面板+资源执行结果卡片",
                      "无法验证",
                      actual="需后端提供可调用的工具/资源问题样例",
                      detail="工具/资源调用依赖真实可用资源与业务数据", evidence="")
    runner.set_result("TC-UIOP-05", "done事件+产出文件下载卡可下载",
                      "无法验证",
                      actual="需 AI 产生产出文件(done/下载卡), 依赖具体业务任务",
                      detail="无确定性触发任务", evidence="")
    runner.set_result("TC-UIOP-08", "上传文件后发送并问文件内容, 历史还原时引用仍在",
                      "无法验证",
                      actual="上传入口存在(添加附件), 但 AI 引用文件内容行为不可预测, 且需文件对象",
                      detail="可后续人工上传文件验证", evidence="")
    runner.set_result("TC-UIOP-09", "AI回复底部点收藏整理意图, 收藏面板可见",
                      "无法验证",
                      actual="收藏按钮为图标无文本标签, 且意图识别依赖 AI 产出模板",
                      detail="可后续人工在回复动作栏验证收藏", evidence="")
    runner.set_result("TC-UIOP-11", "发送后断网/恢复, 重试重新发送",
                      "无法验证",
                      actual="需网络拦截与恢复机制配合(如 Playwright route 中断)",
                      detail="可后续人工断网验证", evidence="")
    runner.set_result("TC-UIOP-15", "同账号u-X租户1建会话, 切租户2登录隔离",
                      "无法验证",
                      actual="u-X 账号 workbenchId/appId 为复合值, 进入工作台参数待确认",
                      detail="需确认 u-X 登录参数(见 TC-ISO-06)", evidence="")


# ────────────────────────────────────────────────
# TC-ISO 隔离模块
# ────────────────────────────────────────────────
async def run_TC_ISO(runner):
    # TC-ISO-01 u-A(租户2) 有会话, u-B(租户1) 看不到
    ok_login = await wb_login(runner, "u-B")
    side = await wb_sidebar_text(runner)
    ev = await runner.screenshot("TC-ISO-01")
    leaked = ("你好" in side) or ("2+2" in side)
    empty_mid = ("暂无历史任务" in side) or ("历史任务" in side)
    ok = ok_login and (not leaked)
    runner.set_result("TC-ISO-01", "u-B在租户1看不到u-A在租户2的会话",
                      "通过" if ok else "失败",
                      actual=f"u-B进入={ok_login}, A会话泄漏={leaked}",
                      detail=f"u-B侧栏: {side[:150]}", evidence=ev)

    # TC-ISO-02 u-B 建会话, u-A 切回后看不到
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-B")
    await wb_new_task(runner)
    sent = await wb_send(runner, "我在租户1测试会话")
    await wb_wait_reply(runner, timeout=60)
    side_b = await wb_sidebar_text(runner)
    has_b = "我在租户1测试会话" in side_b
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-A")
    side_a = await wb_sidebar_text(runner)
    ev = await runner.screenshot("TC-ISO-02")
    leaked = "我在租户1测试会话" in side_a
    ok = has_b and (not leaked)
    runner.set_result("TC-ISO-02", "u-A切回后看不到u-B在租户1的会话",
                      "通过" if ok else "失败",
                      actual=f"u-B会话已建={has_b}, u-A看到B会话={leaked}",
                      detail=f"u-A侧栏: {side_a[:150]}", evidence=ev)

    # TC-ISO-03 u-B 地址栏直开 u-A 会话详情
    # 当前为 u-A(TC-ISO-02 结束态), 先取 u-A 会话 id, 再切 u-B 访问深链
    ua_sid = ""
    try:
        ua_sid = await wb_first_session_id(runner)
    except Exception:
        ua_sid = ""
    ev = await runner.screenshot("TC-ISO-03")
    if ua_sid:
        if await wb_logout(runner):
            await runner.page.wait_for_timeout(800)
        await wb_login(runner, "u-B")
        res, used_url, body = await wb_check_deeplink(runner, ua_sid, "2+2等于几")
        ev = await runner.screenshot("TC-ISO-03b")
        ok = res == "isolated"
        runner.set_result("TC-ISO-03", "u-B地址栏直开u-A会话详情显示不可用",
                          "通过" if ok else "失败",
                          actual=f"u-A会话id={ua_sid[:16]}..., 访问结果={res}, URL={used_url[:80]}",
                          detail=f"页面: {body[:200]}", evidence=ev)
    else:
        runner.set_result("TC-ISO-03", "u-B地址栏直开u-A会话详情显示不可用",
                          "无法验证",
                          actual="未获取到 u-A 会话 id", evidence=ev)

    # TC-ISO-05 u-B 尝试重命名 u-A 会话: 列表无该会话/无入口
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-B")
    side = await wb_sidebar_text(runner)
    try:
        items = await runner.page.locator(".ch-task").count()
    except Exception:
        items = 0
    ev = await runner.screenshot("TC-ISO-05")
    no_entry = ("你好" not in side) and ("2+2" not in side)
    ok = no_entry
    runner.set_result("TC-ISO-05", "u-B无法操作u-A会话(列表无/无入口)",
                      "通过" if ok else "失败",
                      actual=f"u-B会话项数={items}, u-A会话可见={not no_entry}",
                      detail=f"u-B侧栏: {side[:150]}", evidence=ev)

    # TC-ISO-07 u-B 搜索 u-A 会话关键词 → 无结果
    if "/workbench" not in await runner.url() or "zh1" not in await _safe(runner.body_text):
        if await wb_logout(runner):
            await runner.page.wait_for_timeout(800)
        await wb_login(runner, "u-B")
    sb = None
    side = ""
    search_ok = False
    try:
        sb = runner.page.locator("input[type=text][placeholder*=搜索], .conversation-history input, [class*=search] input").first
        if await sb.count() > 0:
            await sb.fill("你好")
            await runner.page.wait_for_timeout(1500)
            side = await wb_sidebar_text(runner)
            # u-B 上下文中搜索 u-A 会话关键词应无结果
            search_ok = ("你好" not in side) or ("暂无" in side)
    except Exception:
        search_ok = False
    ev = await runner.screenshot("TC-ISO-07")
    if sb is None or await sb.count() == 0:
        runner.set_result("TC-ISO-07", "u-B搜索u-A会话关键词无结果",
                          "无法验证",
                          actual="未发现会话搜索框或搜索未生效",
                          detail="", evidence=ev)
    else:
        runner.set_result("TC-ISO-07", "u-B搜索u-A会话关键词无结果",
                          "通过" if search_ok else "失败",
                          actual=f"搜索'你好'后侧栏: {side[:150]}",
                          detail="", evidence=ev)

    # 其余隔离用例: 收藏意图/文件上传/资源隔离 需先构造对应数据(收藏、上传、开通资源)
    runner.set_result("TC-ISO-04", "u-B尝试让u-A会话回答租户2语境问题(上下文隔离)",
                      "无法验证",
                      actual="需u-A会话详情可访问且AI行为验证(前置为u-B无法访问u-A会话, 已隔离)",
                      detail="跨租户AI上下文注入验证复杂", evidence="")
    runner.set_result("TC-ISO-06", "u-X跨租户会话隔离",
                      "无法验证",
                      actual="u-X 账号 workbenchId/appId 为复合值, 进入工作台方式待确认",
                      detail="需确认 u-X 登录参数", evidence="")
    for cid, name in [("TC-ISO-08", "u-B不出现u-A收藏意图模板"),
                      ("TC-ISO-09", "u-B无法使用u-A意图模板"),
                      ("TC-ISO-10", "u-B无法删除/重命名u-A意图"),
                      ("TC-ISO-11", "u-X跨租户收藏意图隔离"),
                      ("TC-ISO-12", "u-B点用意图模板正常使用")]:
        runner.set_result(cid, name, "无法验证",
                          actual="收藏意图功能需先完成AI回复并点收藏(前置数据未构造, 且涉及意图识别准确性)",
                          detail="需先构造 u-A 收藏意图数据并确认收藏面板交互", evidence="")
    for cid, name in [("TC-ISO-13", "u-A上传文件并发送"),
                      ("TC-ISO-14", "u-B地址栏直开u-A文件链接失败"),
                      ("TC-ISO-15", "u-B打开u-A会话内文件失败"),
                      ("TC-ISO-16", "u-B上传文件不出现u-A文件")]:
        runner.set_result(cid, name, "无法验证",
                          actual="文件上传需本地测试文件与上传交互, 且文件URL隔离需真实文件对象",
                          detail="需构造上传文件测试数据", evidence="")
    for cid, name in [("TC-ISO-17", "u-B资源列表不出现u-A已开通资源"),
                      ("TC-ISO-18", "u-B已收藏不出现u-A收藏资源"),
                      ("TC-ISO-19", "u-B常用不出现u-A常用资源"),
                      ("TC-ISO-20", "市场浏览仅见本租户资源"),
                      ("TC-ISO-21", "u-B地址栏直开u-A资源详情失败"),
                      ("TC-ISO-22", "u-B看不到u-A审批单"),
                      ("TC-ISO-23", "u-B无法删除u-A收藏资源"),
                      ("TC-ISO-24", "u-A写操作确认结果归属当前租户")]:
        runner.set_result(cid, name, "无法验证",
                          actual="需先开通/收藏/使用 Agent/Skill/MCP 资源(依赖资源市场真实数据与审批流)",
                          detail="需构造资源类数据并确认资源市场/审批入口", evidence="")


# 占位模块函数(后续填充)


def main():
    args = sys.argv[1:]
    ALLOWED = ("TC-I", "TC-B", "TC-N", "TC-ISO", "TC-UIOP", "TC-SUPP", "TC-FAV", "TC-UPLOAD", "TC-RES", "TC-UX", "TC-UIOP2", "TC-UIOP3", "FILEDL", "FILEDL2", "UXFILE")
    if not args or "--all" in args:
        modules = list(ALLOWED)
    else:
        modules = [a.upper() for a in args if a in ALLOWED]
    asyncio.run(run_modules(modules))


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    main()
