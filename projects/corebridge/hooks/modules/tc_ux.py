# -*- coding: utf-8 -*-
"""TC-UX 模块：跨租户隔离交叉验证（原 _clean_ints 1848-1849 与 run_TC_UX 1852-1970 迁移）。"""
from framework.registry import module
from framework.util import clean_noise
from hooks.login import fixture_path, evidence_path
from hooks.wb import (wb_login, wb_logout, wb_new_task, wb_send, wb_wait_session,
                      wb_session_titles, wb_intent_titles, wb_upload_file,
                      wb_open_market, wb_first_session_id, wb_check_deeplink,
                      wb_check_url_access, wb_get_upload_url)


@module("TC-UX", cases=["UX-01", "UX-02", "UX-03", "UX-04", "UX-05", "UX-06"])
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
    i2 = clean_noise(await wb_intent_titles(runner))  # 当前为租户2
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户1")
    i1 = clean_noise(await wb_intent_titles(runner))
    ev = await runner.screenshot("UX-02")
    leaked_i = [t for t in i2 if t in i1]
    ok = len(leaked_i) == 0
    runner.set_result("UX-02", "u-X跨租户收藏意图隔离(两租户意图列表独立)",
                      "通过" if ok else "失败",
                      actual=f"租户2意图={i2}, 租户1意图={i1}, 重叠={leaked_i}",
                      detail="", evidence=ev)

    # ── UX-03 文件隔离(u-X 租户1 上传, 切租户2 不出现) ──
    await wb_new_task(runner)
    up_x1 = await wb_upload_file(runner, fixture_path(runner, "upload-test.txt"))
    await wb_send(runner, "UX租户1上传的文件标记")
    body1 = await runner._safe(runner.body_text)
    file_in_s1 = "upload-test" in body1
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户2")
    await wb_new_task(runner)
    body2 = await runner._safe(runner.body_text)
    file_in_s2 = "upload-test" in body2
    ev = await runner.screenshot("UX-03")
    ok = up_x1 and file_in_s1 and (not file_in_s2)
    runner.set_result("UX-03", "u-X跨租户文件隔离(租户1上传, 租户2会话不出现)",
                      "通过" if ok else "失败",
                      actual=f"租户1上传={up_x1}, 租户1会话含文件={file_in_s1}, 租户2会话含文件={file_in_s2}",
                      detail="", evidence=ev)

    # ── UX-04 资源市场隔离(两租户市场内容不同) ──
    await wb_open_market(runner)
    m2 = await runner._safe(lambda: runner.page.locator(".resource-market").inner_text())
    ev = await runner.screenshot("UX-04")
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户1")
    opened1 = await wb_open_market(runner)
    m1 = await runner._safe(lambda: runner.page.locator(".resource-market").inner_text())
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
    up_x = await wb_upload_file(runner, fixture_path(runner, "upload-test.txt"))
    await runner.page.wait_for_timeout(2000)
    fx_url = await wb_get_upload_url(runner)
    ev = await runner.screenshot("UX-06a")
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-X", tenant="租户1")
    if fx_url:
        status, body = await wb_check_url_access(runner, fx_url, evidence_path(runner, "ux06"))
        file_kw = runner.cfg.api["file_keywords"]
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
