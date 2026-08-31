# -*- coding: utf-8 -*-
"""UXFILE 模块：u-X 同账号跨租户文件 URL 获取隔离（原 run_TC_UXFILE 1635-1696 迁移）。"""
from framework.registry import module
from hooks.login import _get_token, _exchange_file, evidence_path, fixture_path
from hooks.wb import wb_login, wb_logout, wb_new_task, wb_upload_file


@module("UXFILE", cases=["UX-07"])
async def run_TC_UXFILE(runner):
    def get_fid():
        ub = getattr(runner, "api_upload", None)
        if ub:
            files = (ub.get("data") or {}).get("files") or []
            if files:
                return str(files[0].get("fileId", ""))
        return ""

    # ── 方向1: u-X 租户2 上传 → 同用户租户1 尝试拿 URL ──
    await wb_login(runner, "u-X", tenant="租户2")
    await wb_new_task(runner)
    await wb_upload_file(runner, fixture_path(runner, "upload-test.txt"))
    await runner.page.wait_for_timeout(3000)
    fid2 = get_fid()
    tok2 = await _get_token(runner)
    st_o2, body_o2 = await _exchange_file(runner, fid2, tok2)  # 属主(租户2)确认可拿
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户1")
    tok1 = await _get_token(runner)
    st_1, body_1 = await _exchange_file(runner, fid2, tok1)  # 租户2 的 fileId + 租户1 token
    leak_1 = (st_1 == 200) and ("rawUrl" in body_1)
    # 保存证据
    try:
        p = evidence_path(runner, "uxfile_d1")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"方向1: u-X 租户2 上传 → 同用户租户1 用租户2 的 fileId 调置换接口\n"
            f"fileId: {fid2}\n属主(租户2)调用: HTTP {st_o2}\n"
            f"租户1 调用: HTTP {st_1}\n响应体: {body_1}\n", encoding="utf-8")
    except Exception:
        pass
    ev = await runner.screenshot("UX-07a")

    # ── 方向2: u-X 租户1 上传 → 同用户租户2 尝试拿 URL(反向) ──
    await wb_new_task(runner)
    await wb_upload_file(runner, fixture_path(runner, "upload-test.txt"))
    await runner.page.wait_for_timeout(3000)
    fid1 = get_fid()
    tok1b = await _get_token(runner)
    st_o1, body_o1 = await _exchange_file(runner, fid1, tok1b)  # 属主(租户1)确认可拿
    await wb_logout(runner)
    await wb_login(runner, "u-X", tenant="租户2")
    tok2b = await _get_token(runner)
    st_2, body_2 = await _exchange_file(runner, fid1, tok2b)  # 租户1 的 fileId + 租户2 token
    leak_2 = (st_2 == 200) and ("rawUrl" in body_2)
    try:
        p = evidence_path(runner, "uxfile_d2")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"方向2: u-X 租户1 上传 → 同用户租户2 用租户1 的 fileId 调置换接口\n"
            f"fileId: {fid1}\n属主(租户1)调用: HTTP {st_o1}\n"
            f"租户2 调用: HTTP {st_2}\n响应体: {body_2}\n", encoding="utf-8")
    except Exception:
        pass
    ev = await runner.screenshot("UX-07b")

    owner_ok = (st_o2 == 200) and (st_o1 == 200)
    ok = owner_ok and (not leak_1) and (not leak_2)
    st = "通过" if ok else "失败"
    runner.set_result("UX-07", "u-X同账号跨租户文件URL获取隔离(双向)",
                      st,
                      actual=f"方向1(租户2上传→租户1取): {st_1}(泄漏={leak_1}); 方向2(租户1上传→租户2取): {st_2}(泄漏={leak_2}); 属主取URL均正常={owner_ok}",
                      detail=f"方向1响应: {body_1[:120]} | 方向2响应: {body_2[:120]}",
                      evidence=ev)
