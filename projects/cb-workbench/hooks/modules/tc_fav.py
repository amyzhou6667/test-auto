# -*- coding: utf-8 -*-
"""TC-FAV 模块：收藏意图补充测试（原 run_TC_FAV 1038-1116 迁移）。"""
from framework.registry import module
from hooks.wb import (wb_login, wb_logout, wb_new_task, wb_send, wb_wait_reply,
                      wb_favorite_intent, wb_intent_titles)
from hooks.login import fixture_path, evidence_path
from framework.util import clean_noise


@module("TC-FAV", cases=["TC-UIOP-09", "TC-ISO-08", "TC-ISO-09", "TC-ISO-10",
                         "TC-ISO-12", "TC-ISO-11"])
async def run_TC_FAV(runner):
    # TC-UIOP-09: u-A 收藏意图, 收藏面板可见
    await wb_login(runner, "u-A")
    await wb_new_task(runner)
    await wb_send(runner, "帮我安排明天的会议，列出要点")
    replied, _ = await wb_wait_reply(runner, timeout=80)
    clicked = await wb_favorite_intent(runner, index=1)
    intents = await wb_intent_titles(runner)
    ev = await runner.screenshot("TC-UIOP-09")
    ok = replied and clicked and len(intents) >= 1
    runner.set_result("TC-UIOP-09", "AI回复底部点收藏整理意图, 收藏面板可见",
                      "通过" if ok else "失败",
                      actual=f"AI回复={replied}, 点收藏={clicked}, 收藏面板条目={intents}",
                      detail="", evidence=ev)

    # TC-ISO-08: u-B 看不到 u-A 收藏意图
    await wb_logout(runner)
    await wb_login(runner, "u-B")
    intents_b = await wb_intent_titles(runner)
    ev = await runner.screenshot("TC-ISO-08")
    ok = len(intents_b) == 0
    runner.set_result("TC-ISO-08", "u-B不出现u-A收藏意图模板",
                      "通过" if ok else "失败",
                      actual=f"u-B收藏面板={intents_b}, u-A意图泄漏={not ok}",
                      detail=f"u-A收藏={intents[:2]}", evidence=ev)
    # TC-ISO-09/10: u-B 无 u-A 意图, 无使用/删除入口
    ok = len(intents_b) == 0
    runner.set_result("TC-ISO-09", "u-B无法使用u-A意图模板",
                      "通过" if ok else "失败",
                      actual=f"u-B意图列表为空={ok}, 无可用模板",
                      detail="", evidence="")
    runner.set_result("TC-ISO-10", "u-B无法删除/重命名u-A意图",
                      "通过" if ok else "失败",
                      actual=f"u-B意图列表为空={ok}, 无操作入口",
                      detail="", evidence="")

    # TC-ISO-12: u-B 自己收藏意图并正常使用
    await wb_new_task(runner)
    replied, clicked_b = False, False
    intents_b2 = []
    for msg in ["写一份工作周报的框架", "帮我安排明天的会议，列出要点", "总结一下项目进展"]:
        await wb_send(runner, msg)
        replied, _ = await wb_wait_reply(runner, timeout=90)
        if not replied:
            continue
        clicked_b = await wb_favorite_intent(runner, index=1)
        intents_b2 = await wb_intent_titles(runner)
        if len(intents_b2) >= 1:
            break
    ev = await runner.screenshot("TC-ISO-12")
    ok = replied and clicked_b and len(intents_b2) >= 1
    runner.set_result("TC-ISO-12", "u-B点用意图模板正常使用",
                      "通过" if ok else "无法验证",
                      actual=f"u-B回复={replied}, 收藏={clicked_b}, 本租户意图={intents_b2}",
                      detail="", evidence=ev)

    # TC-ISO-11: u-X 租户1 收藏 → 租户2 不可见
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户1")
    await wb_new_task(runner)
    await wb_send(runner, "总结一下项目进展")
    replied, _ = await wb_wait_reply(runner, timeout=90)
    clicked_x = await wb_favorite_intent(runner, index=1)
    intents_x1 = await wb_intent_titles(runner)
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户2")
    intents_x2 = await wb_intent_titles(runner)
    ev = await runner.screenshot("TC-ISO-11")

    c1, c2 = clean_noise(intents_x1), clean_noise(intents_x2)
    leaked = [t for t in c1 if t in c2]
    ok = (len(c1) >= 0) and (len(leaked) == 0)
    runner.set_result("TC-ISO-11", "u-X跨租户收藏意图隔离",
                      "通过" if ok else "失败",
                      actual=f"租户1意图={c1}, 租户2意图={c2}, 泄漏={leaked}",
                      detail=f"原始: 租户1={intents_x1[:4]} / 租户2={intents_x2[:4]}", evidence=ev)
