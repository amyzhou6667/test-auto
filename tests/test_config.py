# -*- coding: utf-8 -*-
"""framework.config 单测：${VAR} 展开 / .env 解析 / 缺失报错 / 项目配置加载。"""
import os
import pytest

from framework.config import (ProjectConfig, resolve_env, load_dotenv,
                              load_project, ConfigError)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─────────── resolve_env ───────────
def test_resolve_env_flat():
    out = resolve_env({"a": "${FOO}"}, {"FOO": "bar"})
    assert out == {"a": "bar"}


def test_resolve_env_nested_dict_list():
    raw = {"a": {"b": ["${X}", {"c": "${Y}"}]}}
    out = resolve_env(raw, {"X": "1", "Y": "2"})
    assert out == {"a": {"b": ["1", {"c": "2"}]}}


def test_resolve_env_missing_no_default():
    missing = []
    out = resolve_env({"a": "${NOPE}"}, {}, missing)
    assert out == {"a": "${NOPE}"}  # 原样保留
    assert missing == ["NOPE"]


def test_resolve_env_default_syntax():
    out = resolve_env({"a": "${FOO:-默认值}"}, {})
    assert out == {"a": "默认值"}
    assert resolve_env({"a": "${FOO:-def}"}, {"FOO": "env"}) == {"a": "env"}


def test_resolve_env_non_string_passthrough():
    raw = {"n": 5, "b": True, "none": None, "l": [1, 2]}
    assert resolve_env(raw, {}) == raw


# ─────────── load_dotenv ───────────
def test_load_dotenv_parses(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# 注释\n\nA=1\nB = hello world\nexport C=3\nD=\n", encoding="utf-8")
    out = load_dotenv(env)
    assert out == {"A": "1", "B": "hello world", "C": "3", "D": ""}


def test_load_dotenv_missing_file(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") == {}


# ─────────── load_project ───────────
def test_load_project_demo(tmp_path, monkeypatch):
    """demo 项目零必填变量可加载，base_url 用默认值。"""
    cfg = load_project("demo", REPO_ROOT)
    assert cfg.project["name"] == "demo"
    assert cfg.base_url == "http://demo.example.com"
    assert cfg.module_order() == ["SMOKE"]
    assert cfg.resolve_path("results") == cfg.root / "out" / "results"


def test_load_project_corebridge_all_env(monkeypatch):
    """CoreBridge 全账号 env 注入后加载成功，结构完整。"""
    vals = {
        "CB_UA_USER_ID": "ua", "CB_UA_WB_ID": "wa", "CB_UA_APP_ID": "aa",
        "CB_UB_USER_ID": "ub", "CB_UB_WB_ID": "wb", "CB_UB_APP_ID": "ab",
        "CB_UX_USER_ID": "ux",
        "CB_UX_T1_WB_ID": "w1", "CB_UX_T1_APP_ID": "a1",
        "CB_UX_T2_WB_ID": "w2", "CB_UX_T2_APP_ID": "a2",
        "CB_UN_USER_ID": "un",
        "CB_UF_USER_ID": "uf", "CB_UF_WB_ID": "wf", "CB_UF_APP_ID": "af",
        "CB_US_USER_ID": "us", "CB_US_WB_ID": "ws", "CB_US_APP_ID": "as",
    }
    for k, v in vals.items():
        monkeypatch.setenv(k, v)
    cfg = load_project("corebridge", REPO_ROOT)
    assert cfg.project.get("adapter") == "hooks.adapter.CoreBridgeRunner"
    assert cfg.base_url.startswith("http://117.187.178.246:19521")
    assert cfg.account("u-X")["tenants"][0]["name"] == "租户2"
    assert len(cfg.module_order()) == 15
    assert len(cfg.report["doc_order"]) == 55
    assert len(cfg.consolidate["supplements"]) == 10
    assert cfg.status_icons()["待补充"] == "⏳"
    assert "待补充" not in cfg.status_stats()


def test_load_project_corebridge_missing_env_raises(monkeypatch):
    """不设账号 env → ConfigError 列出缺失变量，不静默。

    与本地 .env 存在性无关: 清空 CB_* 环境变量 + 隔离 load_dotenv，
    保证在任何机器（有/无 .env）上都走到「缺失变量」分支。
    """
    # 本机 .env 可能已填入真实值 → mock 掉 dotenv 加载, 让缺失判定只依赖环境变量
    monkeypatch.setattr("framework.config.load_dotenv", lambda path: {})
    for key in list(os.environ):
        if key.startswith("CB_"):
            monkeypatch.delenv(key, raising=False)
    with pytest.raises(ConfigError) as ei:
        load_project("corebridge", REPO_ROOT)
    msg = str(ei.value)
    assert "CB_UA_USER_ID" in msg


def test_load_project_unknown_project_raises():
    with pytest.raises(ConfigError):
        load_project("no-such-project", REPO_ROOT)
