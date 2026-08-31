# -*- coding: utf-8 -*-
"""
[DEPRECATED] 兼容壳：旧入口，转调通用引擎 run_consolidate.py。

合并逻辑已通用化到 framework/consolidate.py，配置从项目配置读取。
请改用:
    python run_consolidate.py --project corebridge            # 合并 projects/corebridge/out/results
    python run_consolidate.py --project corebridge <目录>     # 指定结果目录
旧命令形式 (python consolidate_report.py [results_dir]) 仍可用。
原始 v1 版保留在 legacy/consolidate_report_v1.py 备查。
"""
import sys

import run_consolidate


def main():
    argv = ["--project", "corebridge"] + sys.argv[1:]
    run_consolidate.main(argv)


if __name__ == "__main__":
    main()
