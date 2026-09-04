---
description: 记录功能变动到 CHANGELOG.md，并同步更新相关文档（USAGE.md / CLAUDE.md / project.yaml 注释等）。用法: /record-change 描述你做了什么改动
---

# /record-change — 记录功能变动 & 同步文档

## 使用

```
/record-change 新增了 XX 功能
/record-change 修改了 YY 模块的执行逻辑
/record-change 修复了 ZZ 问题
```

参数 `$ARGUMENTS` 是本次变动的自然语言描述。

## 执行流程

### 第一步：分析变动

根据 `$ARGUMENTS` 和当前会话上下文，识别：

```
变动类型:  feat | fix | refactor | docs | config | test | chore
影响范围:  framework | run_project | hooks | project:<名称> | docs | commands | 其他
变动文件:  列出本次改动涉及的关键文件路径
```

如果 `$ARGUMENTS` 为空或不明确，**询问用户**后再继续。

### 第二步：写入 CHANGELOG.md

读取 `CHANGELOG.md`，在 `<!-- 新条目插入到本行下方 -->` 标记的**正下方**插入新条目：

```markdown
## YYYY-MM-DD — 变动标题（一句话概括）

- **类型**: feat / fix / refactor / docs / config / test / chore
- **范围**: framework / hooks / project:xxx / ...
- **改动文件**:
  - `path/to/file1` — 简要说明
  - `path/to/file2` — 简要说明
- **详情**: 详细描述变动内容、动机、影响
- **关联文档**: 列出可能需要同步更新的文档（下一步处理）
```

日期用当天日期（YYYY-MM-DD 格式）。

### 第三步：识别需同步的文档

根据影响范围，自动判断需要更新哪些文档：

| 影响范围 | 需检查的文档 |
|---------|-------------|
| framework | `CLAUDE.md`、`USAGE.md` |
| run_project / run_consolidate | `CLAUDE.md`、`USAGE.md` |
| hooks / project:* | 对应 `projects/<名称>/project.yaml` 注释、`CLAUDE.md` |
| docs | `USAGE.md` |
| commands | `CLAUDE.md`（常用命令段） |
| 多个范围 | 合并去重 |

### 第四步：更新文档

对每个需同步的文档：

1. **读取**该文档当前内容
2. **判断**是否真的需要改动（如果文档已有准确描述，跳过并说明）
3. **精准编辑**相关段落，保持文档风格一致
4. **报告**做了哪些更新

更新原则：
- `CLAUDE.md`：保持简洁，只更新命令/结构/指引相关的段落
- `USAGE.md`：更新项目结构、使用说明、流程描述
- `project.yaml`：只更新注释，不改配置值
- **不改动**已有的准确内容，只补充/修正与本次变动相关的部分
- **不删除**文档中与本次变动无关的内容

### 第五步：汇总报告

输出本次操作摘要：

```
✅ 变动已记录到 CHANGELOG.md
📝 同步更新了以下文档:
   - CLAUDE.md: 更新了常用命令段
   - USAGE.md: 更新了项目结构说明
   （或：无需更新的文档已跳过）
```

## 注意事项

- 每次只记录**一个**逻辑变动（一次 commit 对应一条记录）
- 变动描述要具体，不要写"做了修改"这种模糊表述
- 如果用户在一次对话中做了多个独立变动，建议分多次 `/record-change`
- CHANGELOG 保持**倒序**（最新在最上面）
