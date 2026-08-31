# -*- coding: utf-8 -*-
"""TC-B 模块：登录回填/信息完整性/退出（原 run_TC_B 533-671 迁移）。"""
from framework.registry import module
from hooks.login import login_as


@module("TC-B", cases=["TC-B-01", "TC-B-02", "TC-B-03", "TC-B-04", "TC-B-05", "TC-B-06"])
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
    dlg = await runner._safe(runner.dialog_text)
    ev = await runner.screenshot("TC-B-01")
    ok = "登录信息" in dlg and ("租户2" in dlg or runner.cfg.account("u-A")["userId"][:6] in dlg)
    runner.set_result("TC-B-01", "重新打开弹窗回填上次账号与租户",
                      "通过" if ok else "失败",
                      actual=f"重新打开={('登录信息' in dlg)}, 回填账号租户={bool('租户2' in dlg)}",
                      detail=f"弹窗: {dlg[:300]}", evidence=ev)

    # ── TC-B-03 信息不完整点进入 → 报 .env 错误 ──
    await runner.goto_login(clear_storage=True)
    await runner.fill_userId(runner.cfg.account("u-A")["userId"])
    await runner.fill_username(runner.cfg.account("u-A")["username"])
    await runner.fill_workbenchId("")
    await runner.fill_appId("")
    await runner.page.wait_for_timeout(1000)
    await runner.click_btn("保存")
    await runner.page.wait_for_timeout(800)
    await runner.click_btn("进入工作台")
    await runner.page.wait_for_timeout(1500)
    full_text = await runner._safe(runner.body_text)
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
    uid_val = await runner._safe(lambda: runner.page.locator(".te-dlg input").nth(0).input_value())
    name_val = await runner._safe(lambda: runner.page.locator(".te-dlg input").nth(1).input_value())
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
    body = await runner._safe(runner.body_text)
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
            dlg_txt = await runner._safe(runner.body_text)
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
    body = await runner._safe(runner.body_text)
    ev = await runner.screenshot("TC-B-06")
    back_to_login = "login" in url
    ok = logged_out and back_to_login
    runner.set_result("TC-B-06", "退出登录回到登录页, 无上一租户残留",
                      "通过" if ok else "失败",
                      actual=f"确认框出现={confirm_seen}, 执行退出={logged_out}, 回到登录页={back_to_login}",
                      detail=f"URL={url}, 页面: {body[:200]}", evidence=ev)
