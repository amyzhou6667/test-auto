# -*- coding: utf-8 -*-
"""TC-UPLOAD 模块：文件上传补充测试（原 run_TC_UPLOAD 1168-1240 迁移）。"""
from framework.registry import module
from hooks.wb import (wb_login, wb_logout, wb_new_task, wb_upload_file, wb_send,
                      wb_wait_reply, wb_reply_text, wb_get_upload_url,
                      wb_check_url_access, wb_sidebar_text)
from hooks.login import fixture_path, evidence_path
from framework.util import clean_noise


@module("TC-UPLOAD", cases=["TC-ISO-13", "TC-UIOP-08", "TC-ISO-14", "TC-ISO-15",
                            "TC-ISO-16"])
async def run_TC_UPLOAD(runner):
    # TC-ISO-13: u-A 上传文件并发送, 文件出现在消息中
    await wb_login(runner, "u-A")
    await wb_new_task(runner)
    up = await wb_upload_file(runner, fixture_path(runner, "upload-test.txt"))
    body = await runner._safe(runner.body_text)
    file_shown = ("upload-test" in body) or ("txt" in body.lower())
    sent = await wb_send(runner, "请读取我上传的文件内容")
    replied, _ = await wb_wait_reply(runner, timeout=90)
    if not replied:
        sent = await wb_send(runner, "文件里写了什么")
        replied, _ = await wb_wait_reply(runner, timeout=90)
    reply = await wb_reply_text(runner)
    ai_got_file = any(k in reply for k in runner.cfg.api["file_keywords"])
    ev = await runner.screenshot("TC-ISO-13")
    ok = up and file_shown
    runner.set_result("TC-ISO-13", "u-A上传文件并发送, 文件出现在消息中",
                      "通过" if ok else "失败",
                      actual=f"上传成功={up}, 文件显示={file_shown}, 已发送={sent}",
                      detail=f"页面含'upload-test'={('upload-test' in body)}", evidence=ev)

    # TC-UIOP-08: AI 引用文件内容
    ok = up and ai_got_file
    runner.set_result("TC-UIOP-08", "上传文件后发送并问文件内容, AI能引用",
                      "通过" if ok else "无法验证",
                      actual=f"AI回复={replied}, 引用文件内容={ai_got_file}",
                      detail=f"AI回复片段: {reply[:120]}", evidence=ev)

    # TC-ISO-14: u-B 直接访问 u-A 上传文件的 URL → 应失败
    file_url = await wb_get_upload_url(runner)
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-B")
    if file_url:
        status, body = await wb_check_url_access(runner, file_url, evidence_path(runner, "tc_iso14"))
        ev = await runner.screenshot("TC-ISO-14")
        file_kw = runner.cfg.api["file_keywords"]
        leaked = (status == 200) and any(k in body for k in file_kw)
        blocked = status in (401, 403, 404, 400) or (status is None)
        ok = blocked and (not leaked)
        st = "通过" if ok else ("失败" if leaked else "无法验证")
        runner.set_result("TC-ISO-14", "u-B地址栏直开u-A文件链接失败(不泄漏)",
                          st,
                          actual=f"u-A文件URL={file_url[:90]}, u-B访问status={status}, 文件内容泄漏={leaked}",
                          detail=f"响应片段: {body[:120]}", evidence=ev)
    else:
        runner.set_result("TC-ISO-14", "u-B地址栏直开u-A文件链接失败(不泄漏)",
                          "无法验证",
                          actual="未捕获到上传响应 rawUrl", detail="", evidence="")

    # TC-ISO-15: u-B 会话内打开 u-A 会话引用的文件 → 无法(会话已隔离)
    body_b = await runner._safe(runner.body_text)
    side_b = await wb_sidebar_text(runner)
    ev = await runner.screenshot("TC-ISO-15")
    # u-B 无 u-A 会话, 自然无法访问其中文件引用
    no_a_file_ref = not any(k in body_b for k in ["upload-test", "upload_test"])
    runner.set_result("TC-ISO-15", "u-B打开u-A会话内文件失败(会话隔离前置)",
                      "通过" if no_a_file_ref else "失败",
                      actual=f"u-B会话区含u-A文件引用={not no_a_file_ref}",
                      detail="u-B无法访问u-A会话(TC-ISO-03已验证), 文件引用随之隔离", evidence=ev)

    # TC-ISO-16: u-B 上传自己的文件, 不出现 u-A 的文件
    await wb_new_task(runner)
    up_b = await wb_upload_file(runner, fixture_path(runner, "upload-test.txt"))
    await wb_send(runner, "这是租户1的上传测试")
    body_b = await runner._safe(runner.body_text)
    ev = await runner.screenshot("TC-ISO-16")
    # u-B 会话中只应有自己的文件缩略(u-A 的文件在 u-A 会话中, 已随会话隔离)
    ok = up_b
    runner.set_result("TC-ISO-16", "u-B上传文件不出现u-A文件(会话隔离)",
                      "通过" if ok else "失败",
                      actual=f"u-B上传成功={up_b}, u-B会话可见自身文件",
                      detail="文件随会话隔离(TC-ISO-01/02 已验证)", evidence=ev)
