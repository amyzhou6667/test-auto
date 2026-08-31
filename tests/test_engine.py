# -*- coding: utf-8 -*-
"""framework.engine / framework.report 单测：Result、build_markdown 转义、save_report 统计、
screenshot 防覆盖、sniff_rules、api_count_since 前缀。全部不启动真实浏览器。"""
import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock

from framework.config import ProjectConfig
from framework.engine import Result, Runner, run_case_table
from framework.report import save_report, build_markdown


def make_cfg(tmp_path):
    """构造最小 ProjectConfig（临时目录），供引擎/报告测试用。"""
    raw = {
        "project": {"name": "t"},
        "paths": {
            "results": "out/results",
            "screenshots": "out/screenshots",
            "reports": "out/reports",
            "evidence": "out/reports/evidence",
        },
        "api": {
            "api_prefix": "/api/",
            "sniff_rules": [
                {"name": "api_upload", "match": "/files/upload"},
            ],
        },
        "report": {
            "title": "T 报告",
            "address": "http://x",
            "footer": "由 {now} 生成",
        },
        "status": {
            "enums": ["通过", "失败", "无法验证", "未执行", "待补充"],
            "icons": {"通过": "✅", "失败": "❌", "无法验证": "⚠️",
                      "未执行": "⏭️", "待补充": "⏳"},
            "stats": ["通过", "失败", "无法验证"],
        },
    }
    return ProjectConfig(raw, tmp_path)


# ─────────── Result ───────────
def test_result_to_dict_key_is_id():
    r = Result("TC-1", "名称", "通过", "实际", "说明")
    d = r.to_dict()
    assert d["id"] == "TC-1"
    assert set(d) == {"id", "name", "status", "actual", "detail", "evidence"}


# ─────────── build_markdown ───────────
def test_build_markdown_escapes_pipe_and_newline(tmp_path):
    cfg = make_cfg(tmp_path)
    data = [
        {"id": "TC-1", "name": "名|称", "status": "通过",
         "actual": "a|b", "detail": "第一行\n第二行", "evidence": ""},
    ]
    md = build_markdown(data, cfg)
    rows = [ln for ln in md.splitlines() if ln.startswith("| TC-1")]
    assert len(rows) == 1                 # 换行被替换为空格，未把一行拆成多行
    row = rows[0]
    assert "第一行 第二行" in row       # 换行被替换为空格
    assert "\\|" in row                 # | 被转义（detail 与 name 中的）


def test_build_markdown_header_from_cfg(tmp_path):
    cfg = make_cfg(tmp_path)
    md = build_markdown([], cfg)
    assert "# T 报告" in md
    assert "http://x" in md
    assert "由 " in md                   # footer


# ─────────── save_report ───────────
def test_save_report_writes_json_and_md(tmp_path):
    cfg = make_cfg(tmp_path)
    runner = Runner(cfg=cfg)
    runner.set_result("TC-1", "用例", "通过", "实际", "说明")
    runner.set_result("TC-2", "用例2", "待补充", "", "占位")  # 待补充不入统计口径
    jpath, mpath = save_report(runner, cfg)
    assert jpath.exists() and mpath.exists()
    data = json.loads(jpath.read_text(encoding="utf-8"))
    assert len(data) == 2
    md = mpath.read_text(encoding="utf-8")
    assert "**总计:** 2" in md            # 待补充计入总计
    assert "**通过:** 1" in md            # 统计口径只有通过/失败/无法验证
    assert "**无法验证:** 0" in md


# ─────────── screenshot 防同秒覆盖 ───────────
def test_screenshot_filename_has_seq(tmp_path):
    cfg = make_cfg(tmp_path)
    runner = Runner(cfg=cfg)
    runner.page = MagicMock()
    runner.page.screenshot = AsyncMock(return_value=None)
    p1 = asyncio.run(runner.screenshot("TC-1"))
    p2 = asyncio.run(runner.screenshot("TC-1"))
    assert p1 != p2
    assert "_01" in p1 and "_02" in p2     # 序号参与文件名，避免同秒覆盖


# ─────────── _on_response 嗅探规则表 ───────────
def test_on_response_sniff_rule_hit_and_miss(tmp_path):
    cfg = make_cfg(tmp_path)
    runner = Runner(cfg=cfg)
    # 命中 /files/upload
    hit = MagicMock()
    hit.url = "http://x/api/files/upload"
    hit.status = 200
    hit.json = AsyncMock(return_value={"ok": True})
    asyncio.run(runner._on_response(hit))
    assert runner.api_upload == {"ok": True}
    # 未命中（sniff_rules 只有 /files/upload）
    miss = MagicMock()
    miss.url = "http://x/api/sessions"
    miss.status = 200
    miss.json = AsyncMock(return_value={"s": 1})
    asyncio.run(runner._on_response(miss))
    assert not hasattr(runner, "api_sessions")
    # 日志照记
    assert len(runner.api_log) == 2


# ─────────── api_count_since 前缀配置化 ───────────
def test_api_count_since_uses_configured_prefix(tmp_path):
    cfg = make_cfg(tmp_path)
    runner = Runner(cfg=cfg)
    runner.api_log = [
        {"url": "http://x/api/foo", "status": 200, "ts": ""},
        {"url": "http://x/static.js", "status": 200, "ts": ""},
        {"url": "http://x/api/bar", "status": 200, "ts": ""},
    ]
    assert runner.api_count_since(0) == 2   # /api/ 前缀命中 2 条


# ─────────── run_case_table 异常兜底 ───────────
def test_run_case_table_exception_sets_cannot_verify(tmp_path):
    cfg = make_cfg(tmp_path)
    runner = Runner(cfg=cfg)

    async def ok(runner):
        runner.set_result("C-1", "正常", "通过", "", "")

    async def boom(runner):
        raise RuntimeError("x")

    asyncio.run(run_case_table(runner, [("C-1", ok, "正常"), ("C-2", boom, "异常")]))
    assert runner.results["C-1"].status == "通过"
    assert runner.results["C-2"].status == "无法验证"
    assert "执行异常" in runner.results["C-2"].actual
