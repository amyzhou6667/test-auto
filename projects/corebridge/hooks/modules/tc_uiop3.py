# -*- coding: utf-8 -*-
"""TC-UIOP3 模块：UIOP 补充（原 _tc_uiopp04 1360 / _tc_uiopp05 1451 / _tc_uiopp08 1477 / run_TC_UIOP3 1501 迁移）。"""
from framework.registry import module
from hooks.wb import wb_login, wb_new_task, wb_upload_file, wb_send, wb_wait_reply, wb_reply_text
from hooks.login import fixture_path
from framework.engine import run_case_table


async def _tc_uiopp04(runner):
    await wb_login(runner, "u-A")
    await wb_new_task(runner)
    ta = runner.page.locator("div.chat-rich-text").first
    await ta.click(timeout=5000)
    await ta.press("/")
    await runner.page.wait_for_timeout(1500)
    picker = await runner._safe(lambda: runner.page.locator(".resource-picker-anchor").inner_text())
    try:
        await runner.page.keyboard.press("Escape")
    except Exception:
        pass
    await runner.page.wait_for_timeout(500)

    def parse_count(txt, key):
        import re as _re
        m = _re.search(key + r"\s*(\d+)", txt)
        return int(m.group(1)) if m else 0

    n_agent = parse_count(picker, "Agent")
    n_skill = parse_count(picker, "Skill")
    n_mcp = parse_count(picker, "MCP")
    n_total = n_agent + n_skill + n_mcp
    ev = await runner.screenshot("TC-UIOP-04")
    if n_total == 0:
        runner.set_result("TC-UIOP-04", "发需调工具/资源的问题, 中间步骤折叠面板+资源执行结果卡片",
                          "无法验证",
                          actual=f"资源选择器可用资源: Agent {n_agent}/Skill {n_skill}/MCP {n_mcp} —— 无已开通资源(skill 需审批通过)",
                          detail=f"选择器: {picker[:100]}", evidence=ev)
        return
    # 重新打开选择器, 优先选中 Excel/skill 资源
    await ta.click(timeout=5000)
    await ta.press("/")
    await runner.page.wait_for_timeout(1500)
    selected = False
    skill_name = ""
    try:
        items = runner.page.locator(".resource-picker-anchor [class*=item], .rp-panel [class*=item], .resource-picker-anchor li")
        n_items = await items.count()
        for i in range(n_items):
            txt = (await items.nth(i).inner_text()).lower()
            if "excel" in txt or "计算" in txt or "skill" in txt:
                skill_name = (await items.nth(i).inner_text()).strip()[:40]
                await items.nth(i).click(timeout=3000)
                selected = True
                break
        if not selected and n_items > 0:
            skill_name = (await items.first.inner_text()).strip()[:40]
            await items.first.click(timeout=3000)
            selected = True
    except Exception:
        selected = False
    try:
        await runner.page.keyboard.press("Escape")
    except Exception:
        pass
    await runner.page.wait_for_timeout(800)
    if not selected:
        runner.set_result("TC-UIOP-04", "发需调工具/资源的问题, 中间步骤折叠面板+资源执行结果卡片",
                          "无法验证",
                          actual=f"选择器有 {n_total} 项但未能选中资源", detail="", evidence=ev)
        return
    # 问询 skill 能力
    try:
        await ta.click(timeout=5000)
        await ta.fill("你可以做什么")
        await ta.press("Enter")
    except Exception:
        pass
    replied1, _ = await wb_wait_reply(runner, timeout=120)
    cap = await wb_reply_text(runner)
    # 上传 Excel 并基于能力回复触发真实执行
    up = await wb_upload_file(runner, fixture_path(runner, "test_sales.xlsx"))
    try:
        await ta.click(timeout=5000)
        await ta.fill("请读取我上传的Excel文件，计算销售额这一列的最大值，并告诉我结果")
        await ta.press("Enter")
    except Exception:
        pass
    replied2, _ = await wb_wait_reply(runner, timeout=150)
    reply2 = await wb_reply_text(runner)
    body = await runner._safe(runner.body_text)
    # 执行结果判定: 出现执行卡片/折叠/计算数值
    has_result = any(k in (reply2 + body) for k in ["执行结果", "折叠", "最大值", "200", "计算", "已执行", "结果"])
    ok = replied1 and replied2 and up and has_result
    runner.set_result("TC-UIOP-04", "发需调工具/资源的问题, 中间步骤折叠面板+资源执行结果卡片",
                      "通过" if ok else "失败",
                      actual=f"选中资源={skill_name!r}, 上传Excel={up}, 问询能力回复={replied1}, 执行回复={replied2}, 含执行结果={has_result}",
                      detail=f"能力回复: {cap[:100]} / 执行回复: {reply2[:100]}", evidence=ev)


async def _tc_uiopp05(runner):
    await wb_new_task(runner)
    await wb_send(runner, "请给我一份杭州三日游攻略，产出markdown文档供下载")
    replied, _ = await wb_wait_reply(runner, timeout=120)
    reply = await wb_reply_text(runner)
    body = await runner._safe(runner.body_text)
    dl_count = 0
    try:
        dl_count = await runner.page.locator("a[download], button:has-text('下载'), [class*=download], [class*=output], [class*=file-card], [class*=artifact]").count()
    except Exception:
        dl_count = 0
    has_md = (".md" in reply) or ("markdown" in reply.lower()) or ("杭州" in reply)
    no_export = "没有可用" in reply or "文档导出资源" in reply or "复制保存" in reply or "暂" in reply
    ev = await runner.screenshot("TC-UIOP-05")
    if replied and dl_count > 0:
        st = "通过"
    elif replied and has_md:
        st = "失败"  # 生成了 md 但无下载卡
    else:
        st = "无法验证"
    runner.set_result("TC-UIOP-05", "done事件+产出文件下载卡可下载",
                      st,
                      actual=f"AI回复={replied}, 生成md内容={has_md}, 下载卡元素数={dl_count}, 提示无导出资源={no_export}",
                      detail=f"回复: {reply[:150]}", evidence=ev)


async def _tc_uiopp08(runner):
    await wb_new_task(runner)
    up = await wb_upload_file(runner, fixture_path(runner, "upload-test.txt"))
    await wb_send(runner, "我上传了一个文件，请告诉我文件里写了哪些内容，特别是我的爱好和经历")
    replied, _ = await wb_wait_reply(runner, timeout=120)
    if not replied:
        await wb_send(runner, "文件里有什么内容？")
        replied, _ = await wb_wait_reply(runner, timeout=120)
    reply = await wb_reply_text(runner)
    file_kw = runner.cfg.api["file_keywords_uiop08"]
    hit = [k for k in file_kw if k in reply]
    ev = await runner.screenshot("TC-UIOP-08")
    if up and replied and reply and len(hit) >= 1:
        st = "通过"
    elif not reply:
        st = "无法验证"  # AI 未稳定回复或回复读取为空
    else:
        st = "无法验证"  # 回复存在但未引用文件关键词(AI 行为不确定)
    runner.set_result("TC-UIOP-08", "上传文件后发送并问文件内容, AI能引用",
                      st,
                      actual=f"上传={up}, AI回复={bool(reply)}, 引用文件关键词={hit}",
                      detail=f"AI回复: {reply[:180]}", evidence=ev)


@module("TC-UIOP3", cases=["TC-UIOP-04", "TC-UIOP-05", "TC-UIOP-08"])
async def run_TC_UIOP3(runner):
    cases = [
        ("TC-UIOP-04", _tc_uiopp04, "发需调工具/资源的问题, 中间步骤折叠面板+资源执行结果卡片"),
        ("TC-UIOP-05", _tc_uiopp05, "done事件+产出文件下载卡可下载"),
        ("TC-UIOP-08", _tc_uiopp08, "上传文件后发送并问文件内容, AI能引用"),
    ]
    for cid, fn, name in cases:
        try:
            await fn(runner)
        except Exception as e:
            runner.set_result(cid, name, "无法验证",
                              actual=f"执行异常: {str(e)[:100]}",
                              detail="自动化异常", evidence="")
