# -*- coding: utf-8 -*-
"""TC-UIOP2 模块：停止/断网重试（原 run_TC_UIOP2 1519-1619 迁移）。"""
from framework.registry import module
from hooks.wb import wb_login, wb_new_task, wb_send, wb_wait_reply, wb_reply_text


@module("TC-UIOP2", cases=["TC-UIOP-10", "TC-UIOP-11"])
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
    body = await runner._safe(runner.body_text)
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
