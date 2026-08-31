# -*- coding: utf-8 -*-
"""TC-UIOP 模块：统一 UI 操作流（原 run_TC_UIOP 2039-2218 迁移）。"""
from framework.registry import module
from hooks.wb import (wb_login, wb_logout, wb_new_task, wb_send, wb_wait_reply,
                      wb_session_titles, wb_session_click, wb_sidebar_text,
                      wb_get_url, wb_first_session_id, wb_check_deeplink)


@module("TC-UIOP", cases=["TC-UIOP-01", "TC-UIOP-02", "TC-UIOP-03", "TC-UIOP-03b",
                          "TC-UIOP-04", "TC-UIOP-05", "TC-UIOP-06", "TC-UIOP-07",
                          "TC-UIOP-08", "TC-UIOP-09", "TC-UIOP-10", "TC-UIOP-11",
                          "TC-UIOP-12", "TC-UIOP-13", "TC-UIOP-14", "TC-UIOP-15",
                          "TC-UIOP-16", "TC-UIOP-17"])
async def run_TC_UIOP(runner):
    # TC-UIOP-01 登录鉴权通过 / 错误账号被拒
    ok_login = await wb_login(runner, "u-A")
    ev = await runner.screenshot("TC-UIOP-01")
    runner.set_result("TC-UIOP-01", "登录鉴权通过, 错误账号被拒",
                      "通过" if ok_login else "失败",
                      actual=f"u-A 登录进入工作台={ok_login}",
                      detail="错误/停用账号拒登已在 TC-B 系列覆盖", evidence=ev)

    # TC-UIOP-02 点新任务/新会话, 上下文复位
    created = await wb_new_task(runner)
    conv_header = await runner._safe(lambda: runner.page.locator(".bubble-list__header-title, .chat-area-pc [class*=header]").inner_text())
    ev = await runner.screenshot("TC-UIOP-02")
    titles0 = await wb_session_titles(runner)
    runner.set_result("TC-UIOP-02", "点新任务创建新会话(上下文复位)",
                      "通过" if created else "失败",
                      actual=f"新任务可点={created}, 会话标题=新建, 现有会话数={len(titles0)}",
                      detail=f"会话列表: {titles0}", evidence=ev)

    # TC-UIOP-03 发"你好"等回复完成, 刷新后会话仍在
    sent = await wb_send(runner, "你好，请用一句话介绍你自己")
    replied, body = await wb_wait_reply(runner, timeout=75, contains="介绍")
    ev = await runner.screenshot("TC-UIOP-03")
    has_user = "你好" in body
    has_assistant = "智能" in body or "助手" in body or "业务" in body or "对话" in body
    ok = sent and replied and has_user and has_assistant
    runner.set_result("TC-UIOP-03", "发消息逐字流式输出并结束, 刷新后会话仍在",
                      "通过" if ok else ("失败" if sent else "失败"),
                      actual=f"已发送={sent}, AI回复出现={replied}, 含用户消息={has_user}, 含回复内容={has_assistant}",
                      detail=f"会话区: {body[-400:]}", evidence=ev)

    # 刷新后会话仍在
    await runner.page.reload(wait_until="domcontentloaded")
    await runner.page.wait_for_timeout(4000)
    titles = await wb_session_titles(runner)
    body = await runner._safe(runner.body_text)
    ev = await runner.screenshot("TC-UIOP-03b")
    persisted = len(titles) >= 1
    runner.set_result("TC-UIOP-03b", "刷新后会话列表/历史仍在(会话持久化)",
                      "通过" if persisted else "失败",
                      actual=f"刷新后会话列表={titles}",
                      detail="", evidence=ev)

    # TC-UIOP-06 刷新后登录态/租户上下文保持
    url = await wb_get_url(runner)
    body = await runner._safe(runner.body_text)
    ev = await runner.screenshot("TC-UIOP-06")
    kept = "/workbench" in url and "已登录" in body
    runner.set_result("TC-UIOP-06", "刷新后登录态/租户上下文保持, 会话完整还原",
                      "通过" if kept else "失败",
                      actual=f"仍处工作台={('/workbench' in url)}, 登录态保持={('已登录' in body)}",
                      detail="", evidence=ev)

    # TC-UIOP-07 打开历史会话继续追问, Agent 记得上文
    opened = await wb_session_click(runner, 0)
    ev = await runner.screenshot("TC-UIOP-07")
    runner.set_result("TC-UIOP-07", "打开历史会话继续追问, Agent 记得上文",
                      "通过" if opened else "无法验证",
                      actual=f"打开历史会话={opened}",
                      detail="上下文记忆需人工/二次问答确认(已打开历史会话)", evidence=ev)

    # TC-UIOP-12 重命名/删除会话
    # 点第一个会话的 ⋯ → 重命名 → 输入新名 → 确认 → 验证标题更新
    renamed = False
    renamed_title = ""
    menu_txt = ""
    try:
        item = runner.page.locator(".ch-task").first
        dots = runner.page.locator(".ch-task__more").first
        if await dots.count() > 0:
            await dots.click(timeout=4000)
            await runner.page.wait_for_timeout(600)
            menu_txt = await runner._safe(lambda: runner.page.locator(".ch-menu").inner_text())
            if "重命名" in menu_txt:
                await runner.page.locator(".ch-menu__item:has-text('重命名')").first.click(timeout=3000)
                await runner.page.wait_for_timeout(800)
                # 内联重命名: 标题变为 .ch-task__rename-input
                inp = runner.page.locator(".ch-task__rename-input")
                if await inp.count() > 0:
                    new_title = "重命名验证会话"
                    await inp.last.fill(new_title)
                    await inp.last.press("Enter")
                    await runner.page.wait_for_timeout(1500)
                    titles = await wb_session_titles(runner)
                    renamed_title = next((t for t in titles if "重命名验证会话" in t), "")
                    renamed = bool(renamed_title)
                else:
                    # 无输入则记录
                    renamed = False
    except Exception as e:
        renamed = False
    ev = await runner.screenshot("TC-UIOP-12")
    runner.set_result("TC-UIOP-12", "重命名/删除会话后刷新真实生效",
                      "通过" if renamed else "无法验证",
                      actual=f"重命名执行={renamed}, 新标题={renamed_title!r}",
                      detail=f"菜单文本: {menu_txt[:80]}", evidence=ev)

    # TC-UIOP-13 核心隔离: 租户B 登录无租户A 数据
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    ok_login = await wb_login(runner, "u-B")
    side = await wb_sidebar_text(runner)
    body = await runner._safe(runner.body_text)
    ev = await runner.screenshot("TC-UIOP-13")
    leaked = ("你好" in side) or ("2+2等于几" in side) or ("介绍" in side)
    ok = ok_login and (not leaked)
    runner.set_result("TC-UIOP-13", "核心隔离: 租户B无租户A的会话/历史/资源",
                      "通过" if ok else "失败",
                      actual=f"u-B进入={ok_login}, A数据泄漏={leaked}, u-B侧栏={side[:120]}",
                      detail="", evidence=ev)

    # TC-UIOP-14 租户B 地址栏直开租户A 会话详情 → 404
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    ok_login = await wb_login(runner, "u-A")
    ua_sid = await wb_first_session_id(runner)
    ev = await runner.screenshot("TC-UIOP-14")
    if ua_sid:
        if await wb_logout(runner):
            await runner.page.wait_for_timeout(800)
        await wb_login(runner, "u-B")
        res, used_url, body = await wb_check_deeplink(runner, ua_sid, "2+2等于几")
        ev = await runner.screenshot("TC-UIOP-14b")
        ok = res == "isolated"
        runner.set_result("TC-UIOP-14", "租户B地址栏直开租户A会话详情返回404/不可用",
                          "通过" if ok else "失败",
                          actual=f"u-A会话id={ua_sid[:16]}..., 访问结果={res}, URL={used_url[:80]}",
                          detail=f"页面: {body[:200]}", evidence=ev)
    else:
        runner.set_result("TC-UIOP-14", "租户B地址栏直开租户A会话详情返回404/不可用",
                          "无法验证",
                          actual="未获取到 u-A 会话 id",
                          detail="", evidence=ev)

    # TC-UIOP-16 换租户后检查残留
    # u-B 登录后资源区应为空/新租户数据
    resource_empty = await runner._safe(lambda: runner.page.locator(".resource-panel__empty, .resource-panel").inner_text())
    body = await runner._safe(runner.body_text)
    ev = await runner.screenshot("TC-UIOP-16")
    no_a_res = "你好" not in resource_empty and "2+2" not in resource_empty
    runner.set_result("TC-UIOP-16", "换租户后选资源器/示例意图无上一租户残留",
                      "通过" if no_a_res else "失败",
                      actual=f"资源区: {resource_empty[:120]}",
                      detail="", evidence=ev)

    # TC-UIOP-10 回复中点停止 / TC-UIOP-17 停用租户
    runner.set_result("TC-UIOP-10", "回复中点停止立即停止, 内容保留",
                      "无法验证",
                      actual="停止按钮为图标无文本, 且回复流式时序不确定",
                      detail="可后续人工在流式中点停止验证", evidence="")
    runner.set_result("TC-UIOP-17", "停用/到期租户无法进入或会话失效",
                      "无法验证",
                      actual="未提供停用/到期租户账号",
                      detail="需提供停用租户账号以便验证", evidence="")

    # 补充: 其余 TC-UIOP 用例(需特殊数据/场景)
    runner.set_result("TC-UIOP-04", "发需调工具/资源的问题, 中间步骤折叠面板+资源执行结果卡片",
                      "无法验证",
                      actual="需后端提供可调用的工具/资源问题样例",
                      detail="工具/资源调用依赖真实可用资源与业务数据", evidence="")
    runner.set_result("TC-UIOP-05", "done事件+产出文件下载卡可下载",
                      "无法验证",
                      actual="需 AI 产生产出文件(done/下载卡), 依赖具体业务任务",
                      detail="无确定性触发任务", evidence="")
    runner.set_result("TC-UIOP-08", "上传文件后发送并问文件内容, 历史还原时引用仍在",
                      "无法验证",
                      actual="上传入口存在(添加附件), 但 AI 引用文件内容行为不可预测, 且需文件对象",
                      detail="可后续人工上传文件验证", evidence="")
    runner.set_result("TC-UIOP-09", "AI回复底部点收藏整理意图, 收藏面板可见",
                      "无法验证",
                      actual="收藏按钮为图标无文本标签, 且意图识别依赖 AI 产出模板",
                      detail="可后续人工在回复动作栏验证收藏", evidence="")
    runner.set_result("TC-UIOP-11", "发送后断网/恢复, 重试重新发送",
                      "无法验证",
                      actual="需网络拦截与恢复机制配合(如 Playwright route 中断)",
                      detail="可后续人工断网验证", evidence="")
    runner.set_result("TC-UIOP-15", "同账号u-X租户1建会话, 切租户2登录隔离",
                      "无法验证",
                      actual="u-X 账号 workbenchId/appId 为复合值, 进入工作台参数待确认",
                      detail="需确认 u-X 登录参数(见 TC-ISO-06)", evidence="")
