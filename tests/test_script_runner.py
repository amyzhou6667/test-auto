# -*- coding: utf-8 -*-
"""script_runner 纯函数单测(不依赖浏览器)"""
from pathlib import Path

import script_runner as sr


def test_get_nested():
    assert sr.get_nested({"a": {"b": 1}}, "a.b") == 1
    assert sr.get_nested({"a": 1}, "a") == 1
    assert sr.get_nested({"a": 1}, "x.y") is None


def test_get_nested_result_scalar():
    """P0-4: path=result + 标量返回值直接返回原值(不再因 _get_nested(bool) 返回 None 恒失败)"""
    assert sr.get_nested(True, "result") is True
    assert sr.get_nested("ok", "result") == "ok"


def test_eval_condition_bool_int_missing():
    params = {"account_verified": True, "withdrawable_balance": 11130}
    assert sr.eval_condition("account_verified == true", params) is True
    assert sr.eval_condition("account_verified == false", params) is False
    assert sr.eval_condition("withdrawable_balance < 1000", params) is False
    assert sr.eval_condition("unknown_param > 5", params) is True  # 未知变量默认通过
    assert sr.eval_condition("", params) is True


def test_eval_condition_rejects_exec_nodes():
    """受限 AST 求值: 函数调用/属性/下标等恶意表达式不得被求值(异常→默认 True, 不执行)。"""
    params = {}
    for malicious in ("__import__('os')", "().__class__", "[1][0]", "lambda: 1",
                      "1 if True else 0", "open('x')", "().__getattribute__"):
        # 关键断言: 不会抛出且不会执行任意代码——默认返回 True（安全降级）
        assert sr.eval_condition(malicious, params) is True, malicious
    # 正常算术/布尔运算仍可用
    assert sr.eval_condition("1 < 2 and 3 > 2", {}) is True
    assert sr.eval_condition("1 + 1 == 2", {}) is True


def test_parse_locator_css():
    assert sr.parse_locator("#withdraw-amount-input")["kind"] == "css"
    assert sr.parse_locator(".table")["kind"] == "css"


def test_parse_locator_styles():
    assert sr.parse_locator('heading "生产者中心"')["kind"] == "heading"
    assert sr.parse_locator('heading "生产者中心"')["name"] == "生产者中心"
    assert sr.parse_locator('button "注册"') == {"kind": "role", "role": "button", "name": "注册"}
    assert sr.parse_locator("getByRole('button', { name: '结算' })") == {"kind": "role", "role": "button", "name": "结算"}
    assert sr.parse_locator("getByText('用户0594')")["kind"] == "text"
    assert sr.parse_locator("提交认证")["kind"] == "auto"


def test_parse_click_target():
    parsed = sr.parse_click_target("getByRole('button', { name: '结算' })")
    assert parsed["kind"] == "role" and parsed["role"] == "button"
    assert sr.parse_click_target("#foo")["kind"] == "css"


def test_interpret_verify_item_combined():
    item = sr.interpret_verify_item({
        "element": "开户行", "text_contains": "招商银行", "should_exist": True,
        "optional": True, "condition": "a == true",
    })
    assert item["checks"] == [("exist", True), ("text_contains", "招商银行")]
    assert item["optional"] and item["condition"] == "a == true"


def test_interpret_verify_item_should_be():
    item = sr.interpret_verify_item({"element": "提交结算申请", "should_be": "disabled"})
    assert item["checks"] == [("disabled", True)]


def test_interpret_verify_item_selector_field():
    """P0-3: selector 字段被采用(与 element 同源)"""
    item = sr.interpret_verify_item({"selector": "实名认证", "should_exist": True})
    assert item["spec"] == "实名认证"


def test_evaluate_verify_result_scalar_result():
    """P0-4: evaluate 返回标量 + path=result 正确比较"""
    ok, msg = sr.evaluate_verify_result(True, [{"path": "result", "expect": True}], {})
    assert ok, msg
    ok, _ = sr.evaluate_verify_result(False, [{"path": "result", "expect": True}], {})
    assert not ok


def test_evaluate_verify_result_condition_false_skips():
    """P0-4: condition=false 的 verify 项跳过,不失败"""
    ok, msg = sr.evaluate_verify_result(
        {"v": 0},
        [{"path": "v", "expect": 1, "condition": "flag == true"}],
        {"flag": False},
    )
    assert ok, msg


def test_evaluate_verify_result_expect_mismatch_fails():
    ok, _ = sr.evaluate_verify_result({"v": 1}, [{"path": "v", "expect": 2}], {})
    assert not ok
    ok, _ = sr.evaluate_verify_result({"v": 10}, [{"path": "v", "expect_gt": 5}], {})
    assert ok
    ok, _ = sr.evaluate_verify_result({"v": "  "}, [{"path": "v", "expect_not_empty": True}], {})
    assert ok


def test_verify_api_field_contain():
    ok, _ = sr.verify_api_field({"data": {"list": ["a", "b"]}}, {"path": "data.list", "expect_contain": "a"})
    assert ok
    ok, _ = sr.verify_api_field({"data": {"list": ["a", "b"]}}, {"path": "data.list", "expect_not_contain": "a"})
    assert not ok
    ok, _ = sr.verify_api_field({"data": {"code": 0}}, {"path": "data.code", "expect": 0})
    assert ok


def test_find_api_match():
    responses = {"http://h/api/user/1": {"status": 200}}
    assert sr.find_api_match(responses, "/api/user")["status"] == 200
    assert sr.find_api_match(responses, "/api/none") is None


def test_resolve_template_nested():
    params = {"base_url": "http://x", "test_account": {"phone": "13616510594"}, "account_verified": True}
    assert sr.resolve_template("{base_url}/p", params) == "http://x/p"
    assert sr.resolve_template("{test_account.phone}", params) == "13616510594"
    assert sr.resolve_template("{account_verified}", params) == "True"


# ─────────── --project 产物目录路由 ───────────
def _script_yaml(path, project=None):
    meta = "  id: SCRIPT-X\n  name: x\n  req: REQ-X\n"
    if project:
        meta += f"  project: {project}\n"
    path.write_text(
        f"metadata:\n{meta}version: 1.0\n"
        "params:\n  base_url: http://demo.example.com\n"
        "steps:\n  - id: S-1\n    name: x\n    actions: []\n",
        encoding="utf-8")


def test_script_runner_project_metadata_routes_dirs(tmp_path):
    """metadata.project 兜底: 报告/截图/history 指向 projects/<名>/out/ 下。"""
    y = tmp_path / "s.yaml"
    _script_yaml(y, project="demo")
    r = sr.ScriptRunner(str(y))
    r.load_script()
    assert r.report_dir == Path(__file__).resolve().parents[1] / "projects" / "demo" / "out" / "reports"
    assert r.screenshot_dir == Path(__file__).resolve().parents[1] / "projects" / "demo" / "out" / "screenshots"


def test_script_runner_cli_project_overrides_metadata(tmp_path):
    """CLI --project 优先于 metadata.project。"""
    y = tmp_path / "s.yaml"
    _script_yaml(y, project="demo")  # 元数据写 demo, CLI 显式给 corebridge
    r = sr.ScriptRunner(str(y), project="corebridge")
    r.load_script()
    assert r.report_dir.name == "reports"
    assert "corebridge" in str(r.report_dir)


def test_script_runner_no_project_keeps_legacy_dirs(tmp_path):
    """不传 --project 且脚本无 metadata.project → 保持仓库根旧路径。"""
    y = tmp_path / "s.yaml"
    _script_yaml(y)  # 无 project
    r = sr.ScriptRunner(str(y))
    r.load_script()
    assert r.report_dir == Path(__file__).resolve().parents[1] / "reports"
    assert r.screenshot_dir == Path(__file__).resolve().parents[1] / "screenshots"
