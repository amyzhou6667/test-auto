# -*- coding: utf-8 -*-
"""
[DEPRECATED] 兼容壳：旧入口，转调通用引擎 run_project.py。

CoreBridge 专属执行逻辑已迁移到 projects/corebridge/hooks/。
请改用:
    python run_project.py --project corebridge            # 全量
    python run_project.py --project corebridge TC-I TC-B  # 指定模块
    python run_project.py --project corebridge --list     # 列出模块
旧命令形式 (python execute_test_cases.py TC-I) 仍可用，但行为等价于 --project corebridge。
原始 v1 单体版保留在 legacy/execute_test_cases_v1.py 备查。
"""
import sys

import run_project


def main():
    argv = ["--project", "corebridge"] + sys.argv[1:]
    run_project.main(argv)


if __name__ == "__main__":
    main()
