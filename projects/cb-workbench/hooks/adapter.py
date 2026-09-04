# -*- coding: utf-8 -*-
"""CoreBridgeRunner(Runner) 子类：承载 CoreBridge 专属页面 DOM 方法。

引擎基座 Runner 只含通用原语；登录弹窗/租户下拉/表单填充等专属逻辑全在这里，
15 个 run_TC_* 模块函数的 `runner.dialog_*` 调用点零改动 —— 这是 1:1 迁移的胜负手。
数据源从全局常量（BASE_URL / ACCOUNTS / 硬编码选择器）改为读 self.cfg。
"""
from framework.engine import Runner


class CoreBridgeRunner(Runner):
    # ─────────── 登录弹窗（CoreBridge 专属）───────────
    def dialog_sel(self):
        return (self.cfg.selectors or {}).get("dialog", ".te-dlg")

    async def goto_login(self, clear_storage=False):
        base_url = self.cfg.base_url
        if clear_storage:
            await self.page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.evaluate("localStorage.clear(); sessionStorage.clear();")
        await self.page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
        try:
            await self.page.locator(self.dialog_sel()).first.wait_for(state="visible", timeout=5000)
        except Exception:
            pass
        await self.page.wait_for_timeout(800)

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
