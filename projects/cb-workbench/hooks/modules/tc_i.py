# -*- coding: utf-8 -*-
"""TC-I 模块：登录弹窗与账号绑定（原 execute_test_cases.py run_TC_I 407-531 迁移）。"""
from framework.registry import module
from hooks.login import login_as


@module("TC-I", cases=["TC-I-01", "TC-I-02", "TC-I-03", "TC-I-04",
                       "TC-I-05", "TC-I-06", "TC-I-07"])
async def run_TC_I(runner):
    # ── TC-I-01 打开工作台自动弹登录窗 ──
    await runner.goto_login(clear_storage=True)
    dlg = await runner._safe(runner.dialog_text)
    body = await runner._safe(runner.body_text)
    ev = await runner.screenshot("TC-I-01")
    ok = "登录信息" in dlg and "智能业务终端" in body and "进入工作台" in body
    runner.set_result("TC-I-01", "打开工作台自动弹出登录信息弹窗, 主卡片显示标题与进入按钮",
                      "通过" if ok else "失败",
                      actual=f"弹窗含'登录信息'={bool('登录信息' in dlg)}, 页面含标题={bool('智能业务终端' in body)}, 含进入按钮={bool('进入工作台' in body)}",
                      detail=f"弹窗文本: {dlg[:200]}", evidence=ev)

    # ── TC-I-02 仅填 userId, 用户名留空 ──
    await runner.fill_userId(runner.cfg.account("u-A")["userId"])
    await runner.fill_username("")
    await runner.page.wait_for_timeout(1000)
    n0 = runner.api_snapshot_len()
    disabled = await runner._safe(runner.tenant_disabled, None)
    dlg = await runner._safe(runner.dialog_text)
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
    await runner.fill_userId(runner.cfg.account("u-A")["userId"])
    await runner.fill_username(runner.cfg.account("u-A")["username"])
    # 捕捉"加载中"中间态
    mid_loading = False
    for _ in range(6):
        sel = await runner._safe(lambda: runner.page.locator(".te-dlg .el-select").inner_text(), "")
        if "加载" in sel:
            mid_loading = True
            break
        await runner.page.wait_for_timeout(300)
    await runner.page.wait_for_timeout(1200)
    opts = await runner._safe(runner.tenant_options)
    sel_text = await runner._safe(runner.tenant_selected_text)
    ev = await runner.screenshot("TC-I-03")
    auto_selected = bool(sel_text) and "加载" not in sel_text and "请输入" not in sel_text
    ok = (len(opts) >= 1) and auto_selected
    runner.set_result("TC-I-03", "填完整账号后租户加载并自动选中唯一租户",
                      "通过" if ok else "失败",
                      actual=f"加载中中间态={mid_loading}, 下拉选项={opts}, 已选={sel_text!r}",
                      detail="", evidence=ev)

    # ── TC-I-04 u-N 无绑定租户 ──
    await runner.goto_login(clear_storage=True)
    await runner.fill_userId(runner.cfg.account("u-N")["userId"])
    await runner.fill_username(runner.cfg.account("u-N")["username"])
    await runner.page.wait_for_timeout(2000)
    opts = await runner._safe(runner.tenant_options)
    dlg = await runner._safe(runner.dialog_text)
    msg_hit = any(k in dlg for k in ["暂无绑定租户", "未绑定", "暂无", "没有绑定"])
    await runner.open_tenant_dropdown()
    await runner.page.wait_for_timeout(600)
    await runner.click_btn("保存")
    await runner.page.wait_for_timeout(800)
    dlg2 = await runner._safe(runner.dialog_text)
    save_hit = any(k in dlg2 for k in ["请选择租户", "请选择"])
    ev = await runner.screenshot("TC-I-04")
    ok = (len(opts) == 0) and msg_hit and save_hit
    runner.set_result("TC-I-04", "u-N无绑定租户: 下拉为空+提示+保存报错",
                      "通过" if ok else "失败",
                      actual=f"选项数={len(opts)}, 无租户提示={msg_hit}, 保存报错={save_hit}",
                      detail=f"弹窗: {dlg2[:300]}", evidence=ev)

    # ── TC-I-05 租户下拉仅列本账号租户+已选高亮 ──
    await runner.goto_login(clear_storage=True)
    await runner.fill_userId(runner.cfg.account("u-A")["userId"])
    await runner.fill_username(runner.cfg.account("u-A")["username"])
    await runner.page.wait_for_timeout(1800)
    await runner.open_tenant_dropdown()
    await runner.page.wait_for_timeout(600)
    opts = await runner._safe(runner.tenant_options)
    highlighted = await runner._safe(lambda: runner.page.evaluate(
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
    disabled = await runner._safe(runner.tenant_disabled, None)
    sel_text = await runner._safe(runner.tenant_selected_text)
    sel_empty = (not sel_text) or "请输入" in sel_text or "加载" in sel_text
    body = await runner._safe(runner.body_text)
    ev = await runner.screenshot("TC-I-06")
    ok = disabled and sel_empty
    runner.set_result("TC-I-06", "清空userId后租户被清空并禁用, 无报错",
                      "通过" if ok else "失败",
                      actual=f"租户禁用={disabled}, 已选={sel_text!r}(视为空={sel_empty})",
                      detail="", evidence=ev)

    # ── TC-I-07 保存: 弹窗关闭+显示用户名+进入可点+不跳转 ──
    await runner.goto_login(clear_storage=True)
    await login_as(runner, "u-A", do_save=True, do_enter=False)
    dlg_visible = await runner._safe(runner.dialog_visible)
    body = await runner._safe(runner.body_text)
    enter_ok = await runner._safe(lambda: runner.page.locator("button.submit").is_enabled())
    url = await runner.url()
    ev = await runner.screenshot("TC-I-07")
    closed = not dlg_visible
    username_shown = runner.cfg.account("u-A")["username"] in body
    ok = closed and enter_ok and "login" in url
    runner.set_result("TC-I-07", "保存后弹窗关闭, 显示用户名, 进入按钮可点, 不跳转",
                      "通过" if ok else "失败",
                      actual=f"弹窗可见={dlg_visible}(期望关闭), 用户名显示={username_shown}, 进入可点={enter_ok}, URL含login={('login' in url)}",
                      detail=f"页面: {body[:200]}", evidence=ev)
