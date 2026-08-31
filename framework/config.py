# -*- coding: utf-8 -*-
"""
项目配置加载：读取 projects/<name>/project.yaml，支持 ${ENV_VAR} 环境变量注入与 .env 解析。

通用引擎的一部分：不绑定任何具体项目。
核心职责：
  - 定位并加载 projects/<项目名>/project.yaml
  - 递归展开 ${VAR} 环境变量引用（os.environ → 项目目录 .env）
  - 缺失变量一次性收集报错，不静默留空（防止账号字段悄悄为空导致假失败）
  - 路径字段相对项目根解析为绝对路径
"""
import os
import re
from pathlib import Path

try:
    import yaml
except ImportError:  # 与 script_runner.py 同款自愈逻辑
    import sys
    os.system(f"{sys.executable} -m pip install pyyaml -q")
    import yaml

ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-[^}]*)?\}")


class ConfigError(Exception):
    """项目配置加载/解析错误（缺失环境变量、文件缺失、结构错误）。"""


# ────────────────────────────────────────────────
# .env 解析（纯函数，自写轻量解析器，不引 python-dotenv）
# ────────────────────────────────────────────────
def load_dotenv(path):
    """解析 KEY=VALUE 形式的 .env 文件，返回 dict。

    规则: 空行/# 注释跳过; 行首 export 前缀忽略; 值 strip 空白。
    不处理引号/转义（测试环境 .env 足够简单）。
    """
    result = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            result[key] = value.strip()
    return result


# ────────────────────────────────────────────────
# ${VAR} 递归展开
# ────────────────────────────────────────────────
def resolve_env(obj, environ=None, missing=None):
    """递归展开字符串中的 ${VAR}。

    environ: 变量来源 dict（默认 os.environ，已含 .env 合并结果）。
    missing: 可选 list，缺失变量名收集于此（同一 missing 列表可跨多次调用累计）。
    返回展开后的新结构（不改原对象）。
    """
    if environ is None:
        environ = os.environ
    if missing is None:
        missing = []

    def _resolve_string(s):
        if not isinstance(s, str) or "${" not in s:
            return s
        used = {}  # name -> 是否有默认值

        def _sub(m):
            name = m.group(1)
            default = m.group(2)
            used[name] = default is not None
            if name in environ:
                return environ[name]
            if default is not None:
                return default[2:]  # 去掉 ":-" 前缀
            return m.group(0)  # 缺失且无默认，先保留原样，最后统一判定

        out = ENV_PATTERN.sub(_sub, s)
        # 未替换的 ${VAR}（缺失且无默认值）—— 保持原样字符串，并登记缺失
        for name, has_default in used.items():
            if not has_default and name not in environ and name not in missing:
                missing.append(name)
        return out

    if isinstance(obj, dict):
        return {k: _resolve_string(v) if isinstance(v, str) else resolve_env(v, environ, missing)
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_string(v) if isinstance(v, str) else resolve_env(v, environ, missing)
                for v in obj]
    return obj


# ────────────────────────────────────────────────
# 项目配置
# ────────────────────────────────────────────────
class ProjectConfig:
    """已解析的项目配置对象。属性访问各配置节，路径字段相对项目根解析。"""

    def __init__(self, raw, project_root, environ=None):
        self.raw = raw
        self.root = Path(project_root)
        self.environ = environ or os.environ
        self.project = raw.get("project") or {}
        self.paths = raw.get("paths") or {}
        self.browser = raw.get("browser") or {}
        self.base_url = raw.get("base_url", "")
        self.api_base = raw.get("api_base", "")
        self.accounts = raw.get("accounts") or {}
        self.selectors = raw.get("selectors") or {}
        self.api = raw.get("api") or {}
        self.evidence = raw.get("evidence") or {}
        self.modules = raw.get("modules") or {}
        self.report = raw.get("report") or {}
        self.consolidate = raw.get("consolidate") or {}
        self.status = raw.get("status") or {}

    # ── 路径解析（相对项目根 → 绝对） ──
    def resolve_path(self, key):
        """按 paths 配置节里的 key 解析为绝对路径（相对项目根）。"""
        rel = self.paths.get(key)
        if not rel:
            raise ConfigError(f"paths.{key} 未在项目配置中定义")
        p = Path(str(rel))
        return p if p.is_absolute() else self.root / p

    def resolve_all_paths(self):
        """返回 paths 各 key 的绝对路径 dict（供运行前统一 mkdir）。"""
        return {k: self.resolve_path(k) for k in (self.paths or {})}

    # ── 账号访问 ──
    def account(self, key):
        acc = self.accounts.get(key)
        if not acc:
            raise ConfigError(f"账号 {key} 未在 accounts 中定义")
        return acc

    def module_order(self):
        return list(self.modules.get("order") or [])

    def status_icons(self):
        return dict(self.status.get("icons") or {})

    def status_stats(self):
        return list(self.status.get("stats") or [])

    def __repr__(self):
        return f"<ProjectConfig name={self.project.get('name')!r} root={self.root}>"


def load_project(project_name, repo_root, strict=True):
    """加载并解析 projects/<project_name>/project.yaml。

    repo_root: 仓库根目录（含 projects/ 与 framework/）。
    strict: 缺失必填环境变量是否抛错（--list 等只读操作传 False，缺的变量保留 ${VAR} 原样）。
    返回 ProjectConfig。env 注入顺序：os.environ → 项目目录 .env（项目 .env 优先于仓库根 .env）。
    """
    repo_root = Path(repo_root)
    project_dir = repo_root / "projects" / project_name
    yaml_path = project_dir / "project.yaml"
    if not yaml_path.exists():
        raise ConfigError(f"未找到项目配置: {yaml_path} (可用 --project <名称> 指定 projects/ 下的项目)")

    with open(yaml_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # 环境变量合并: os.environ 基础, 项目 .env 覆盖, 仓库根 .env 兜底
    environ = dict(os.environ)
    for env_path in (project_dir / ".env", repo_root / ".env"):
        environ.update(load_dotenv(env_path))

    missing = []
    resolved = resolve_env(raw, environ, missing)
    if strict and missing:
        raise ConfigError(
            "缺少环境变量: " + ", ".join(f"${m}" for m in sorted(set(missing)))
            + "\n  请复制 projects/%s/.env.example 为 .env 并填入真实值"
            % project_name
        )
    return ProjectConfig(resolved, project_dir, environ)
