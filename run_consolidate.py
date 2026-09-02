# -*- coding: utf-8 -*-
"""汇总报告入口：python run_consolidate.py --project <名称> [results_dir]

从 consolidate_report.py 抽取的 CLI 壳，读取项目配置执行合并。
用法:
    python run_consolidate.py --project corebridge            # 合并 projects/corebridge/out/results
    python run_consolidate.py --project corebridge <目录>     # 指定结果目录
"""
import sys
from pathlib import Path

from framework import cli
from framework.config import load_project
from framework.consolidate import render_report
from framework.util import win32_utf8

ROOT = Path(__file__).parent


def main(argv=None):
    win32_utf8()
    parser = cli.add_project_arg(prog="run_consolidate")
    parser.add_argument("results_dir", nargs="?", default=None,
                        help="结果目录(缺省取项目配置 paths.results)")
    args = parser.parse_args(argv)

    try:
        if args.project is None:
            sys.exit(cli.list_projects_and_exit(ROOT, prog="run_consolidate"))
        # consolidate 只读 results/report/consolidate 配置节，不需要账号 env → 宽松模式
        cfg = load_project(args.project, ROOT, strict=False)
    except Exception as e:
        print(f"[错误] {e}")
        sys.exit(1)

    try:
        out, resolved, merged = render_report(cfg, results_dir=args.results_dir)
        print(f"\n[完成] {out} ({len(merged)} 条合并结果)")
    except FileNotFoundError as e:
        print(f"[错误] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
