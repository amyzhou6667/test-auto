#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
YAML 测试脚本自动生成器

读取需求文档 (.md)，自动分析测试点，生成可直接执行的 YAML 测试脚本。

用法:
    python yaml_generator.py docs/xxx.md                           # 生成测试脚本
    python yaml_generator.py docs/xxx.md --output scripts/xxx.yaml # 指定输出
    python yaml_generator.py docs/xxx.md --run                      # 生成后直接执行
"""
import re
import sys
import json
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    import io
    # 注意: sys.stdout 包装移入 __main__ 块,避免在 import 时替换导致 pytest capture 失效
    _io = io
else:
    _io = None


# ─────────────────────────────────────────────────────────
# 通用化需求文档解析(支持 FR-x.x 章节 + 表格 + 描述文本内嵌字段规则)
# ─────────────────────────────────────────────────────────

FIELD_DEF_RE = re.compile(r"([^\s，。、；;：:（）()/|]{1,20})\s*[（(]((?:必填|选填)[^）)]*)[）)]")


def parse_requirement(file_path: Path) -> dict:
    """解析需求文档，提取结构化信息（通用化解析,委托 parse_requirement_text）"""
    req = parse_requirement_text(file_path.read_text(encoding="utf-8"))
    req["file"] = file_path.name
    return req


def parse_requirement_text(text: str) -> dict:
    """从需求文档文本提取结构化信息(纯函数,可单测,无需临时文件)"""
    lines = text.split("\n")
    sections = extract_sections(lines)
    text_no_table = re.sub(r"\|[^\n]*\|", "", text)
    req = {
        "file": "",
        "title": _extract_title(lines),
        "id": _extract_req_id(lines),
        "inputs": extract_field_items(sections, text_no_table),
        "buttons": extract_buttons(sections),
        "api_endpoints": extract_api_endpoints(text),
        "states": extract_states(lines),
        "sections": {s["title"]: {"subsections": s["subsections"], "content": s["content"], "tables": s["tables"]} for s in sections},
        "flow": [],
    }
    return req


def _extract_title(lines):
    for line in lines:
        m = re.match(r"^#\s+(.+)", line)
        if m:
            return m.group(1).strip()
    return ""


def _extract_req_id(lines):
    for line in lines:
        m = re.search(r"REQ-?\d+", line)
        if m:
            return m.group(0)
    return ""


def extract_sections(lines):
    """按 H2/H3/H4 构建章节树,返回 [{title, id, level, content, tables, subsections}]"""
    sections = []
    stack = []  # (level, index_in_sections)
    current = None
    for line in lines:
        m = re.match(r"^(#{2,4})\s+(.+)", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            sec = {"title": title, "id": _extract_req_id([title]), "level": level,
                   "content": [], "tables": [], "subsections": []}
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                sections[stack[-1][1]]["subsections"].append(title)
            sections.append(sec)
            stack.append((level, len(sections) - 1))
            current = sec
            continue
        if current is not None:
            current["content"].append(line)
            if line.strip().startswith("|"):
                current["tables"].append(line)
    return sections


def parse_table_blocks(table_lines):
    """把连续 | 行分组成表格块,每块为 [row...],每 row 为 [cell...]。跳过 |---| 分隔行。"""
    blocks = []
    current = None
    for line in table_lines:
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and all(re.fullmatch(r":?-+:?", c) for c in cells if c != ""):
                continue
            if current is None:
                current = []
                blocks.append(current)
            current.append(cells)
        else:
            current = None
    return blocks


def _is_non_field_name(name):
    """过滤明显的非输入框名称(动词/结构词)"""
    if not name or len(name) < 2 or len(name) > 20:
        return True
    if any(k in name for k in ["按钮", "提交", "保存", "取消", "确认", "关闭",
                                "新建", "编辑", "删除", "功能", "模块", "编号", "返回", "切换"]):
        return True
    return False


def _build_field_item(name, rule_text):
    rules = parse_field_rule(rule_text)
    item = {
        "name": name,
        "required": rules.get("required", False),
        "rules": rule_text,
        "selector": _infer_selector(name, None),
    }
    for k in ["min_len", "max_len", "length", "step", "min_value", "max_value", "pattern"]:
        if rules.get(k) is not None:
            item[k] = rules[k]
    return item


def extract_field_items(sections, text_no_table):
    """从章节表格与描述文本提取输入框字段。
    路径: ① 描述文本/单元格的"字段名（必填/选填，规则）" → ② 字段名/规则列表格 → ③ 旧姓名/身份证/金额正则兜底。"""
    items = []
    seen = set()

    def add(item):
        if item["name"] in seen:
            return
        seen.add(item["name"])
        items.append(item)

    # ① 全文非表格文本 + 表格单元格中的字段定义模式
    haystack = [text_no_table]
    for sec in sections:
        haystack.extend(sec["content"])
        for table in parse_table_blocks(sec["tables"]):
            for row in table[1:]:
                haystack.extend(row)
    for m in FIELD_DEF_RE.finditer("\n".join(haystack)):
        name, rule_text = m.group(1).strip(), m.group(2).strip()
        if _is_non_field_name(name):
            continue
        add(_build_field_item(name, rule_text))

    # ② 表格列角色(字段名/规则列)
    for sec in sections:
        for table in parse_table_blocks(sec["tables"]):
            if not table:
                continue
            header = table[0]
            field_col = rule_col = None
            for i, h in enumerate(header):
                if any(k in h for k in ["名称", "字段", "输入", "参数"]):
                    field_col = i
                if any(k in h for k in ["规则", "校验", "描述", "说明", "约束"]):
                    rule_col = i
            if field_col is None:
                continue
            for row in table[1:]:
                if len(row) <= field_col:
                    continue
                name = row[field_col].strip()
                if not name or _is_non_field_name(name):
                    continue
                rule_text = row[rule_col].strip() if rule_col is not None and rule_col < len(row) else ""
                if not rule_text:
                    rule_text = "必填" if "必填" in row[field_col] else ""
                add(_build_field_item(name, rule_text))

    # ③ 旧格式兜底(姓名/身份证/金额 正则,作用于全文去表格文本)
    for legacy in _legacy_input_regex(text_no_table):
        add(legacy)
    return items


def parse_field_rule(rule_text):
    """从规则文本提取结构化约束,返回 {required, min_len, max_len, length, step, min_value, max_value, pattern}"""
    rules = {}
    rules["required"] = ("必填" in rule_text) and ("选填" not in rule_text)
    m = re.search(r"(\d+)[-~到至](\d+)\s*个?字符", rule_text)
    if m:
        rules["min_len"], rules["max_len"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)\s*位", rule_text)
    if m:
        rules["length"] = int(m.group(1))
    m = re.search(r"(\d+)\s*的倍数", rule_text)
    if m:
        rules["step"] = int(m.group(1))
    m = re.search(r"最低\s*(\d+)", rule_text)
    if m:
        rules["min_value"] = int(m.group(1))
    m = re.search(r"(?:不超过|最大|上限)\s*(\d+)", rule_text)
    if m:
        rules["max_value"] = int(m.group(1))
    pat = _charset_to_pattern(rule_text)
    if pat:
        rules["pattern"] = pat
    return rules


def _charset_to_pattern(rule_text):
    """把"仅允许小写字母开头、字母/数字/连字符"这类描述转成正则模式"""
    if "小写字母开头" in rule_text and "连字符" in rule_text:
        return r"^[a-z][a-z0-9-]*$"
    if "数字" in rule_text and "字母" in rule_text and "下划线" in rule_text:
        return r"^[A-Za-z0-9_]+$"
    if "中文" in rule_text:
        return r"^[一-龥]+$"
    return ""


def _legacy_input_regex(text):
    """旧格式兜底: 姓名/身份证号/金额 的硬编码规则提取"""
    items = []
    input_names_seen = set()
    for line in text.split("\n"):
        name_match = re.search(r"姓名.*?(\d+)[-~到至](\d+).*?字符", line)
        if name_match and "姓名" not in input_names_seen:
            input_names_seen.add("姓名")
            items.append({
                "name": "姓名", "required": True,
                "rules": f"{name_match.group(1)}-{name_match.group(2)}个字符，仅支持中文",
                "selector": "#name-input",
                "min_len": int(name_match.group(1)), "max_len": int(name_match.group(2)),
            })
        id_match = re.search(r"身份证.*?(\d+).*?位", line)
        if id_match and "身份证号" not in input_names_seen:
            input_names_seen.add("身份证号")
            items.append({
                "name": "身份证号", "required": True,
                "rules": f"{id_match.group(1)}位身份证号格式校验",
                "selector": "#idcard-input", "length": int(id_match.group(1)),
            })
        multi_match = re.search(r"(\d+)\s*的倍数", line)
        if multi_match and "金额" not in input_names_seen:
            input_names_seen.add("金额")
            item = {
                "name": "金额", "required": True,
                "rules": f"必须为 {multi_match.group(1)} 的倍数",
                "selector": "#amount-input", "step": int(multi_match.group(1)),
            }
            min_match = re.search(r"最低.*?(\d+)", line)
            if min_match:
                item["min_value"] = int(min_match.group(1))
            items.append(item)
    return items


def extract_buttons(sections):
    """从表格中提取按钮/操作名"""
    buttons = []
    seen = set()
    for sec in sections:
        for table in parse_table_blocks(sec["tables"]):
            for row in table[1:]:
                for cell in row:
                    if any(k in cell for k in ["按钮", "提交", "保存", "确认", "取消"]):
                        name = cell.strip()
                        if 1 < len(name) < 30 and name not in seen:
                            seen.add(name)
                            buttons.append({"name": name, "action": ""})
    return buttons


def extract_api_endpoints(text):
    """提取 /api/ 端点(去重保序)"""
    return list(dict.fromkeys(re.findall(r"/api/[\w/-]+", text)))


def extract_states(lines):
    """检测 MUST/NOT 约束(扩展到 不允许/禁止/不可/不得)"""
    states = []
    for line in lines:
        if "MUST" in line or "必须" in line:
            states.append({"type": "must", "desc": line.strip()})
        if any(k in line for k in ["NOT", "不应", "禁止", "不允许", "不可", "不得"]):
            states.append({"type": "not", "desc": line.strip()})
    return states


def extract_forbidden_text(desc):
    """从 NOT/不应/禁止 约束行抽取禁止出现的短语。优先引号内容(含「」『』),否则取约束词后 12 字。"""
    desc = desc or ""
    m = re.search(r"[“\"'（(「『]([^”\"')）」』]{1,30})[”\"')）」』]", desc)
    if m:
        return m.group(1)
    m = re.search(r"(?:不应|禁止|不能|不可|不允许|不得)\s*([^\s，。;；,]{2,12})", desc)
    if m:
        return m.group(1)
    return ""


def _boundary_ids(inp):
    """为单个输入框分配唯一的边界用例 (suffix, name, expected_state),suffix 顺序递增避免 ID 冲突。"""
    ids = []

    def add(name, expected):
        suffix = chr(ord("a") + len(ids))
        ids.append((suffix, name, expected))

    add("空值校验", "disabled")
    if inp.get("min_len") and inp.get("max_len"):
        add(f"{inp['min_len']-1}个字符(低于下限)", "disabled")
        add(f"{inp['min_len']}个字符(合法)", "enabled")
        add(f"{inp['max_len']}个字符(合法)", "enabled")
        add(f"{inp['max_len']+1}个字符(高于上限)", "disabled")
    elif inp.get("length"):
        add(f"{inp['length']-1}位(低于下限)", "disabled")
        add(f"{inp['length']}位(合法)", "enabled")
        add(f"{inp['length']+1}位(高于上限)", "disabled")
    if inp.get("min_value"):
        add(f"{inp['min_value']-1}(低于最低值)", "disabled")
        add(f"{inp['min_value']}(合法最低值)", "enabled")
    if inp.get("step"):
        add(f"非{inp['step']}倍数", "disabled")
        add(f"{inp['step']}(合法倍数)", "enabled")
    return ids


def _boundary_value(inp, case_name):
    """根据边界用例名生成填充值"""
    if "空值" in case_name:
        return ""
    m = re.match(r"(\d+)个字符", case_name)
    if m:
        return "a" * int(m.group(1))
    m = re.match(r"(\d+)位", case_name)
    if m:
        return "1" * int(m.group(1))
    if case_name.startswith("非"):
        return str(inp.get("step", 100) - 1)
    m = re.match(r"(\d+)", case_name)
    if m:
        return m.group(1)
    return ""


def _infer_selector(name: str, idx=None) -> str:
    """根据字段名推断选择器。永不输出 #中文 非法选择器。
    优先级: 已知映射 → ASCII slug → 兜底 #field-{idx}(打印警告需人工确认)"""
    name_map = {
        "姓名": "#name-input",
        "身份证号": "#idcard-input",
        "手机号": "#phone-input",
        "金额": "#amount-input",
        "验证码": "#code-input",
        "银行卡号": "#bankcard-input",
        "开户行": "#bankname-input",
    }
    for key, sel in name_map.items():
        if key in name:
            return sel
    # ASCII/英文 slug
    slug = re.sub(r"[^a-zA-Z0-9_]", "", name)
    if slug:
        return f"#{slug}"
    if idx is not None:
        print(f"  [WARN] 字段「{name}」无法推断选择器,使用 #field-{idx},请人工确认")
        return f"#field-{idx}"
    return "#input"


def generate_test_script(req: dict) -> str:
    """根据解析结果生成 YAML 测试脚本"""
    req_id = req.get("id", "REQ-XXX")
    title = req.get("title", "未命名需求")
    file_name = req.get("file", "").replace(".md", "")

    yaml_lines = [
        f"# 测试脚本 — {title}",
        f"# 需求: {req_id}",
        f"# 自动生成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "metadata:",
        f"  id: SCRIPT-{req_id}",
        f"  name: {title}",
        f"  req: {req_id}",
        "  version: 1.0",
        "",
        "params:",
        "  base_url: http://目标地址",
        f'  api_base: "http://api.目标地址"',
        "",
    ]

    # data_setup: API 数据构造
    if req["api_endpoints"]:
        yaml_lines.extend([
            "data_setup:",
            "  - id: SETUP-001",
            "    name: 准备测试数据",
            "    type: api_call",
            f'    request:',
            "      method: GET",
            f'      url: "{req["api_endpoints"][0]}"',
            "    verify:",
            "      - path: code",
            "        expect: 0",
            "",
        ])

    # steps: 功能验证
    yaml_lines.extend([
        "steps:",
        "  # ── 导航 ──",
        "  - id: NAV-001",
        "    name: 打开页面",
        "    actions:",
        "      - type: navigate",
        '        url: "{base_url}"',
    ])
    if req["api_endpoints"]:
        yaml_lines.extend([
            "    api_check:",
            f"      - url: {req['api_endpoints'][0]}",
            "        method: GET",
            "        expected_code: 200",
        ])

    # 为每个输入框生成边界值测试(唯一 suffix,避免 ID 冲突)
    for idx, inp in enumerate(req["inputs"]):
        name = inp["name"]
        selector = inp.get("selector") or "#input"
        if selector in ("#input",) or selector.startswith("#field-") or (len(selector) == 1):
            selector = _infer_selector(name, idx + 1)
            inp["selector"] = selector
        rules = inp.get("rules", "")

        for suffix, case_name, expected in _boundary_ids(inp):
            value = _boundary_value(inp, case_name)
            yaml_lines.extend([
                "",
                f"  # ── {name} — {case_name} ──",
                f"  - id: BOUNDARY-{idx+1:03d}-{suffix}",
                f"    name: {name} — {case_name}",
                "    actions:",
                f'      - type: fill',
                f'        target: "{selector}"',
                f'        value: "{value}"',
                "      - type: wait",
                "        ms: 300",
                "    verify:",
                "      - element: 提交按钮",
                f"        should_be: {expected}",
            ])

    # MUST/NOT 验证(负面约束: 提取禁止文本,不生成空括号死代码)
    not_count = 0
    for st in req["states"]:
        if st["type"] == "not":
            not_count += 1
            forbidden = extract_forbidden_text(st["desc"])
            yaml_lines.extend([
                "",
                f"  - id: NEGATIVE-{not_count:03d}",
                f'    name: "负面约束 — {st["desc"][:40]}"',
            ])
            if forbidden:
                yaml_lines.extend([
                    "    actions:",
                    "      - type: evaluate",
                    "        code: |",
                    f"          return {{ checked: !document.body.innerText.includes({json.dumps(forbidden, ensure_ascii=False)}) }};",
                    "    verify:",
                    "      - path: checked",
                    "        expect: true",
                ])
            else:
                yaml_lines.extend([
                    "    actions: []",
                    "    condition: false  # 未从约束中提取到禁止文本,需人工补断言",
                ])

    # 结尾
    yaml_lines.extend([
        "",
        "  # ── 关闭 ──",
        "  - id: CLOSE-001",
        "    name: 关闭页面",
        "    actions:",
        "      - type: wait",
        "        ms: 1000",
    ])

    return "\n".join(yaml_lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="YAML 测试脚本自动生成器")
    parser.add_argument("input", help="需求文档路径 (docs/xxx.md)")
    parser.add_argument("--output", help="输出路径 (默认 scripts/xxx.yaml)")
    parser.add_argument("--run", action="store_true", help="生成后直接执行")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[错误] 未找到需求文档: {input_path}")
        sys.exit(1)

    print(f"📄 读取需求文档: {input_path.name}")
    req = parse_requirement(input_path)

    print(f"  需求编号: {req.get('id', 'N/A')}")
    print(f"  识别输入框: {len(req['inputs'])} 个")
    for inp in req["inputs"]:
        print(f"    - {inp['name']}: {inp.get('rules', '')}")
    print(f"  识别按钮: {len(req['buttons'])} 个")
    print(f"  识别 MUST/NOT: {len(req['states'])} 条")
    print(f"  识别 API: {len(req['api_endpoints'])} 个")

    # 生成 YAML
    yaml_content = generate_test_script(req)

    # 输出
    if args.output:
        output_path = Path(args.output)
    else:
        stem = input_path.stem.replace(" ", "_")[:30]
        output_path = Path("scripts") / f"{stem}.yaml"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml_content, encoding="utf-8")
    print(f"\n✅ 脚本已生成: {output_path}")

    # 生成后直接执行
    if args.run:
        print(f"\n🚀 执行测试脚本...")
        import subprocess
        subprocess.run([sys.executable, "script_runner.py", str(output_path)])


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    main()
