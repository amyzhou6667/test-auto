# -*- coding: utf-8 -*-
r"""报告生成：保存 results JSON + 渲染 Markdown。

从 execute_test_cases.py 的 save_report/build_markdown 抽取，通用化 + 修复：
  - 标题/地址/页脚/文件名全部来自项目配置（不再写死 CoreBridge）
  - build_markdown 单元格转义 ``|``→``\|``、换行→空格（修表格撑破 bug）
  - 统计口径来自 cfg.status.stats（「待补充」等扩展状态可配置是否计入）
"""
import json
import os
from datetime import datetime
from pathlib import Path


def _unique_path(path):
    """目标已存在则追加 _2/_3… 后缀，避免同秒运行互相覆盖。

    后缀在按名排序中仍排在原文件之后（'.' < '_'），不破坏"字典序=时间序"。
    """
    if not path.exists():
        return path
    for i in range(2, 1000):
        cand = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not cand.exists():
            return cand
    return path


def save_report(runner, cfg, modules=None):
    """把 runner.results 落盘为 results_{ts}.json + report_{ts}.md。

    应在调度层 try/finally 内调用（修 bug6：异常也保报告）。
    modules: 本次执行的模块名列表，写入 results JSON 的 meta（供 consolidate 精确匹配）。
    """
    result_dir = cfg.resolve_path("results")
    result_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    data = [r.to_dict() for r in runner.results.values()]
    payload = {
        "meta": {
            "modules": list(modules) if modules else [],
            "project": cfg.project.get("name", ""),
            "ts": ts,
        },
        "results": data,
    }
    jpath = _unique_path(result_dir / f"results_{ts}.json")
    jpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = build_markdown(data, cfg, report_dir=result_dir)
    mpath = _unique_path(result_dir / f"report_{ts}.md")
    mpath.write_text(md, encoding="utf-8")
    print(f"\n  📄 报告已保存: {mpath}")
    print(f"  📄 明细已保存: {jpath}")
    # 汇总（统计口径从配置读，支持扩展状态）
    stats = cfg.status_stats() or ["通过", "失败", "无法验证"]
    parts = " | ".join(f"{s} {_count(data, s)}" for s in stats)
    print(f"\n{'='*66}")
    print(f"  汇总: 总计 {len(data)} | {parts}")
    print(f"{'='*66}")
    return jpath, mpath


def build_markdown(data, cfg, report_dir=None):
    """渲染单次运行 Markdown 报告。标题/地址/页脚来自项目配置。

    report_dir: 报告落盘目录；提供时 evidence 输出相对路径（便于报告整体移动/分享）。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_cfg = cfg.report or {}
    stats = cfg.status_stats() or ["通过", "失败", "无法验证"]
    icons = cfg.status_icons()
    parts = " | ".join(f"**{s}:** {_count(data, s)}" for s in stats)
    lines = [
        f"# {report_cfg.get('title', '测试报告')}",
        "",
        f"**时间:** {now}",
        f"**地址:** {_fmt(report_cfg.get('address', cfg.base_url or ''))}",
        f"**总计:** {len(data)} | {parts}",
        "",
        f"## 逐条结果",
        "",
        f"| 用例 | 名称 | 结果 | 实际 | 说明 | 证据 |",
        f"|------|------|------|------|------|------|",
    ]
    for r in data:
        icon = icons.get(r["status"], "❓")
        # evidence: 提供 report_dir 时取相对路径(与汇总报告/管线1截图一致), 否则 basename
        ev = f"`{evidence_ref(r.get('evidence'), report_dir)}`" if r.get("evidence") else ""
        # 单元格转义: | → \| , 换行 → 空格（修表格撑破）
        act = escape_cell(r.get("actual", ""))
        det = escape_cell(r.get("detail", ""))
        nm = escape_cell(r.get("name", ""))
        lines.append(f"| {r['id']} | {nm} | {icon} {r['status']} | {act} | {det} | {ev} |")
    footer = (report_cfg.get("footer") or "由引擎自动生成 | {now}").format(now=now)
    lines.extend(["", "---", f"*{footer}*", ""])
    return "\n".join(lines)


def _count(data, status):
    return sum(1 for r in data if r["status"] == status)


def escape_cell(text):
    r"""Markdown 表格单元格转义：| → \| ，换行 → 空格（单次与汇总报告统一使用）。"""
    return (text or "").replace("|", "\\|").replace("\n", " ")


def evidence_ref(path, report_dir=None):
    """证据引用：报告目录已知时输出相对路径（便于报告整体移动），否则取 basename。

    单次/汇总报告统一使用；管线1截图走相对路径，管线2 evidence 也一致化。
    """
    if not path:
        return ""
    try:
        if report_dir is not None:
            rel = os.path.relpath(str(path), str(report_dir))
            return rel.replace("\\", "/")
    except (OSError, ValueError):
        pass
    return Path(path).name


def _fmt(text):
    return text if text else "N/A"
