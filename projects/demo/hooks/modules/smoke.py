# -*- coding: utf-8 -*-
"""demo 冒烟模块：不碰浏览器，直接登记假结果，验证引擎调度/报告链路。"""
from framework.registry import module


@module("SMOKE", cases=["SMOKE-01", "SMOKE-02"])
async def run_SMOKE(runner):
    runner.set_result("SMOKE-01", "引擎可接入(假数据)", "通过",
                      actual="无需浏览器", detail="demo 项目验证")
    runner.set_result("SMOKE-02", "报告链路可用", "通过",
                      actual="report 生成", detail="demo 项目验证")
