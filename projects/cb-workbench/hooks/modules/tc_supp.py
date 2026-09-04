# -*- coding: utf-8 -*-
"""TC-SUPP 模块：补充测试（被冻结/停用账号 + u-X 跨租户隔离）（原 run_TC_SUPP 947-1032 迁移）。"""
from framework.registry import module
from hooks.login import login_as
from hooks.wb import (wb_login, wb_logout, wb_new_task, wb_send,
                      wb_wait_reply, wb_sidebar_text)


@module("TC-SUPP", cases=["TC-B-04", "TC-N-03", "TC-UIOP-17", "TC-ISO-06",
                          "TC-UIOP-15", "TC-ISO-11", "TC-ISO-08", "TC-ISO-09",
                          "TC-ISO-10", "TC-ISO-12", "TC-UIOP-09", "TC-ISO-13",
                          "TC-ISO-16", "TC-UIOP-08", "TC-ISO-17", "TC-ISO-18",
                          "TC-ISO-19", "TC-ISO-20"])
async def run_TC_SUPP(runner):
    # ── TC-B-04 / TC-N-03 被冻结账号(u-F=dj)不可进入 ──
    await runner.goto_login(clear_storage=True)
    await login_as(runner, "u-F", do_save=True, do_enter=False)
    await runner.click_btn("进入工作台")
    await runner.page.wait_for_timeout(2000)
    body = await runner._safe(runner.body_text)
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
    body = await runner._safe(runner.body_text)
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
