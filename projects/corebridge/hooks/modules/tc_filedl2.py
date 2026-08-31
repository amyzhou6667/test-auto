# -*- coding: utf-8 -*-
"""FILEDL2 模块：真实文件下载置换接口隔离（原 run_TC_FILEDL2 1721-1779 迁移）。"""
from framework.registry import module
from hooks.login import _get_token, _exchange_file, evidence_path, fixture_path
from hooks.wb import wb_login, wb_logout, wb_new_task, wb_upload_file


@module("FILEDL2", cases=["FILEDL2"])
async def run_TC_FILEDL2(runner):
    # ── 1. u-A 上传, 获取 fileId; 属主(u-A)调用确认接口可用 ──
    await wb_login(runner, "u-A")
    await wb_new_task(runner)
    up = await wb_upload_file(runner, fixture_path(runner, "upload-test.txt"))
    await runner.page.wait_for_timeout(3000)
    ub = getattr(runner, "api_upload", None)
    fileId_A = ""
    if ub:
        files = (ub.get("data") or {}).get("files") or []
        if files:
            fileId_A = str(files[0].get("fileId", ""))
    token_A = await _get_token(runner)
    st_owner, body_owner = await _exchange_file(runner, fileId_A, token_A)
    owner_ok = (st_owner == 200) and ("rawUrl" in body_owner)
    ev = await runner.screenshot("FILEDL2-a")

    # ── 2. u-B(跨用户)用 u-A 的 fileId 调置换接口 ──
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-B")
    token_B = await _get_token(runner)
    st_B, body_B = await _exchange_file(runner, fileId_A, token_B)
    leak_B = (st_B == 200) and ("rawUrl" in body_B)
    ev = await runner.screenshot("FILEDL2-b")

    # ── 3. u-X 租户2 上传 → u-X 租户1 用租户2 的 fileId 调置换接口 ──
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-X", tenant="租户2")
    await wb_new_task(runner)
    upx = await wb_upload_file(runner, fixture_path(runner, "upload-test.txt"))
    await runner.page.wait_for_timeout(3000)
    ubx = getattr(runner, "api_upload", None)
    fileId_X2 = ""
    if ubx:
        files = (ubx.get("data") or {}).get("files") or []
        if files:
            fileId_X2 = str(files[0].get("fileId", ""))
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-X", tenant="租户1")
    token_X1 = await _get_token(runner)
    st_X, body_X = await _exchange_file(runner, fileId_X2, token_X1)
    leak_X = (st_X == 200) and ("rawUrl" in body_X)
    ev = await runner.screenshot("FILEDL2-c")

    # ── 判定 ──
    # 属主应能换到 URL(200+rawUrl); 跨用户/同账号跨租户应被拒(非 200 或 无 rawUrl)
    ok_owner = owner_ok
    ok_iso_B = (not leak_B) and (st_B not in (200,))
    ok_iso_X = (not leak_X) and (st_X not in (200,))
    ok = ok_owner and ok_iso_B and ok_iso_X
    st = "通过" if ok else ("失败" if (leak_B or leak_X) else "无法验证")
    runner.set_result("FILEDL2", "真实文件下载置换接口隔离(属主/跨用户/同账号跨租户)",
                      st,
                      actual=f"属主u-A调用→{st_owner}(可用={owner_ok}); u-B用u-A的fileId→{st_B}(泄漏={leak_B}); u-X租户1用租户2的fileId→{st_X}(泄漏={leak_X})",
                      detail=f"属主响应: {body_owner[:120]} | u-B响应: {body_B[:120]} | u-X租户1响应: {body_X[:120]}",
                      evidence=ev)
