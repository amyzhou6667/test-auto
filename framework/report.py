# -*- coding: utf-8 -*-
r"""报告生成：保存 results JSON + 渲染 Markdown。

从 execute_test_cases.py 的 save_report/build_markdown 抽取，通用化 + 修复：
  - 标题/地址/页脚/文件名全部来自项目配置（不再写死 CoreBridge）
  - build_markdown 单元格转义 ``|``→``\|``、换行→空格（修表格撑破 bug）
  - 统计口径来自 cfg.status.stats（「待补充」等扩展状态可配置是否计入）
"""
import json
from datetime import datetime
from pathlib import Path


def save_report(runner, cfg):
    """把 runner.results 落盘为 results_{ts}.json + report_{ts}.md。

    应在调度层 try/finally 内调用（修 bug6：异常也保报告）。
    """
    result_dir = cfg.resolve_path("results")
    result_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    data = [r.to_dict() for r in runner.results.values()]
    jpath = result_dir / f"results_{ts}.json"
    jpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    md = build_markdown(data, cfg)
    mpath = result_dir / f"report_{ts}.md"
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


def build_markdown(data, cfg):
    """渲染单次运行 Markdown 报告。标题/地址/页脚来自项目配置。"""
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
        # evidence 与汇总报告一致取 basename（绝对路径仅用于落盘诊断）
        ev = f"`{Path(r['evidence']).name}`" if r.get("evidence") else ""
        # 单元格转义: | → \| , 换行 → 空格（修表格撑破）
        act = _escape_cell(r.get("actual", ""))
        det = _escape_cell(r.get("detail", ""))
        nm = _escape_cell(r.get("name", ""))
        lines.append(f"| {r['id']} | {nm} | {icon} {r['status']} | {act} | {det} | {ev} |")
    footer = (report_cfg.get("footer") or "由引擎自动生成 | {now}").format(now=now)
    lines.extend(["", "---", f"*{footer}*", ""])
    return "\n".join(lines)


def _count(data, status):
    return sum(1 for r in data if r["status"] == status)


def _escape_cell(text):
    return (text or "").replace("|", "\\|").replace("\n", " ")


def _fmt(text):
    return text if text else "N/A"
