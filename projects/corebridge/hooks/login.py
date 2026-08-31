# -*- coding: utf-8 -*-
"""CoreBridge 登录辅助：login_as / token / 置换接口调用。

数据源从全局 ACCOUNTS/BASE_URL 改为 runner.cfg（项目配置）。
"""
from pathlib import Path


async def login_as(runner, account_key, tenant=None, do_save=True, do_enter=False, fill_ids=True):
    """用指定账号填充登录弹窗。
    - tenant: 指定租户名(多租户账号 u-X 必填, 决定用哪对 workbenchId/appId)
    - fill_ids: 是否填 workbenchId/appId(进入工作台必需)
    """
    acc = runner.cfg.account(account_key)
    await runner.fill_userId(acc["userId"])
    await runner.fill_username(acc["username"])
    # 确定租户与 workbenchId/appId
    wb = ap = None
    sel_tenant = None
    if acc.get("tenants"):
        # 多租户账号(u-X): 按租户名取配对
        pair = None
        if tenant:
            pair = next((t for t in acc["tenants"] if t["name"] == tenant), None)
        if not pair:
            pair = acc["tenants"][0]
        sel_tenant = pair["name"]
        wb = pair.get("workbenchId")
        ap = pair.get("appId")
    else:
        sel_tenant = tenant or acc.get("tenant")
        wb = acc.get("workbenchId")
        ap = acc.get("appId")
    if fill_ids and wb:
        await runner.fill_workbenchId(wb)
    if fill_ids and ap:
        await runner.fill_appId(ap)
    await runner.page.wait_for_timeout(1200)
    if sel_tenant:
        await runner.select_tenant(sel_tenant)
    if do_save:
        await runner.click_btn("保存")
        await runner.page.wait_for_timeout(800)
    if do_enter:
        await runner.click_btn("进入工作台")
        await runner.page.wait_for_timeout(4000)
    return acc


async def _get_token(runner):
    """读取 localStorage 登录 token（键名来自配置 api.token_key）。"""
    try:
        key = runner.cfg.api.get("token_key", "cb_login_token")
        return await runner.page.evaluate(f"() => localStorage.getItem('{key}') || ''")
    except Exception:
        return ""


async def _exchange_file(runner, fileId, token):
    """调用真实置换接口 GET /mc/api/v1/agentcore/files/{fileId}。返回 (status, body)。"""
    template = (runner.cfg.api.get("path_templates") or {}).get("exchange_file")
    url = template.format(base=runner.cfg.api_base, fileId=fileId)
    try:
        resp = await runner.page.request.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20000)
        body = ""
        try:
            body = await resp.text()
        except Exception:
            pass
        return resp.status, body[:500]
    except Exception as e:
        return None, str(e)[:120]


def fixture_path(runner, name):
    """返回项目 fixtures 目录下文件绝对路径。"""
    return runner.cfg.resolve_path("fixtures") / name


def evidence_path(runner, key):
    """返回项目证据目录下某文件绝对路径（文件名来自配置 evidence.filenames）。"""
    names = runner.cfg.evidence.get("filenames") or {}
    fname = names.get(key)
    if not fname:
        raise KeyError(f"evidence.filenames 缺 {key}")
    return runner.cfg.resolve_path("evidence") / fname
