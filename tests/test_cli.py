# -*- coding: utf-8 -*-
"""framework.cli 单测：resolve_modules 的 --smoke / --all / 模块名解析 + 可用项目列举。"""
import os

from framework import cli

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ORDER = ["TC-I", "TC-B", "TC-N", "TC-ISO", "TC-UIOP"]
SMOKE = ["TC-I", "TC-B", "TC-ISO"]


class _Args:
    def __init__(self, smoke=False, all_=False, modules=None):
        self.smoke = smoke
        self.all = all_
        self.modules = modules or []


def test_smoke_returns_smoke_set():
    mods, invalid = cli.resolve_modules(_Args(smoke=True), ORDER, smoke=SMOKE)
    assert mods == SMOKE
    assert invalid == []


def test_smoke_filters_unknown():
    mods, invalid = cli.resolve_modules(_Args(smoke=True), ORDER, smoke=["TC-I", "NOPE"])
    assert mods == ["TC-I"]
    assert invalid == ["NOPE"]


def test_smoke_empty_falls_back_to_all():
    # --smoke 但配置未定义冒烟集 → 等价 --all（order 全量）
    mods, invalid = cli.resolve_modules(_Args(smoke=True), ORDER, smoke=[])
    assert mods == ORDER
    assert invalid == []


def test_all_returns_order():
    mods, invalid = cli.resolve_modules(_Args(all_=True), ORDER)
    assert mods == ORDER
    assert invalid == []


def test_positional_uppercased_and_filtered():
    mods, invalid = cli.resolve_modules(_Args(modules=["tc-i", "TC-UIOP", "BAD"]), ORDER)
    assert mods == ["TC-I", "TC-UIOP"]
    assert invalid == ["BAD"]


def test_no_modules_defaults_to_all():
    mods, invalid = cli.resolve_modules(_Args(), ORDER)
    assert mods == ORDER
    assert invalid == []


# ─────────── available_projects ───────────
def test_available_projects_lists_real_projects():
    names = cli.available_projects(REPO_ROOT)
    assert "demo" in names
    assert "corebridge" in names
    # 排序且唯一
    assert names == sorted(set(names))
