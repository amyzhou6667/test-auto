# -*- coding: utf-8 -*-
"""framework.consolidate 单测：find_base 排 BAD_RUNS、find_supp 精确相等 + consumed 独占、
FILEDL2 在前 FILEDL 不抢、OVERRIDES/EXCLUDE/DOC_ORDER 排序。"""
import json

from framework.config import ProjectConfig
from framework.consolidate import (find_base, find_supp, result_files,
                                   render_report)


def _write_json(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


def _cfg(tmp_path, **overrides):
    raw = {
        "project": {"name": "t"},
        "paths": {"results": "out/results", "reports": "out/reports"},
        "status": {"icons": {"通过": "✅", "失败": "❌", "无法验证": "⚠️"},
                   "stats": ["通过", "失败", "无法验证"]},
        "consolidate": {"base": [], "supplements": []},
        "report": {"title": "T", "address": "http://x", "doc_order": [],
                   "bad_runs": [], "overrides": {}, "exclude": [],
                   "output_name": "t_{ts}.md", "footer": "f {now}"},
    }
    raw.update(overrides)
    return ProjectConfig(raw, tmp_path)


# ─────────── find_base / find_supp ───────────
def test_find_base_skips_bad_runs(tmp_path):
    bad = tmp_path / "results_20260101_000000.json"
    good = tmp_path / "results_20260102_000000.json"
    _write_json(bad, [{"id": "TC-I-01", "status": "失败", "name": "", "actual": "",
                       "detail": "", "evidence": ""}])
    _write_json(good, [{"id": "TC-I-01", "status": "通过", "name": "", "actual": "",
                        "detail": "", "evidence": ""}])
    files = result_files(tmp_path)
    path, data = find_base("TC-I-01", files, {"results_20260101_000000.json"})
    assert path.name == "results_20260102_000000.json"
    assert data[0]["status"] == "通过"


def test_find_supp_exact_anchor_and_skips_waiting(tmp_path):
    # 含「待补充」占位的不算真实结果 → 被跳过
    wait = tmp_path / "results_20260101_000000.json"
    real = tmp_path / "results_20260102_000000.json"
    _write_json(wait, [{"id": "TC-B-04", "status": "待补充", "name": "", "actual": "",
                        "detail": "", "evidence": ""}])
    _write_json(real, [{"id": "TC-B-04", "status": "通过", "name": "", "actual": "",
                        "detail": "", "evidence": ""}])
    files = result_files(tmp_path)
    path, data = find_supp(["TC-B-04"], files, set(), set())
    assert path.name == "results_20260102_000000.json"


def test_find_supp_consumed_file_not_reused(tmp_path):
    f1 = tmp_path / "results_20260101_000000.json"
    f2 = tmp_path / "results_20260102_000000.json"
    # 两个文件都含 FILEDL2（同一次全量运行既有 FILEDL2 又可能被误判为 FILEDL）
    for f, sid in ((f1, "FILEDL2"), (f2, "FILEDL2")):
        _write_json(f, [{"id": sid, "status": "通过", "name": "", "actual": "",
                         "detail": "", "evidence": ""}])
    files = result_files(tmp_path)
    # FILEDL 锚点精确匹配 "FILEDL"，不会命中 id="FILEDL2" 的记录
    path, data = find_supp(["FILEDL"], files, set(), set())
    assert path is None or not any(r["id"] == "FILEDL2" for r in data)
    # 且即使两个文件都被 FILEDL2 占用（consumed），FILEDL 也找不到可用文件（不误抢）
    consumed = set(files)
    path, data = find_supp(["FILEDL"], files, set(), consumed)
    assert path is None


# ─────────── render_report 全流程 ───────────
def _make_render_files(tmp_path):
    """构造: 全量运行(TC-I-01 开头) + 补跑(TC-B-04 锚定) + FILEDL 单独文件。"""
    base = tmp_path / "out" / "results" / "results_20260101_000000.json"
    supp = tmp_path / "out" / "results" / "results_20260102_000000.json"
    filedl = tmp_path / "out" / "results" / "results_20260103_000000.json"
    _write_json(base, [
        {"id": "TC-I-01", "name": "n1", "status": "通过", "actual": "a",
         "detail": "d", "evidence": ""},
        {"id": "TC-I-02", "name": "n2", "status": "通过", "actual": "a",
         "detail": "d", "evidence": ""},
        {"id": "TC-ISO-04", "name": "删除项", "status": "通过", "actual": "a",
         "detail": "d", "evidence": ""},   # 应在 EXCLUDE 中被过滤
    ])
    _write_json(supp, [
        {"id": "TC-B-04", "name": "n3", "status": "失败", "actual": "bad",
         "detail": "d", "evidence": ""},
    ])
    _write_json(filedl, [
        {"id": "FILEDL", "name": "n4", "status": "通过", "actual": "ok",
         "detail": "d", "evidence": ""},
    ])
    return base, supp, filedl


def test_render_report_merge_override_exclude_doc_order(tmp_path):
    base, supp, filedl = _make_render_files(tmp_path)
    cfg = _cfg(tmp_path, **{
        "consolidate": {
            "base": [{"module": "TC-I", "first_id": "TC-I-01"}],
            "supplements": [
                {"module": "TC-SUPP", "anchors": ["TC-B-04"]},
                {"module": "FILEDL", "anchors": ["FILEDL"]},
            ],
        },
        "report": {
            "title": "T", "address": "http://x",
            "doc_order": ["TC-I-01", "TC-B-04", "TC-I-02"],
            "bad_runs": [], "overrides": {"TC-B-04": {"status": "无法验证"}},
            "exclude": ["TC-ISO-04"],
            "output_name": "t_{ts}.md", "footer": "f {now}",
        },
    })
    out, resolved, merged = render_report(cfg, print_summary=False)
    assert out.exists()
    # EXCLUDE 过滤: TC-ISO-04 不在合并结果
    assert "TC-ISO-04" not in merged
    # 基础结果: TC-I-01/02 在
    assert merged["TC-I-01"]["status"] == "通过"
    # 补充覆盖 + OVERRIDES 后处理: TC-B-04 被补跑覆盖为 失败, 再被 OVERRIDES 覆盖为 无法验证
    assert merged["TC-B-04"]["status"] == "无法验证"
    # DOC_ORDER 顺序: TC-I-01 在前
    md = out.read_text(encoding="utf-8")
    assert md.index("TC-I-01") < md.index("TC-B-04")


def test_render_report_filedl2_before_filedl_priority(tmp_path):
    """FILEDL2 在前 FILEDL 在后: FILEDL 不会抢 FILEDL2 的文件，且 FILEDL2 记录被保留。"""
    d = tmp_path / "out" / "results"
    _write_json(d / "results_20260101_000000.json",
                [{"id": "FILEDL", "name": "f", "status": "通过", "actual": "ok",
                  "detail": "", "evidence": ""}])
    _write_json(d / "results_20260102_000000.json",
                [{"id": "FILEDL2", "name": "f2", "status": "通过", "actual": "ok",
                  "detail": "", "evidence": ""}])
    cfg = _cfg(tmp_path, **{
        "consolidate": {
            "base": [],
            "supplements": [
                {"module": "FILEDL2", "anchors": ["FILEDL2"]},
                {"module": "FILEDL", "anchors": ["FILEDL"]},
            ],
        },
        "report": {
            "title": "T", "address": "http://x",
            "doc_order": ["FILEDL2", "FILEDL"],
            "bad_runs": [], "overrides": {}, "exclude": [],
            "output_name": "t_{ts}.md", "footer": "f {now}",
        },
    })
    out, resolved, merged = render_report(cfg, print_summary=False)
    # FILEDL2 拿最新文件; FILEDL 拿含 FILEDL 的旧文件——两条都进 merged 不互抢
    assert "FILEDL2" in merged
    assert "FILEDL" in merged
    # 解析摘要顺序: FILEDL2 在 FILEDL 前
    kinds = [m for m, _, _, _ in resolved]
    assert kinds == ["FILEDL2", "FILEDL"]
