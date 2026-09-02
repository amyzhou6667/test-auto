# -*- coding: utf-8 -*-
"""demo 假项目端到端：引擎零 CoreBridge 假设可接入。

monkeypatch 掉 Runner.start/close（不启动真实浏览器），走 run_project.main 全链路，
验证 hooks 加载、@module 注册、模块执行、报告落盘。
产物目录重定向到 tmp_path，不污染真实 projects/demo/out/。
"""
import os

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

    # 产物路径重定向到 tmp_path（demo 配置 paths 覆盖为绝对路径）
    def _load_to_tmp(name, repo_root, strict=True):
        cfg = load_project(name, repo_root, strict)
        base = tmp_path / "out"
        for key in ("results", "screenshots", "reports", "evidence"):
            cfg.paths[key] = str(base / key)
        return cfg

    import run_project
    monkeypatch.setattr(run_project, "load_project", _load_to_tmp)

    run_project.main(["--project", "demo"])

    out = capsys.readouterr().out
    assert "SMOKE-01" in out
    assert "通过" in out

    results_dir = tmp_path / "out" / "results"
    files = list(results_dir.glob("results_*.json"))
    assert files, "demo 应生成 results_*.json"
    report_files = list(results_dir.glob("report_*.md"))
    assert report_files, "demo 应生成 report_*.md"


def test_demo_list_lists_module():
    import run_project
    run_project.main(["--project", "demo", "--list"])
    # 无断言: --list 不应抛错（宽松加载, 无需环境变量）
