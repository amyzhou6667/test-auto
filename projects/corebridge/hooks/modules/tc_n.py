# -*- coding: utf-8 -*-
"""TC-N 模块：数据隔离与权限（原 run_TC_N 2002-2033 迁移）。"""
from framework.registry import module
from hooks.wb import wb_login, wb_logout, wb_sidebar_text


@module("TC-N", cases=["TC-N-01", "TC-N-02", "TC-N-03"])
async def run_TC_N(runner):
    # TC-N-01 登录后租户上下文正确
    ok_login = await wb_login(runner, "u-A")
    body = await runner._safe(runner.body_text)
    ev = await runner.screenshot("TC-N-01")
    ctx_ok = "已登录" in body and runner.cfg.account("u-A")["username"] in body
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
    body = await runner._safe(runner.body_text)
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
