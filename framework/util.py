# -*- coding: utf-8 -*-
"""通用小工具：纯函数，无 Playwright 依赖。"""
import sys
import io


def clean_noise(items):
    """过滤列表里的噪音项：空/纯空白/省略号⋯/纯数字。

    合并 execute_test_cases.py 中 clean(1107) 与 _clean_ints(1848) 两份重复实现。
    返回已 strip 的干净项（取两份实现中更规范的去空白版本）。
    """
    return [t.strip() for t in items
            if t and t.strip() and t.strip() != "⋯" and not t.strip().isdigit()]


def get_nested(data, path, default=None):
    """按 'a.b.c' 点路径取嵌套 dict 值，缺失返回 default。"""
    cur = data
    for key in str(path).split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


_UTF8_WRAPPED = False


def win32_utf8():
    """Windows 下把 stdout/stderr 包装为 UTF-8（replace 容错），避免中文打印崩。

    幂等：只包装一次；pytest 捕获（sys.stdout 已被替换为 DontReadFromInput 等）时跳过，
    避免替换 pytest 的捕获流导致 teardown 报 "I/O operation on closed file"。
    """
    global _UTF8_WRAPPED
    if _UTF8_WRAPPED:
        return
    if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
        # 已包装过 / 已被测试框架替换的流，不再动
        if getattr(sys.stdout, "encoding", "").upper().replace("-", "") == "UTF8":
            _UTF8_WRAPPED = True
            return
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        _UTF8_WRAPPED = True
