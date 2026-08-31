# -*- coding: utf-8 -*-
"""加载项目 hooks（importlib 正规包导入，不污染 sys.path 全局）。

项目钩子 = projects/<name>/hooks/ 包：
  - modules/ 下每个文件用 @module 装饰器注册一个测试模块
  - adapter.py 提供 Runner 子类（项目专属 DOM 方法），由配置 project.adapter 指定

加载方式: 把 hooks 目录作为一个名为 ``hooks`` 的包导入，使其在 sys.modules 中
可被 hooks/modules/*.py 内的 `from hooks.login import ...` 自然解析。
"""
import importlib
import importlib.util
import sys
from pathlib import Path


def _import_package(name, path):
    """把 path 目录作为名为 name 的包导入（无需 __init__ 外的特殊处理）。"""
    spec = importlib.util.spec_from_file_location(
        name, str(path / "__init__.py"),
        submodule_search_locations=[str(path)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    if spec.loader:
        spec.loader.exec_module(mod)
    return mod


def load_hooks(cfg, framework_imports=None):
    """加载项目的 hooks 包（含 modules/*.py 触发 @module 注册）。

    返回 (registered_modules_dict, adapter_cls)。
    framework_imports: 兼容参数，保留（框架包经 repo_root 注入 sys.path 可 import）。
    """
    from framework import registry

    registry.clear()  # 同一进程切换项目时清掉残留注册

    hooks_dir = cfg.root / "hooks"
    if not hooks_dir.exists():
        return {}, None

    # hooks 内 `from framework.xxx import ...` 依赖仓库根在 sys.path
    repo_root = cfg.root.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # 以 "hooks" 为名导入项目 hooks 包
    _import_package("hooks", hooks_dir)

    # 导入 modules 子包（触发 @module 注册）
    modules_dir = hooks_dir / "modules"
    if modules_dir.exists():
        _import_package("hooks.modules", modules_dir)
        for py in sorted(modules_dir.glob("*.py")):
            if py.name.startswith("_"):
                continue
            mod_name = f"hooks.modules.{py.stem}"
            importlib.import_module(mod_name)

    # adapter 类：配置 project.adapter = "hooks.adapter.CoreBridgeRunner"
    adapter_cls = None
    adapter_cfg = (cfg.project or {}).get("adapter")
    if adapter_cfg:
        if not adapter_cfg.startswith("hooks."):
            raise ImportError(f"project.adapter 必须以 hooks. 开头: {adapter_cfg}")
        mod_name, _, attr = adapter_cfg.rpartition(".")
        importlib.import_module(mod_name)
        adapter_cls = getattr(sys.modules[mod_name], attr, None)
    else:
        adapter_path = hooks_dir / "adapter.py"
        if adapter_path.exists():
            importlib.import_module("hooks.adapter")
            mod = sys.modules["hooks.adapter"]
            adapter_cls = (getattr(mod, "CoreBridgeRunner", None)
                           or getattr(mod, "ProjectRunner", None))

    return registry.registered_modules(), adapter_cls
