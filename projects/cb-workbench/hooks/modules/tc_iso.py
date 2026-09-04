# -*- coding: utf-8 -*-
"""TC-ISO 模块：数据隔离（原 run_TC_ISO 2224-2363 迁移）。"""
from framework.registry import module
from hooks.wb import (wb_login, wb_logout, wb_new_task, wb_send, wb_wait_reply,
                      wb_sidebar_text, wb_first_session_id, wb_check_deeplink)


@module("TC-ISO", cases=["TC-ISO-01", "TC-ISO-02", "TC-ISO-03", "TC-ISO-05",
                         "TC-ISO-06", "TC-ISO-07", "TC-ISO-08", "TC-ISO-09",
                         "TC-ISO-10", "TC-ISO-11", "TC-ISO-12", "TC-ISO-13",
                         "TC-ISO-14", "TC-ISO-15", "TC-ISO-16", "TC-ISO-17",
                         "TC-ISO-18", "TC-ISO-19", "TC-ISO-20", "TC-ISO-21",
                         "TC-ISO-22", "TC-ISO-23", "TC-ISO-24"])
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
    if "/workbench" not in await runner.url() or "zh1" not in await runner._safe(runner.body_text):
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
