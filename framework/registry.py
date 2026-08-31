# -*- coding: utf-8 -*-
"""模块注册表：@module 装饰器登记项目钩子模块，替代 execute_test_cases.py 的 15 个 elif。"""


class ModuleSpec:
    """一个已注册的测试模块。name=模块名，fn=执行函数，cases=该模块覆盖的用例 id 列表。"""

    def __init__(self, name, fn, cases=None):
        self.name = name
        self.fn = fn
        self.cases = list(cases) if cases else []

    def __repr__(self):
        return f"<ModuleSpec {self.name} ({len(self.cases)} cases)>"


_MODULES = {}


def module(name, cases=None):
    """装饰器：把模块执行函数注册到全局表。

    用法:
        @module("TC-I", cases=["TC-I-01", ...])
        async def run_TC_I(runner):
            ...
    """
    def decorator(fn):
        if name in _MODULES:
            raise ValueError(f"模块重复注册: {name}")
        _MODULES[name] = ModuleSpec(name, fn, cases)
        return fn
    return decorator


def registered_modules():
    """返回全部已注册模块（{name: ModuleSpec}，按注册顺序）。"""
    return dict(_MODULES)


def is_registered(name):
    return name in _MODULES


def clear():
    """清空注册表（同一进程内切换项目时调用，避免残留）。"""
    _MODULES.clear()
