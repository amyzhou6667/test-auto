# -*- coding: utf-8 -*-
"""demo 假项目端到端：引擎零 CoreBridge 假设可接入。

monkeypatch 掉 Runner.start/close（不启动真实浏览器），走 run_project.main 全链路，
验证 hooks 加载、@module 注册、模块执行、报告落盘。
"""
import os
from pathlib import Path

from framework.config import load_project

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_demo_project_runs_report(monkeypatch, tmp_path, capsys):
    # 不启动浏览器: 引擎的 start/close 替换为 no-op
    from framework.engine import Runner

    async def _fake_start(self):
        self.page = None
        for key in ("results", "screenshots", "reports", "evidence"):
            try:
                self.cfg.resolve_path(key).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

    async def _fake_close(self):
        pass

    monkeypatch.setattr(Runner, "start", _fake_start)
    monkeypatch.setattr(Runner, "close", _fake_close)

    import run_project
    run_project.main(["--project", "demo"])

    out = capsys.readouterr().out
    assert "SMOKE-01" in out
    assert "通过" in out

    cfg = load_project("demo", REPO_ROOT)
    files = list(cfg.resolve_path("results").glob("results_*.json"))
    assert files, "demo 应生成 results_*.json"
    report_files = list(cfg.resolve_path("results").glob("report_*.md"))
    assert report_files, "demo 应生成 report_*.md"


def test_demo_list_lists_module():
    import run_project
    run_project.main(["--project", "demo", "--list"])
    # 无断言: --list 不应抛错（宽松加载, 无需环境变量）
