# -*- coding: utf-8 -*-
"""CLI 参数解析：--project / --list / --all / --smoke / 模块名。"""
import argparse
from pathlib import Path


def add_project_arg(parser=None, prog="run_project"):
    """构造通用参数解析器。返回 parser（可传入已有的以叠加参数）。"""
    parser = parser or argparse.ArgumentParser(prog=prog)
    parser.add_argument("--project",
                        help="项目名（projects/<名称>/），必填；缺省时列出可用项目")
    parser.add_argument("--list", action="store_true",
                        help="列出项目已注册模块与用例范围")
    parser.add_argument("--all", action="store_true",
                        help="执行项目配置 modules.order 中的全部模块")
    parser.add_argument("modules", nargs="*",
                        help="要执行的模块名（如 TC-I TC-UIOP3）；缺省等价 --all")
    return parser


def available_projects(repo_root):
    """列出 projects/ 下含 project.yaml 的项目名（排序）。"""
    projects_dir = Path(repo_root) / "projects"
    if not projects_dir.is_dir():
        return []
    return sorted(p.name for p in projects_dir.iterdir()
                  if p.is_dir() and (p / "project.yaml").exists())


def list_projects_and_exit(repo_root, prog="run_project"):
    """缺省 --project 时列出可用项目并退出（返回退出码）。"""
    print("[错误] 未指定项目 (--project <名称>)。可用项目:")
    for name in available_projects(repo_root):
        print(f"  - {name}")
    print(f"用法: python {prog} --project <名称> [模块...] / --list / --all / --smoke")
    return 1


def resolve_modules(args, order, smoke=None):
    """把命令行模块名解析为执行列表。

    修复 execute_test_cases.py main() 的大小写规范化失效 bug：
    先 upper() 归一化，再与 ALLOWED（order）校验；无效模块名给出警告。
    smoke: 项目配置 modules.smoke 冒烟集；args.smoke 为真时优先返回它（过滤未注册项）。
    返回 (modules, 无效模块名列表)。
    """
    if getattr(args, "smoke", False) and smoke:
        modules, invalid = [], []
        for name in smoke:
            up = name.upper()
            if up in order:
                modules.append(up)
            else:
                invalid.append(name)
        if invalid:
            print("  [WARN] 冒烟集中未识别的模块(已忽略): " + ", ".join(invalid)
                  + " (可用 --list 查看已注册模块)")
        return modules, invalid
    if args.all or not getattr(args, "modules", None):
        return list(order), []
    modules = []
    invalid = []
    for name in args.modules:
        up = name.upper()
        if up in order:
            modules.append(up)
        else:
            invalid.append(name)
    if invalid:
        print("  [WARN] 未识别的模块(已忽略): " + ", ".join(invalid)
              + " (可用 --list 查看已注册模块)")
    return modules, invalid
