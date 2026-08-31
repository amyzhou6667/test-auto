# -*- coding: utf-8 -*-
"""FILEDL 模块：u-B 能否通过应用接口拿到 u-A 文件（原 run_TC_FILEDL 1782-1842 迁移）。"""
from framework.registry import module
from hooks.login import _get_token, _exchange_file, evidence_path, fixture_path
from hooks.wb import wb_login, wb_logout, wb_new_task, wb_upload_file


@module("FILEDL", cases=["FILEDL"])
async def run_TC_FILEDL(runner):
    # u-A 上传, 捕获 fileId + rawUrl
    await wb_login(runner, "u-A")
    await wb_new_task(runner)
    up = await wb_upload_file(runner, fixture_path(runner, "upload-test.txt"))
    await runner.page.wait_for_timeout(4000)
    ub = getattr(runner, "api_upload", None)
    fileId, rawUrl = "", ""
    if ub:
        files = (ub.get("data") or {}).get("files") or []
        if files:
            fileId = str(files[0].get("fileId", ""))
            rawUrl = str(files[0].get("rawUrl", ""))
    print(f"     [FILEDL] 上传成功={up}, api_upload={ub is not None}, fileId={fileId[:30] or '空'}")
    ev = await runner.screenshot("FILEDL-a")
    if await wb_logout(runner):
        await runner.page.wait_for_timeout(800)
    await wb_login(runner, "u-B")
    if not fileId:
        runner.set_result("FILEDL", "u-B能否通过应用接口拿到u-A文件",
                          "无法验证",
                          actual="未捕获到 u-A 的 fileId", detail="", evidence=ev)
        return
    token = await _get_token(runner)
    base = runner.cfg.api_base
    candidates = [t.format(base=base, fileId=fileId) for t in runner.cfg.api["path_templates"]["filedl_candidates"]]
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    results = []
    for url in candidates:
        try:
            resp = await runner.page.request.get(url, headers=headers, timeout=15000)
            body = ""
            try:
                body = (await resp.text())[:200]
            except Exception:
                pass
            results.append({"path": url.replace(base, ""), "status": resp.status, "body": body})
        except Exception as e:
            results.append({"path": url.replace(base, ""), "status": None, "body": str(e)[:80]})
    file_kw = ["梦想", "鸭爪", "江永", "世界和平", "开开心心"]
    leaked = [r for r in results if r["status"] == 200 and any(k in r["body"] for k in file_kw)]
    any200 = [r for r in results if r["status"] == 200]
    ok = len(leaked) == 0
    ev = await runner.screenshot("FILEDL-b")
    detail = " | ".join(f"{r['path']}→{r['status']}" for r in results)
    runner.set_result("FILEDL", "u-B能否通过应用接口拿到u-A文件(判定隔离可绕过性)",
                      "通过" if ok else "失败",
                      actual=f"u-A fileId={fileId[:26]}..., 候选接口{len(results)}个, 返回200={len(any200)}, 含文件内容泄漏={len(leaked)}",
                      detail=detail, evidence=ev)
