# -*- coding: utf-8 -*-
"""
汇总报告：合并各模块权威运行结果为一份最终测试报告。

算法骨架来自 consolidate_report.py（find_base/find_supp/merge/override/渲染），
全部写死配置（BASE/SUPPLEMENTS/BAD_RUNS/OVERRIDES/DOC_ORDER/EXCLUDE/标题/地址/结论/文件名）
改为从项目配置读取。

关键顺序约束（保持与原实现一致）：
  - SUPPLEMENTS 列表顺序即覆盖优先级（后者覆盖前者）；FILEDL2 在前、FILEDL 在后
    （find_supp 精确相等匹配 + consumed 集合独占，保证 FILEDL 不会抢到 FILEDL2 的文件）
"""
from datetime import datetime
from pathlib import Path

from framework.report import _unique_path, escape_cell, evidence_ref


def load(path):
    """读取 results JSON，返回 (meta, rows)。

    新格式 {meta, results} 取 meta 与结果列表；老格式（裸 list）兼容，meta 记为空 dict。
    """
    import json
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict) and "results" in data:
        return data.get("meta") or {}, data["results"]
    return {}, data


def result_files(results_dir):
    files = list(Path(results_dir).glob("results_*.json"))
    files.sort(key=lambda p: p.name)  # 文件名含时间戳, 字典序 = 时间序(旧→新)
    return files


def find_base(first_id, files, bad_runs, module=None):
    """取 base 模块的最新一次运行(全量运行)。

    有 module 且文件 meta 含 modules 时按模块名精确匹配（消除首条 id 前缀误判）；
    否则回退首条用例 id 以 first_id 开头的旧逻辑（兼容老格式文件）。
    """
    for p in reversed(files):
        if p.name in bad_runs:
            continue
        try:
            meta, rows = load(p)
        except Exception:
            continue
        if module and meta.get("modules"):
            if module in meta["modules"]:
                return p, rows
            continue
        if rows and rows[0].get("id", "").startswith(first_id):
            return p, rows
    return None, None


def find_supp(anchors, files, bad_runs, consumed):
    """从最新到最旧找包含任一锚定用例 id「真实结果」且未被占用的运行。

    anchors 匹配是精确相等（非 prefix），consumed 集合独占文件——
    这是 FILEDL2 在前 FILEDL 在后约束的机制保证。
    """
    for p in reversed(files):
        if p.name in bad_runs or p in consumed:
            continue
        try:
            _, rows = load(p)
        except Exception:
            continue
        if any(r.get("status") not in ("待补充", "") and
               r.get("id") in anchors
               for r in rows):
            return p, rows
    return None, None


def render_report(cfg, results_dir=None, print_summary=True):
    """执行合并并生成汇总 Markdown，写盘到 cfg.paths.reports。

    返回 (out_path, resolved, merged)。resolved 供解析摘要；merged 供测试断言。
    """
    results_dir = results_dir or cfg.resolve_path("results")
    files = result_files(results_dir)
    if not files:
        raise FileNotFoundError(
            f"{results_dir}/ 下没有 results_*.json, 请先运行 run_project.py")

    consolidate_cfg = cfg.consolidate or {}
    report_cfg = cfg.report or {}
    base = consolidate_cfg.get("base") or []
    supplements = consolidate_cfg.get("supplements") or []
    bad_runs = set(report_cfg.get("bad_runs") or [])
    overrides = report_cfg.get("overrides") or {}
    doc_order = list(report_cfg.get("doc_order") or [])
    exclude = set(report_cfg.get("exclude") or [])
    conclusion = report_cfg.get("conclusion") or ""
    stats = cfg.status_stats() or ["通过", "失败", "无法验证"]
    icons = cfg.status_icons()

    merged = {}
    consumed = set()
    resolved = []

    # 1) 基础模块: 最新一次全量运行
    for item in base:
        module = item["module"]
        first_id = item["first_id"]
        path, data = find_base(first_id, files, bad_runs, module=module)
        if not path:
            print(f"[警告] 未找到 {module} 的全量运行(首条 id 以 {first_id} 开头)")
            continue
        consumed.add(path)
        n = 0
        for r in data:
            if r["id"] in exclude:
                continue
            merged[r["id"]] = r
            n += 1
        resolved.append((module, "基础", path.name, n))

    # 2) 补充模块: 覆盖同 id 的基础结果(列表顺序即覆盖优先级)
    for item in supplements:
        module = item["module"]
        anchors = list(item["anchors"])
        path, data = find_supp(anchors, files, bad_runs, consumed)
        if not path:
            print(f"[警告] 未找到 {module} 的补跑结果")
            continue
        consumed.add(path)
        n = 0
        for r in data:
            if r.get("status") == "待补充" or r["id"] in exclude:
                continue  # 占位, 跳过
            merged[r["id"]] = r
            n += 1
        resolved.append((module, "补充", path.name, n))

    # 3) 后处理覆盖
    for cid, patch in overrides.items():
        if cid in merged:
            merged[cid].update(patch)

    # 按文档顺序输出
    rows = [merged[cid] for cid in doc_order if cid in merged]
    # 追加不在文档顺序中的补充用例(如 TC-UIOP-03b)
    extra = [r for r in merged.values() if r["id"] not in doc_order and r["status"] != "待补充"]
    rows += extra

    counts = {s: sum(1 for r in rows if r["status"] == s) for s in stats}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out_dir = cfg.resolve_path("reports")  # 提前定义，供 evidence 相对路径使用

    lines = [
        f"# {report_cfg.get('title', '测试报告(汇总)')}",
        "",
        f"**时间:** {now}",
        f"**地址:** {report_cfg.get('address', cfg.base_url or 'N/A')}",
        f"**执行方式:** {report_cfg.get('exec_method', 'Playwright 自动化(Chromium) + 网络/API 捕获 + 失败截图')}",
        "",
        f"**总计:** {len(rows)} | " + " | ".join(f"**{s}:** {counts[s]}" for s in stats),
        "",
    ]
    if conclusion:
        ctitle = report_cfg.get("conclusion_title") or "结论说明"
        if ctitle != "结论说明":
            ctitle = f"结论说明({ctitle})"
        lines.extend(["", f"## {ctitle}", "", f"> {conclusion}", ""])
    lines.extend([
        f"| 用例 | 名称 | 结果 | 实际 | 说明 | 证据 |",
        f"|------|------|------|------|------|------|",
    ])
    for r in rows:
        icon = icons.get(r["status"], "❓")
        ev = f"`{evidence_ref(r.get('evidence'), out_dir)}`" if r.get("evidence") else ""
        act = escape_cell(r.get("actual"))
        det = escape_cell(r.get("detail"))
        nm = escape_cell(r.get("name"))
        lines.append(f"| {r['id']} | {nm} | {icon} {r['status']} | {act} | {det} | {ev} |")

    lines.append("")
    lines.append("## ❌ 失败用例")
    lines.append("")
    for r in rows:
        if r["status"] == "失败":
            lines.append(f"- **{r['id']}** {r['name']} — {r.get('actual')}")
    lines.append("")
    lines.append("## ⚠️ 无法验证用例(原因)")
    lines.append("")
    for r in rows:
        if r["status"] == "无法验证":
            lines.append(f"- **{r['id']}** {r['name']}: {r.get('actual')}")
    lines.append("")
    lines.append("---")
    lines.append(f"*{report_cfg.get('footer', '由引擎各模块独立运行合并 | {now}').format(now=now)}*")
    lines.append("")

    md = "\n".join(lines)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = (report_cfg.get("output_name") or "测试报告汇总_{ts}.md")
    out = _unique_path(out_dir / out_name.format(ts=datetime.now().strftime("%Y%m%d_%H%M%S")))
    out.write_text(md, encoding="utf-8")
    if print_summary:
        print(md)
        print(f"\n[已保存] {out}")

        print("\n== 结果文件解析(自动发现) ==")
        for module, kind, fname, n in resolved:
            print(f"  [{kind}] {module:9s} <- {fname} ({n} 条)")
        unused = [p.name for p in files if p not in consumed]
        if unused:
            print("  未使用(被更新的运行覆盖 / 异常运行 / 占位):")
            for fname in unused:
                print(f"    - {fname}")
    return out, resolved, merged
