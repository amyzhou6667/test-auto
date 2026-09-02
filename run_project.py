# -*- coding: utf-8 -*-
"""通用引擎入口：python run_project.py --project <名称> [模块...] / --list / --all

从 execute_test_cases.py 的 main/run_modules 抽取的调度骨架，通用化 + 修复：
  - bug5: 模块名先 upper() 再校验（大小写归一化生效）；新增 --list
  - bug6: save_report 移入 finally 内（异常也保报告，不丢已跑结果）
  - per-module try/except: 单模块异常不中断后续模块（原来会整体崩溃丢结果）
  - 模块调度由 @module 注册表 + 配置 modules.order 双轨驱动（删 15 个 elif）
"""
import asyncio
import sys
from pathlib import Path

from framework import cli
from framework.config import load_project
from framework.loader import load_hooks
from framework.report import save_report
from framework.engine import Runner
from framework.util import win32_utf8

ROOT = Path(__file__).parent


def _pick_runner_cls(adapter_cls, cfg):
    """项目 adapter（Runner 子类，含专属 DOM 方法）；无则用通用 Runner。"""
    return adapter_cls or Runner


async def _run(cfg, modules, mods, runner_cls):
    runner = runner_cls(modules, cfg)
    try:
        await runner.start()
        print(f"{'='*66}")
        title = cfg.project.get("title", cfg.project.get("name", ""))
        print(f"  {title} — 测试执行")
        print(f"  地址: {cfg.base_url}")
        print(f"{'='*66}")
    except Exception as e:
        print(f"  [ERROR] 浏览器启动失败: {e!r}")
        # 即便启动失败也尝试保存空报告（保留 finally 语义）
        try:
            await runner.close()
            save_report(runner, cfg, modules=modules)
        except Exception:
            pass
        return

    try:
        for mod in modules:
            print(f"\n\n########## 模块 {mod} ##########")
            spec = mods.get(mod)
            if not spec:
                print(f"  [WARN] 未实现的模块: {mod}")
                continue
            try:
                await spec.fn(runner)
            except Exception as e:  # 单模块异常不中断后续
                print(f"  [ERROR] 模块 {mod} 异常: {e!r}")
    finally:
        await runner.close()
        save_report(runner, cfg, modules=modules)  # 异常也保报告（修 bug6）


def main(argv=None):
    win32_utf8()
    parser = cli.add_project_arg()
    parser.add_argument("--smoke", action="store_true",
                        help="执行项目配置 modules.smoke 冒烟集（默认取 modules.order 全部）")
    args = parser.parse_args(argv)

    try:
        cfg = load_project(args.project, ROOT, strict=not args.list)
    except Exception as e:
        print(f"[错误] {e}")
        sys.exit(1)

    mods, adapter_cls = load_hooks(cfg)
    order = cfg.module_order()

    if args.list:
        print(f"项目: {cfg.project.get('name')} ({cfg.project.get('title', '')})")
        print(f"模块执行顺序 (modules.order, {len(order)} 个):")
        for name in order:
            spec = mods.get(name)
            state = f"已注册({len(spec.cases)} 用例)" if spec else "[未实现]"
            print(f"  - {name:<10} {state}")
        smoke = cfg.smoke_modules()
        print(f"冒烟集 (modules.smoke{', ' + str(len(smoke)) + ' 个' if smoke else ', 未配置'}):")
        if smoke:
            for name in smoke:
                spec = mods.get(name.upper())
                state = f"已注册({len(spec.cases)} 用例)" if spec else "[未实现]"
                print(f"  - {name:<10} {state}")
        return

    modules, _ = cli.resolve_modules(args, order, smoke=cfg.smoke_modules())
    if not modules:
        print("[错误] 没有可执行的模块 (用 --list 查看, 或 --project <名称> 指定项目)")
        sys.exit(1)

    asyncio.run(_run(cfg, modules, mods, _pick_runner_cls(adapter_cls, cfg)))


if __name__ == "__main__":
    main()
