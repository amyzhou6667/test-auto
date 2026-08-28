# -*- coding: utf-8 -*-
"""yaml_generator 纯函数单测(不依赖浏览器)"""
import re

import yaml_generator as yg

LEGACY_DOC = """\
# 提现需求 REQ-047
| 需求编号 | REQ-047 |
姓名：2-20 个字符，仅支持中文
身份证号：18 位
提现金额：100 的倍数，最低 1000
不允许重复提交
"""

COREBRIDGE_DOC = """\
## 1. 概述

### FR-1 租户管理

**功能点**：

| 编号 | 功能 | 描述 |
| --- | --- | --- |
| FR-1.1 | 新建租户 | 租户名称（必填）、租户标识（必填，仅允许小写字母开头、字母/数字/连字符）、企业简称（选填） |

#### FR-3.1.1 登录流程

| 编号 | 功能 | 描述 |
| --- | --- | --- |
| FR-3.1.1 | 登录 | 输入用户名和密码，调用 /api/users/login |
"""


def test_parse_requirement_legacy_name_idcard_amount():
    """回归: 旧姓名/身份证/金额正则仍能提取结构化规则"""
    req = yg.parse_requirement_text(LEGACY_DOC)
    by_name = {i["name"]: i for i in req["inputs"]}
    assert req["id"] == "REQ-047"
    assert by_name["姓名"]["min_len"] == 2
    assert by_name["姓名"]["max_len"] == 20
    assert by_name["姓名"]["selector"] == "#name-input"
    assert by_name["身份证号"]["length"] == 18
    assert by_name["金额"]["step"] == 100
    assert by_name["金额"]["min_value"] == 1000


def test_parse_requirement_fr_sections_tables():
    """FR-x 章节 + 编号/功能/描述 表格 → 提取字段及规则/pattern"""
    req = yg.parse_requirement_text(COREBRIDGE_DOC)
    by_name = {i["name"]: i for i in req["inputs"]}
    assert "租户名称" in by_name and by_name["租户名称"]["required"]
    assert "租户标识" in by_name
    assert by_name["租户标识"]["pattern"] == r"^[a-z][a-z0-9-]*$"
    assert "企业简称" in by_name and not by_name["企业简称"]["required"]


def test_parse_requirement_h3_h4_sections():
    """H3/H4 子章节被收集进 sections"""
    req = yg.parse_requirement_text(COREBRIDGE_DOC)
    assert "FR-1 租户管理" in req["sections"]
    assert "FR-3.1.1 登录流程" in req["sections"]


def test_parse_field_rule_length_range():
    r = yg.parse_field_rule("必填，2-20 个字符")
    assert r["min_len"] == 2 and r["max_len"] == 20 and r["required"]


def test_parse_field_rule_length_fixed():
    r = yg.parse_field_rule("18 位")
    assert r["length"] == 18


def test_parse_field_rule_step():
    r = yg.parse_field_rule("必须为 100 的倍数")
    assert r["step"] == 100


def test_parse_field_rule_charset_pattern():
    r = yg.parse_field_rule("仅允许小写字母开头、字母/数字/连字符")
    assert r["pattern"] == r"^[a-z][a-z0-9-]*$"


def test_infer_selector_never_invalid_chinese_css():
    """中文名绝不产出 #中文 非法选择器;未知字段回退 #field-{idx}"""
    assert yg._infer_selector("租户名称", 1) == "#field-1"
    assert not yg._infer_selector("租户名称", 1).startswith("#租")
    assert yg._infer_selector("userName", 2) == "#userName"
    assert yg._infer_selector("姓名", 3) == "#name-input"


def test_generate_script_boundary_ids_unique():
    """同一字段含多规则(length+step)时 BOUNDARY id 不冲突"""
    req = yg.parse_requirement_text(LEGACY_DOC)
    script = yg.generate_test_script(req)
    ids = re.findall(r"- id: (BOUNDARY-[\w-]+)", script)
    assert ids
    assert len(ids) == len(set(ids))


def test_generate_script_negative_js_not_empty():
    """负面约束绝不生成空括号 includes();有禁止文本时生成真实断言"""
    req = yg.parse_requirement_text(LEGACY_DOC)
    script = yg.generate_test_script(req)
    assert "includes()" not in script
    assert "includes(" in script


def test_generate_script_contains_step_verify():
    """生成脚本的边界用例带 verify 断言块(供 runner 执行)"""
    req = yg.parse_requirement_text(LEGACY_DOC)
    script = yg.generate_test_script(req)
    assert "verify:" in script
    assert "should_be: disabled" in script


def test_extract_api_endpoints():
    endpoints = yg.extract_api_endpoints("POST /api/user/register 与 GET /api/user/register")
    assert endpoints == ["/api/user/register"]


def test_extract_states_must_not():
    states = yg.extract_states(["必须实名认证", "不允许重复提交", "普通行"])
    types = [s["type"] for s in states]
    assert "must" in types and "not" in types


def test_extract_forbidden_text_quote_and_keyword():
    assert yg.extract_forbidden_text("不允许重复提交") == "重复提交"
    assert yg.extract_forbidden_text("提示「请勿重复操作」") == "请勿重复操作"
    assert yg.extract_forbidden_text("普通约束行") == ""
