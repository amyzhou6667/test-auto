# -*- coding: utf-8 -*-
"""
通用执行引擎：Result 数据类 + Runner 浏览器基座 + 表驱动用例调度。

从 execute_test_cases.py 抽取的约 200 行可复用基座，通用化 + 修复引擎侧接缝 bug：
  - bug1  run_case 空实现 → 删除，由 run_case_table 取代
  - bug2  screenshot 的 _seq 从未参与文件名 → 接入防同秒覆盖
  - bug6  save_report 在 try/finally 之外 → 由调度层在 finally 内保存（见 run_project.py）
  - 资源泄漏: close() 未调用 playwright 实例 stop() → 补上
  - _on_response 的两条 CoreBridge 嗅探 → 改为配置驱动嗅探规则表
  - 状态图标表（原 248/349 两份重复）→ 统一从 cfg.status.icons 读取
"""
from datetime import datetime

from playwright.async_api import async_playwright


class Result:
    """单条用例结果。to_dict 输出键名 id（下游报告依赖）。"""

    def __init__(self, case_id, name, status="未执行", actual="", detail="", evidence=""):
        self.case_id = case_id
        self.name = name
        self.status = status  # 通过/失败/无法验证/未执行（扩展状态见项目配置 status.enums）
        self.actual = actual
        self.detail = detail
        self.evidence = evidence  # 截图路径

    def to_dict(self):
        return {"id": self.case_id, "name": self.name, "status": self.status,
                "actual": self.actual, "detail": self.detail, "evidence": self.evidence}


class Runner:
    """浏览器基座：负责启动/关闭、网络捕获、截图、结果登记。

    项目专属页面操作（登录弹窗 DOM 等）由项目 hooks 里的 Runner 子类扩展，
    基座本身不包含任何项目假设。
    """

    def __init__(self, modules=None, cfg=None):
        self.modules = modules or []
        self.cfg = cfg
        self.results = {}
        self.browser = None
        self.context = None
        self.page = None
        self._p = None  # playwright 实例（close 时需 stop，防资源泄漏）
        self.api_log = []           # 网络请求日志 [{url, status, ts}]
        self._seq = 0

    # ─────────── 浏览器基座 ───────────
    async def start(self):
        browser_cfg = (self.cfg.browser if self.cfg else {}) or {}
        headless = bool(browser_cfg.get("headless", False))
        channel = browser_cfg.get("channel", "chrome")
        viewport = browser_cfg.get("viewport") or {"width": 1920, "height": 1080}

        self._p = await async_playwright().start()
        self.browser = await self._p.chromium.launch(headless=headless, channel=channel)
        self.context = await self.browser.new_context(viewport=viewport)
        self.page = await self.context.new_page()
        self.page.on("response", self._on_response)

        if self.cfg:
            for key in ("results", "screenshots", "reports", "evidence"):
                try:
                    self.cfg.resolve_path(key).mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self._p:
            await self._p.stop()  # 修复资源泄漏

    async def _on_response(self, resp):
        """网络响应监听：记录日志 + 按配置嗅探规则表捕获响应体。"""
        try:
            self.api_log.append({"url": resp.url, "status": resp.status,
                                 "ts": datetime.now().isoformat()})
            rules = (self.cfg.api.get("sniff_rules") if self.cfg and self.cfg.api else None) or []
            for rule in rules:
                match = rule.get("match", "")
                if match and match in resp.url:
                    try:
                        setattr(self, rule["name"], await resp.json())
                    except Exception:
                        pass
        except Exception:
            pass

    def api_count_since(self, idx):
        """统计自 idx 之后到当前新增的 API 请求数（前缀从配置读取）。"""
        prefix = (self.cfg.api.get("api_prefix") if self.cfg and self.cfg.api else None) or "/api/"
        return sum(1 for e in self.api_log[idx:] if prefix in e["url"])

    def api_snapshot_len(self):
        return len(self.api_log)

    # ─────────── 页面辅助（通用原语） ───────────
    async def body_text(self):
        try:
            return (await self.page.evaluate("document.body.innerText")).strip()
        except Exception:
            return ""

    async def url(self):
        return self.page.url

    async def click_btn(self, text):
        """按按钮文本点击，role→text 双层降级。"""
        try:
            await self.page.get_by_role("button", name=text).click(timeout=4000)
            return True
        except Exception:
            try:
                await self.page.locator(f"button:has-text('{text}')").first.click(timeout=4000)
                return True
            except Exception:
                return False

    async def screenshot(self, name):
        """截图到 screenshots/ 目录。文件名含序号防同秒覆盖（修 _seq bug）。"""
        self._seq += 1
        ts = datetime.now().strftime("%H%M%S")
        shot_dir = self.cfg.resolve_path("screenshots") if self.cfg else None
        if shot_dir is None:
            from pathlib import Path
            shot_dir = Path("screenshots")
        shot_dir.mkdir(parents=True, exist_ok=True)
        path = shot_dir / f"{name}_{ts}_{self._seq:02d}.png"
        try:
            await self.page.screenshot(path=str(path))
            return str(path)
        except Exception:
            return ""

    @staticmethod
    async def _safe(fn, default=""):
        try:
            return await fn()
        except Exception:
            return default

    # ─────────── 结果登记 ───────────
    def set_result(self, case_id, name, status, actual, detail="", evidence=""):
        self.results[case_id] = Result(case_id, name, status, actual, detail, evidence)
        icons = self.cfg.status_icons() if self.cfg else {}
        icon = icons.get(status, "❓")
        print(f"  {icon} {case_id} {name} — {status}")
        if detail:
            print(f"      {detail}")
        if actual:
            print(f"      实际: {actual[:300]}")


async def run_case_table(runner, cases):
    """表驱动执行一组用例，逐条 try/except 兜底（推广 TC-UIOP3 的异常隔离模式）。

    cases: [(case_id, callable, name), ...]，callable 签名 async (runner)。
    异常时结果归为「无法验证」（区别于真实的「失败」）。
    """
    for cid, fn, name in cases:
        try:
            await fn(runner)
        except Exception as e:
            runner.set_result(cid, name, "无法验证",
                              actual=f"执行异常: {str(e)[:100]}",
                              detail="自动化异常", evidence="")
