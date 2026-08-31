# -*- coding: utf-8 -*-
"""framework.registry 单测：@module 注册、重复注册报错、clear。"""
import pytest

from framework import registry


def test_module_registration():
    registry.clear()
    assert not registry.registered_modules()

    @registry.module("M1", cases=["M1-01"])
    async def run_M1(runner):
        pass

    mods = registry.registered_modules()
    assert "M1" in mods
    assert mods["M1"].cases == ["M1-01"]
    assert registry.is_registered("M1")
    registry.clear()
    assert not registry.is_registered("M1")


def test_duplicate_registration_raises():
    registry.clear()

    @registry.module("M2")
    async def run_M2a(runner):
        pass

    with pytest.raises(ValueError):
        @registry.module("M2")
        async def run_M2b(runner):
            pass

    registry.clear()


def test_module_without_cases():
    registry.clear()

    @registry.module("M3")
    async def run_M3(runner):
        pass

    assert registry.registered_modules()["M3"].cases == []
    registry.clear()
