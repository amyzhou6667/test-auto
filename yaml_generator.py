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
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def parse_requirement(file_path: Path) -> dict:
    """解析需求文档，提取结构化信息"""
    text = file_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    req = {
        "file": file_path.name,
        "title": "",
        "id": "",
        "inputs": [],
        "buttons": [],
        "api_endpoints": [],
        "states": [],
        "sections": {},
        "flow": [],
    }

    current_section = ""
    current_subsection = ""
    seen_buttons = set()

    for line in lines:
        # 提取需求编号和标题
        h1_match = re.match(r"^#\s+(.+)", line)
        if h1_match:
            req["title"] = h1_match.group(1).strip()
            id_match = re.search(r"(REQ-\d+)", line)
            if id_match:
                req["id"] = id_match.group(1)

        # 提取文档信息表格中的需求编号
        table_match = re.match(r"\|.*\|.*\|", line)
        if table_match and "需求编号" in line:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 2:
                id_in_cell = re.search(r"REQ-?\d+", cells[1])
                if id_in_cell:
                    req["id"] = id_in_cell.group(0)

        # 提取章节
        h2_match = re.match(r"^##\s+(.+)", line)
        if h2_match:
            current_section = h2_match.group(1).strip()
            req["sections"][current_section] = {"subsections": [], "content": []}
            current_subsection = ""

        h3_match = re.match(r"^###\s+(.+)", line)
        if h3_match:
            current_subsection = h3_match.group(1).strip()
            if current_section:
                req["sections"][current_section].setdefault("subsections", []).append(current_subsection)
            req["sections"][current_section].setdefault("content", []).append(line)

        # 提取表格（输入框定义通常在表格中）
        if "|" in line and line.strip().startswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]

            # 检测输入框定义行
            if any(kw in line for kw in ["输入框", "输入", "填写"]) and len(cells) >= 3:
                input_def = {
                    "name": cells[0] if len(cells) > 0 else "",
                    "required": "必填" in line,
                    "rules": cells[1] if len(cells) > 1 else "",
                    "description": cells[2] if len(cells) > 2 else "",
                    "selector": _infer_selector(cells[0]),
                }
                req["inputs"].append(input_def)

            # 检测按钮定义
            if any(kw in line for kw in ["按钮", "提交", "保存", "确认", "取消"]):
                cell0 = cells[0] if len(cells) > 0 else ""
                if len(cell0) > 1 and len(cell0) < 30 and cell0 not in seen_buttons:
                    seen_buttons.add(cell0)
                    req["buttons"].append({
                        "name": cell0,
                        "action": cells[1] if len(cells) > 1 else "",
                    })

    # 提取输入校验规则（从段落文本中）
    text_no_table = re.sub(r"\|[^\n]*\|", "", text)
    input_names_seen = set()
    seen_buttons = set()
    for line in text_no_table.split("\n"):
        # 姓名规则
        name_match = re.search(r"姓名.*?(\d+)[-~到至](\d+).*?字符", line)
        if name_match and "姓名" not in input_names_seen:
            input_names_seen.add("姓名")
            req["inputs"].append({
                "name": "姓名",
                "required": True,
                "rules": f"{name_match.group(1)}-{name_match.group(2)}个字符，仅支持中文",
                "selector": "#name-input",
                "min_len": int(name_match.group(1)),
                "max_len": int(name_match.group(2)),
            })

        # 身份证号规则
        id_match = re.search(r"身份证.*?(\d+).*?位", line)
        if id_match and "身份证号" not in input_names_seen:
            input_names_seen.add("身份证号")
            req["inputs"].append({
                "name": "身份证号",
                "required": True,
                "rules": f"{id_match.group(1)}位身份证号格式校验",
                "selector": "#idcard-input",
                "length": int(id_match.group(1)),
            })

        # 金额规则（倍数）
        multi_match = re.search(r"(\d+)\s*的倍数", line)
        if multi_match and "金额" not in input_names_seen:
            input_names_seen.add("金额")
            req["inputs"].append({
                "name": "金额",
                "required": True,
                "rules": f"必须为 {multi_match.group(1)} 的倍数",
                "selector": "#amount-input",
                "step": int(multi_match.group(1)),
            })
            # 金额最小值
            min_match = re.search(r"最低.*?(\d+)", line)
            if min_match:
                req["inputs"][-1]["min_value"] = int(min_match.group(1))

    # 检测 MUST/NOT 约束
    for line in text_no_table.split("\n"):
        if "MUST" in line or "必须" in line:
            req["states"].append({"type": "must", "desc": line.strip()})
        if "NOT" in line or "不应" in line:
            req["states"].append({"type": "not", "desc": line.strip()})

    # 检测 API 端点
    for line in text_no_table.split("\n"):
        api_match = re.search(r"/api/[\w/-]+", line)
        if api_match:
            req["api_endpoints"].append(api_match.group(0))

    return req


def _infer_selector(name: str) -> str:
    """根据字段名推断选择器"""
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
    # 拼音/英文
    pinyin = "#" + re.sub(r'[^\w]', '', name)
    return pinyin


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

    # 为每个输入框生成边界值测试
    for idx, inp in enumerate(req["inputs"]):
        name = inp["name"]
        selector = inp.get("selector", "#input")
        rules = inp.get("rules", "")

        yaml_lines.extend([
            "",
            f"  # ── {name} 输入校验 ──",
            f"  - id: BOUNDARY-{idx+1:03d}",
            f"    name: {name} — 空值校验",
            "    actions:",
            f'      - type: fill',
            f'        target: "{selector}"',
            '        value: ""',
            "      - type: wait",
            "        ms: 300",
            "    verify:",
            "      - element: 提交按钮",
            "        should_be: disabled",
        ])

        # 如果有长度限制，生成边界值
        min_len = inp.get("min_len")
        max_len = inp.get("max_len")
        length = inp.get("length")
        step = inp.get("step")
        min_val = inp.get("min_value")

        if min_len and max_len:
            yaml_lines.extend([
                "",
                f"  - id: BOUNDARY-{idx+1:03d}a",
                f"    name: {name} — {min_len-1}个字符（低于下限）",
                "    actions:",
                f'      - type: fill',
                f'        target: "{selector}"',
                f'        value: {"a" * (min_len - 1)}',
                "    verify:",
                "      - element: 提交按钮",
                "        should_be: disabled",
                "",
                f"  - id: BOUNDARY-{idx+1:03d}b",
                f"    name: {name} — {min_len}个字符（合法）",
                "    actions:",
                f'      - type: fill',
                f'        target: "{selector}"',
                f'        value: {"a" * min_len}',
                "    verify:",
                "      - element: 提交按钮",
                "        should_be: enabled",
            ])

        if length:
            yaml_lines.extend([
                "",
                f"  - id: BOUNDARY-{idx+1:03d}a",
                f"    name: {name} — {length-1}位（低于下限）",
                "    actions:",
                f'      - type: fill',
                f'        target: "{selector}"',
                f'        value: {"1" * (length - 1)}',
                "    verify:",
                "      - element: 提交按钮",
                "        should_be: disabled",
                "",
                f"  - id: BOUNDARY-{idx+1:03d}b",
                f"    name: {name} — {length}位（合法）",
                "    actions:",
                f'      - type: fill',
                f'        target: "{selector}"',
                f'        value: {"1" * length}',
                "    verify:",
                "      - element: 提交按钮",
                "        should_be: enabled",
            ])

        if step:
            yaml_lines.extend([
                "",
                f"  - id: BOUNDARY-{idx+1:03d}a",
                f"    name: {name} — {step-1}（非{step}倍数）",
                "    actions:",
                f'      - type: fill',
                f'        target: "{selector}"',
                f'        value: "{step - 1}"',
                "      - type: wait",
                "        ms: 300",
                "    verify:",
                "      - element: 错误提示",
                f'        text_contains: "必须为 {step} 的倍数"',
                "        optional: true",
                "",
                f"  - id: BOUNDARY-{idx+1:03d}b",
                f"    name: {name} — {step}（合法）",
                "    actions:",
                f'      - type: fill',
                f'        target: "{selector}"',
                f'        value: "{step}"',
                "      - type: wait",
                "        ms: 300",
                "    verify:",
                "      - element: 提交按钮",
                "        should_be: enabled",
            ])

    # MUST/NOT 验证
    not_count = 0
    for st in req["states"]:
        if st["type"] == "not":
            not_count += 1
            yaml_lines.extend([
                "",
                f"  - id: NEGATIVE-{not_count:03d}",
                f'    name: "负面约束 — {st["desc"][:40]}"',
                "    actions:",
                "      - type: evaluate",
                "        code: |",
                f'          return {{ checked: document.body.innerText.includes() }};',
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
    main()
