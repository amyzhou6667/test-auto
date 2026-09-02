# -*- coding: utf-8 -*-
"""
管线1 纯函数（从 script_runner.py 抽取）：参数拍平 / 模板替换 / 条件求值 /
locator 解析 / verify 归一化与求值 / API 字段断言 / API 匹配。

与 script_runner 的浏览器执行层解耦，便于独立单测与框架内复用。
关键安全点：eval_condition 用受限 AST 求值替代内置 eval()——
YAML 脚本中的 condition 只允许常量/比较/算术/布尔运算，拒绝调用/属性/下标等任意代码执行。
"""
import ast
import json
import operator
import re


# ─────────────────────────────────────────────────────────
# 参数处理
# ─────────────────────────────────────────────────────────
def _flatten_params(params, prefix=""):
    """把嵌套 params 拍平成 {a.b.c: value} 形式,长 key 优先(避免子串误替换)。"""
    out = {}
    for k, v in params.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten_params(v, key))
        else:
            out[key] = v
    return out


def _params_sorted(params):
    return sorted(_flatten_params(params).items(), key=lambda kv: len(kv[0]), reverse=True)


def get_nested(obj, path):
    """从嵌套字典/对象中获取路径值。
    path 为空或 "result" 时返回原值(兼容 evaluate 标量返回值,修复 P0-4)。"""
    if not path or path == "result":
        return obj
    parts = path.split(".")
    for part in parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def resolve_template(text, params):
    """替换 {param} 占位符,支持嵌套路径 {a.b.c} 与值内嵌套 {x}={other}。非字符串原样返回。"""
    if not isinstance(text, str):
        return text
    result = text
    pairs = list(_params_sorted(params))
    # 迭代解析至多 5 轮,支持 params 值内部再嵌套占位符
    for _ in range(5):
        new = result
        for key, val in pairs:
            if isinstance(val, (str, int, float, bool)):
                new = new.replace(f"{{{key}}}", str(val))
        if new == result:
            break
        result = new
    return result


# ─────────────────────────────────────────────────────────
# 条件求值（受限 AST，替代 eval）
# ─────────────────────────────────────────────────────────
_CMP_OPS = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
    ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
}
_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_TRUTHY_NAMES = {"true": True, "True": True, "false": False, "False": False}


def _eval_node(node):
    """在受限白名单内求值 AST 节点。

    仅允许: 字面量(数字/字符串/bool/None)、标识符 true/false、比较/算术/布尔运算。
    拒绝: 函数调用、属性访问、下标、lambda、列表推导、import 等任意代码执行。
    """
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in _TRUTHY_NAMES:
            return _TRUTHY_NAMES[node.id]
        raise ValueError(f"未知标识符: {node.id}")
    if isinstance(node, ast.BoolOp):
        vals = [_eval_node(v) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return not _eval_node(node.operand)
        if isinstance(node.op, ast.USub):
            return -_eval_node(node.operand)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval_node(comp)
            if type(op) not in _CMP_OPS or not _CMP_OPS[type(op)](left, right):
                return False
            left = right
        return True
    raise ValueError(f"不支持的表达式节点: {type(node).__name__}")


def eval_condition(condition, params):
    """安全评估条件表达式(布尔/数值参数替换)。

    参数替换后交受限 AST 求值。未知变量或异常默认返回 True（保持原行为）。
    """
    if not condition:
        return True
    try:
        expr = str(condition)
        for key, val in _params_sorted(params):
            if isinstance(val, bool):
                expr = expr.replace(key, str(val).lower())
            elif isinstance(val, (int, float)):
                expr = expr.replace(key, str(val))
            elif isinstance(val, str):
                expr = expr.replace(key, f"'{val}'")
        tree = ast.parse(expr, mode="eval")
        return bool(_eval_node(tree.body))
    except Exception:
        return True


# ─────────────────────────────────────────────────────────
# locator 解析
# ─────────────────────────────────────────────────────────
def _dequote(s):
    """只剥掉首尾成对的引号(不影响值内部引号,如 button "注册")。"""
    s = (s or "").strip()
    while len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1].strip()
    return s


def parse_locator(spec):
    """把元素说明解析为 locator 描述。
    返回 {"kind": "css"|"heading"|"role"|"text"|"auto", "name": str, "role": str|None}
    优先级: CSS(#/.) → heading "…" → button "…" → getByRole(...) → getByText(...) → auto(纯文本)
    """
    s = _dequote(spec)
    if not s:
        return {"kind": "auto", "name": ""}
    if s.startswith("#") or s.startswith("."):
        return {"kind": "css", "name": s}
    m = re.fullmatch(r'heading\s+"([^"]+)"', s)
    if m:
        return {"kind": "heading", "name": m.group(1)}
    m = re.fullmatch(r'button\s+"([^"]+)"', s)
    if m:
        return {"kind": "role", "role": "button", "name": m.group(1)}
    m = re.fullmatch(r"getByRole\('(\w+)',\s*\{?\s*name:\s*'([^']+)'?\s*\}?\)", s)
    if m:
        return {"kind": "role", "role": m.group(1), "name": m.group(2)}
    m = re.fullmatch(r"getByText\('([^']+)'\)", s)
    if m:
        return {"kind": "text", "name": m.group(1)}
    return {"kind": "auto", "name": s}


def parse_click_target(target):
    """解析 click 目标。返回 {"kind": "role"|"text"|"css", "role": str|None, "name": str}"""
    s = _dequote(target)
    parsed = parse_locator(s)
    if parsed["kind"] == "role":
        return {"kind": "role", "role": parsed["role"], "name": parsed["name"]}
    if parsed["kind"] == "text":
        return {"kind": "text", "role": None, "name": parsed["name"]}
    if parsed["kind"] == "heading":
        return {"kind": "role", "role": "heading", "name": parsed["name"]}
    return {"kind": "css", "role": None, "name": s}


# 页面级标签别名: 用于 text_contains 断言的区域回退
PAGE_REGION_ALIASES = {
    "错误提示": "body", "错误信息": "body", "提示": "body",
    "toast": ".ant-message, .el-message, .el-notification, .toast",
    "message": ".ant-message, .el-message",
}


# ─────────────────────────────────────────────────────────
# verify 归一化与求值
# ─────────────────────────────────────────────────────────
def interpret_verify_item(item):
    """把 step.verify 的一项归一化,返回 {"spec", "checks", "optional", "condition"}。
    checks: [(assertion, expected)] — disabled/enabled/exist/not_exist/text_contains,可组合。"""
    item = item or {}
    spec = str(item.get("element") or item.get("selector") or item.get("target") or "")
    checks = []
    should_be = item.get("should_be")
    if should_be in ("disabled", "enabled"):
        checks.append((should_be, True))
    if "should_exist" in item:
        exist = bool(item.get("should_exist"))
        checks.append(("exist" if exist else "not_exist", exist))
    if item.get("text_contains") is not None:
        checks.append(("text_contains", item.get("text_contains")))
    if not checks:
        checks.append(("exist", True))
    return {"spec": spec, "checks": checks,
            "optional": bool(item.get("optional", False)), "condition": item.get("condition")}


def evaluate_verify_result(result, verify_list, params):
    """评估 evaluate action 的 verify 列表(纯函数)。
    修复: path 为空或 result 且结果是标量 → 直接比较 result。
    每条 verify 先判断 condition,false 则跳过。返回 (all_ok, first_failure_msg)。"""
    if not verify_list:
        return True, ""
    for item in verify_list:
        cond = item.get("condition")
        if cond and not eval_condition(cond, params):
            continue
        path = item.get("path", "") or "result"
        expect_val = item.get("expect")
        expect_gt = item.get("expect_gt")
        expect_not = item.get("expect_not")
        expect_not_empty = item.get("expect_not_empty", False)
        actual = get_nested(result, path)
        if expect_val is not None and actual != expect_val:
            return False, f"{path}={actual!r} (期望 {expect_val!r})"
        if expect_gt is not None and (actual is None or not isinstance(actual, (int, float)) or actual <= expect_gt):
            return False, f"{path}={actual!r} (期望 > {expect_gt})"
        if expect_not is not None and actual == expect_not:
            return False, f"{path}={actual!r} (不应等于 {expect_not!r})"
        if expect_not_empty and not actual:
            return False, f"{path} 为空"
    return True, ""


def _stringify(obj):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (list, dict)):
        return json.dumps(obj, ensure_ascii=False)
    return "" if obj is None else str(obj)


def verify_api_field(body, item):
    """验证 API 响应字段(纯函数)。
    支持 expect / expect_gt / expect_not / expect_not_empty / expect_contain / expect_not_contain。"""
    item = item or {}
    path = item.get("path", "")
    actual = get_nested(body, path)
    expect_val = item.get("expect")
    expect_gt = item.get("expect_gt")
    expect_not = item.get("expect_not")
    expect_not_empty = item.get("expect_not_empty", False)
    expect_contain = item.get("expect_contain")
    expect_not_contain = item.get("expect_not_contain")

    if expect_val is not None and actual != expect_val:
        return False, f"{path}={actual!r} (期望 {expect_val!r})"
    if expect_gt is not None and (actual is None or not isinstance(actual, (int, float)) or actual <= expect_gt):
        return False, f"{path}={actual!r} (期望 > {expect_gt})"
    if expect_not is not None and actual == expect_not:
        return False, f"{path}={actual!r} (不应等于 {expect_not!r})"
    if expect_not_empty and not actual:
        return False, f"{path} 为空"
    if expect_contain is not None:
        if expect_contain not in _stringify(actual):
            return False, f"{path} 不包含 {expect_contain!r}"
    if expect_not_contain is not None:
        if expect_not_contain in _stringify(actual):
            return False, f"{path} 不应包含 {expect_not_contain!r}"
    return True, ""


def find_api_match(api_responses, url_pattern):
    """在捕获的响应字典中按子串匹配 URL,返回首个命中响应或 None。"""
    if not url_pattern:
        return None
    for api_url, resp in api_responses.items():
        if url_pattern in api_url:
            return resp
    return None
