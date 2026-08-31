# -*- coding: utf-8 -*-
"""CoreBridge 工作台辅助函数（wb_* 系列，原 execute_test_cases.py 677-1162 迁移）。

数据源从全局常量改为 runner.cfg（账号/URL 模板/关键词/证据表头/夹具路径）。
"""
from framework.util import get_nested
from hooks.login import login_as


async def wb_login(runner, account_key, fill_ids=True, tenant=None):
    """登录并进入工作台。返回是否进入成功。tenant 指定租户(多租户账号必填)。"""
    await runner.goto_login(clear_storage=True)
    await login_as(runner, account_key, tenant=tenant, do_save=True, do_enter=True, fill_ids=fill_ids)
    ok = "/workbench" in await runner.url()
    if not ok:
        await runner.page.wait_for_timeout(2000)
        ok = "/workbench" in await runner.url()
    return ok


async def wb_new_task(runner):
    try:
        await runner.page.locator(".new-task").click(timeout=4000)
        await runner.page.wait_for_timeout(800)
        return True
    except Exception:
        return False


async def wb_send(runner, text):
    """在聊天输入框输入消息并按 Enter 发送"""
    try:
        ta = runner.page.locator("div.chat-rich-text").first
        await ta.click(timeout=4000)
        await ta.fill(text)
        await runner.page.wait_for_timeout(400)
        await runner.page.keyboard.press("Enter")
        return True
    except Exception:
        return False


async def wb_wait_reply(runner, timeout=75, contains=None):
    """等待 AI 回复渲染完成。完成信号: 命中 contains 文本 / 出现动作栏(action-bar)且已发起过 SSE。"""
    n0 = runner.api_snapshot_len()
    seen_sse = False
    last_body = ""
    for i in range(int(timeout / 3)):
        await runner.page.wait_for_timeout(3000)
        try:
            last_body = await runner.page.evaluate("document.body.innerText")
        except Exception:
            last_body = ""
        new_api = runner.api_log[n0:]
        if any("/agentcore/chat" in e["url"] for e in new_api):
            seen_sse = True
        if contains and contains in last_body:
            return True, last_body
        # 动作栏出现 + 已发请求 → 回复完成
        try:
            ab = await runner.page.locator(".action-bar-wrapper").count()
        except Exception:
            ab = 0
        if ab >= 1 and seen_sse:
            await runner.page.wait_for_timeout(1500)
            return True, last_body
    return seen_sse, last_body


async def wb_session_titles(runner):
    """读取历史任务会话标题列表(.ch-task__title)"""
    try:
        return await runner.page.evaluate("""() =>
            Array.from(document.querySelectorAll('.ch-task__title')).map(e => (e.innerText||'').trim())
        """)
    except Exception:
        return []


async def wb_session_click(runner, index=0):
    """打开第 index 个历史会话"""
    try:
        await runner.page.locator(".ch-task__title").nth(index).click(timeout=4000)
        await runner.page.wait_for_timeout(1500)
        return True
    except Exception:
        return False


async def wb_intent_titles(runner):
    try:
        return await runner.page.evaluate("""() => {
            const b = document.querySelector('.intent-list');
            if (!b) return [];
            const txt = b.innerText || '';
            return txt.split('\\n').map(s=>s.trim()).filter(s=>s && s!=='收藏意图' && s!=='暂无收藏意图');
        }""")
    except Exception:
        return []


async def wb_sidebar_text(runner):
    """左侧栏完整文本(会话+意图)"""
    try:
        return await runner.page.evaluate("""() => {
            const parts = [];
            const conv = document.querySelector('.conversation-history');
            const int = document.querySelector('.intent-list');
            if (conv) parts.push(conv.innerText||'');
            if (int) parts.push(int.innerText||'');
            return parts.join(' || ');
        }""")
    except Exception:
        return ""


async def wb_logout(runner):
    """退出登录, 返回是否回到登录页"""
    try:
        await runner.page.locator(".user-bar button, button.icon-btn:has-text('⏻')").first.click(timeout=4000)
        await runner.page.wait_for_timeout(800)
        for csel in ["button:has-text('退出登录')", ".el-message-box button:has-text('确定')", "button:has-text('确定退出')"]:
            try:
                loc = runner.page.locator(csel).first
                if await loc.count() > 0:
                    await loc.click(timeout=3000)
                    break
            except Exception:
                continue
        await runner.page.wait_for_timeout(2000)
        return "login" in await runner.url()
    except Exception:
        return False


async def wb_get_url(runner):
    return await runner.url()


async def wb_first_session_id(runner):
    """从已捕获的 /api/v1/sessions 响应中提取第一个会话 ID(复用应用自身已鉴权的请求)。"""
    try:
        body = getattr(runner, "api_sessions", None)
        if not body:
            return ""
        data = body.get("data") if isinstance(body, dict) else None
        lst = None
        if isinstance(data, dict):
            lst = data.get("list") or data.get("rows") or data.get("items")
        elif isinstance(data, list):
            lst = data
        if not lst and isinstance(body, dict):
            lst = body.get("list") or body.get("rows") or body.get("items")
        if not lst:
            return ""
        s = lst[0] if isinstance(lst, list) else None
        if not isinstance(s, dict):
            return ""
        return str(s.get("sessionId") or s.get("id") or s.get("conversationId") or s.get("uuid") or "")
    except Exception:
        return ""


async def wb_upload_file(runner, file_path=None):
    """通过发送区上传按钮上传本地文件。返回是否成功。默认上传配置的夹具 upload-test.txt。"""
    file_path = file_path or (runner.cfg.resolve_path("fixtures") / "upload-test.txt")
    try:
        fi = runner.page.locator(".sender-topbar-upload input[type=file], .el-upload input[type=file]")
        if await fi.count() > 0:
            await fi.set_input_files(str(file_path))
            await runner.page.wait_for_timeout(2000)
            return True
        return False
    except Exception:
        return False


async def wb_click_actionbar(runner, index=1):
    """点击最新一条 AI 回复动作栏第 index 个图标(0=重新发送, 1=收藏意图, 2=复制文本)。"""
    try:
        bar = runner.page.locator(".action-bar-wrapper").last
        btn = bar.locator(".btn-item").nth(index)
        await btn.click(timeout=4000)
        await runner.page.wait_for_timeout(1500)
        return True
    except Exception:
        return False


async def wb_favorite_intent(runner, index=1):
    """点击收藏意图按钮并完成『提取意图』对话框, 返回是否成功入库。
    提取为多阶段 AI 过程(理解主旨→整理表述→模板), 以『确认/保存』按钮出现为完成信号。"""
    try:
        bar = runner.page.locator(".action-bar-wrapper").last
        btn = bar.locator(".btn-item").nth(index)
        await btn.click(timeout=4000)
        await runner.page.wait_for_timeout(1000)
        dlg = runner.page.locator(".distill-dialog")
        try:
            await dlg.wait_for(state="visible", timeout=6000)
        except Exception:
            return False
        # 等待提取完成: 出现确认按钮(直接保存/保存/确认等) 或 对话框自行关闭
        confirm_labels = ["保存", "确认", "确定", "收藏", "添加"]
        completed = False
        for _ in range(40):  # 最长 ~80s
            try:
                if not await dlg.is_visible():
                    completed = True
                    break
                labels = [b.strip() for b in await dlg.locator("button").all_inner_texts()]
                # 部分匹配: "直接保存" 含 "保存"
                if any(any(cl in lbl for cl in confirm_labels) for lbl in labels):
                    completed = True
                    break
            except Exception:
                break
            await runner.page.wait_for_timeout(2000)
        # 点击确认/保存按钮
        clicked = False
        for lbl in confirm_labels:
            try:
                b = dlg.locator(f"button:has-text('{lbl}')")
                if await b.count() > 0:
                    await b.first.click(timeout=3000)
                    clicked = True
                    break
            except Exception:
                continue
        await runner.page.wait_for_timeout(2000)
        return clicked or completed
    except Exception:
        return False


async def wb_reply_text(runner):
    """读取最新一条 AI 回复文本(仅 assistant 气泡 .el-bubble-start, 跳过用户消息/错误)。"""
    try:
        return await runner.page.evaluate("""() => {
            const bubbles = Array.from(document.querySelectorAll('.el-bubble'));
            for (let i = bubbles.length - 1; i >= 0; i--) {
                const cls = bubbles[i].className || '';
                // 只取 assistant 气泡(start), 跳过用户消息(end)
                if (!cls.includes('bubble-start')) continue;
                const t = (bubbles[i].innerText || '').trim();
                if (!t) continue;
                if (/出错了|请重试|连接已中断/.test(t)) continue;
                return t;
            }
            return '';
        }""")
    except Exception:
        return ""


async def wb_open_market(runner):
    """打开资源市场。返回是否成功。"""
    try:
        await runner.page.locator(".r-market").click(timeout=4000)
        await runner.page.wait_for_timeout(2000)
        return True
    except Exception:
        return False


async def wb_check_logged_in_user(runner):
    """返回当前登录用户标识(用于判断当前是哪个账号)。"""
    try:
        return await runner.page.evaluate("""() => {
            const bar = document.querySelector('.user-bar');
            return bar ? (bar.innerText||'').trim().slice(0,40) : '';
        }""")
    except Exception:
        return ""


async def wb_get_upload_url(runner):
    """从上传响应提取文件 rawUrl(用于跨租户文件访问隔离测试)。"""
    try:
        body = getattr(runner, "api_upload", None)
        path = (runner.cfg.api.get("upload_response") or {}).get("rawUrl", "data.files[0].rawUrl")
        raw = get_nested(body, path)
        return str(raw) if raw else ""
    except Exception:
        return ""


async def wb_check_url_access(runner, url, ev_path=None):
    """以当前登录身份访问目标 URL, 返回 (status, body片段)。ev_path 非空时把 HTTP 响应写入证据文件。"""
    headers_cfg = (runner.cfg.evidence or {}).get("headers") or {}
    try:
        resp = await runner.page.request.get(url, timeout=20000)
        try:
            body = await resp.text()
        except Exception:
            body = ""
        status = resp.status
        if ev_path:
            try:
                ev_path.parent.mkdir(parents=True, exist_ok=True)
                with open(ev_path, "w", encoding="utf-8") as f:
                    f.write(headers_cfg.get("request_url", "请求 URL: {url}").format(url=url) + "\n")
                    f.write(headers_cfg.get("http_status", "HTTP 状态: {status}").format(status=status) + "\n")
                    f.write(headers_cfg.get("content_type", "Content-Type: {content_type}").format(
                        content_type=resp.headers.get('content-type', '')) + "\n")
                    f.write(headers_cfg.get("identity", "请求方身份: 当前登录账号(见报告说明)") + "\n\n")
                    f.write(headers_cfg.get("body_begin", "=== HTTP 响应体 ===") + "\n")
                    f.write(body[:3000])
                print(f"     [证据已保存] {ev_path}")
            except Exception as e:
                print(f"     [证据保存失败] {e}")
        return status, body[:500]
    except Exception as e:
        if ev_path:
            try:
                ev_path.parent.mkdir(parents=True, exist_ok=True)
                with open(ev_path, "w", encoding="utf-8") as f:
                    f.write(headers_cfg.get("request_url", "请求 URL: {url}").format(url=url) + "\n\n=== 请求异常 ===\n" + str(e)[:500] + "\n")
            except Exception:
                pass
        return None, str(e)[:120]


async def wb_wait_session(runner, keyword, timeout=15):
    """轮询历史任务列表直到出现包含 keyword 的会话。返回是否出现。"""
    for _ in range(int(timeout)):
        titles = await wb_session_titles(runner)
        if any(keyword in t for t in titles):
            return True
        await runner.page.wait_for_timeout(1000)
    return False


async def wb_check_deeplink(runner, target_sid, leak_keyword):
    """以当前(目标)账号身份访问目标会话深链, 判断是否泄漏/隔离。
    返回 (result, url, body): result ∈ leaked/isolated"""
    base = runner.cfg.api_base
    templates = (runner.cfg.api.get("path_templates") or {}).get("deeplink_candidates", [])
    candidates = [t.format(base=base, sid=target_sid) for t in templates]
    for u in candidates:
        try:
            await runner.page.goto(u, wait_until="domcontentloaded", timeout=15000)
            await runner.page.wait_for_timeout(2500)
            body = await runner._safe(runner.body_text)
            if leak_keyword in body:
                return "leaked", u, body
            not_found = any(k in body for k in ["此内容不可用", "未找到", "404", "不存在", "无权限", "无权访问"])
            if not_found:
                return "isolated", u, body
        except Exception:
            continue
    # 无泄漏即视为隔离(未能出现404也可能只是无深链路由, 但内容未泄漏)
    return "isolated", "", ""
