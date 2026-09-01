# -*- coding: utf-8 -*-
"""项目配置 ↔ hooks 注册表一致性单测：防止用例 drift 导致合并静默丢结果。

用例 id 存在于三处（模块 @module(cases)、执行时 set_result、consolidate 锚点），
本测试校验前两处与配置声明的一致性，任何一处漂移立刻暴露：

  1. base 强校验: consolidate.base 每个模块的 first_id 必须 == 该模块 @module(cases) 首项
     —— 否则 find_base 按 first_id 前缀匹配会匹配到错误的模块/运行文件。
  2. supplements 弱校验: 每个补充模块的 anchors 锚点必须存在于至少一个已注册模块的 cases 中
     —— 否则 find_supp 精确相等匹配永远找不到补跑文件, 锚定的用例结果会丢失。
"""
import os

from framework.config import load_project
from framework.loader import load_hooks

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _check_project(project_name):
    cfg = load_project(project_name, REPO_ROOT, strict=False)
    mods, _ = load_hooks(cfg)
    all_cases = set()
    for spec in mods.values():
        all_cases.update(spec.cases)

    # 1) base 强校验
    for item in cfg.consolidate.get("base") or []:
        module, first_id = item["module"], item["first_id"]
        spec = mods.get(module)
        assert spec is not None, f"{project_name}: base 模块 {module} 未注册"
        assert spec.cases, f"{project_name}: 模块 {module} 未登记用例 (cases 为空)"
        assert spec.cases[0] == first_id, (
            f"{project_name}: {module} 用例首项 {spec.cases[0]!r} != "
            f"consolidate.base.first_id {first_id!r}")

    # 2) supplements 锚点弱校验
    for item in cfg.consolidate.get("supplements") or []:
        for anchor in item["anchors"]:
            assert anchor in all_cases, (
                f"{project_name}: 补充模块 {item['module']} 锚点 {anchor!r} "
                f"不在任何模块登记的 cases 中")


def test_corebridge_consistency():
    _check_project("corebridge")


def test_demo_consistency():
    _check_project("demo")
