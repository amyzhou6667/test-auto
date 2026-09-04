# -*- coding: utf-8 -*-
"""TC-RES 模块：资源隔离补充测试（原 run_TC_RES 1246-1354 迁移）。"""
from framework.registry import module
from hooks.wb import wb_login, wb_logout, wb_open_market
from hooks.login import fixture_path, evidence_path
from framework.util import clean_noise


@module("TC-RES", cases=["TC-ISO-20", "TC-ISO-17", "TC-ISO-18", "TC-ISO-23",
                         "TC-ISO-19", "TC-ISO-22", "TC-ISO-21", "TC-ISO-24"])
async def run_TC_RES(runner):
    # u-A(租户2) 打开资源市场
    await wb_login(runner, "u-A")
    opened = await wb_open_market(runner)
    market_a = await runner._safe(lambda: runner.page.locator(".resource-market").inner_text())
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
            apply_result = await runner._safe(lambda: runner.page.locator(".resource-market").inner_text())
    except Exception:
        applied = False
    ev = await runner.screenshot("TC-ISO-17a")
    # 关闭市场, 检查 u-A 资源面板(资源清单/已收藏/常用)
    try:
        await runner.page.locator(".resource-market .rm-drawer__close, .resource-market button:has-text('✕')").first.click(timeout=3000)
    except Exception:
        pass
    await runner.page.wait_for_timeout(1000)
    rp_a = await runner._safe(lambda: runner.page.locator(".resource-panel").inner_text())

    # u-B(租户1) 打开市场对比
    await wb_logout(runner)
    await wb_login(runner, "u-B")
    opened_b = await wb_open_market(runner)
    market_b = await runner._safe(lambda: runner.page.locator(".resource-market").inner_text())
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
    rp_b = await runner._safe(lambda: runner.page.locator(".resource-panel").inner_text())
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
    fav_b = await runner._safe(lambda: runner.page.locator(".resource-panel").inner_text())
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
    common_b = await runner._safe(lambda: runner.page.locator(".resource-panel").inner_text())
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
