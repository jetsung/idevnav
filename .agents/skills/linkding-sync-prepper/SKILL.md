---
name: linkding-sync-prepper
description: 提取 data/navsites.yml 中的新增书签，并按 taxonomy->list->term->links 结构整理到 updates.yaml，以便 c2linkding.py 使用。
---

# Linkding Sync Prepper

该技能用于从 `data/navsites.yml` 提取新添加的链接项，并生成符合 `c2linkding.py` 要求的 `updates.yaml` 格式。

## 工作流

1. **确定新增项**: 使用 `git diff origin/main -- data/navsites.yml` 识别相对于远程主分支真正新增的链接。
2. **结构化处理**: 将这些链接按其所属的 `taxonomy`（大分类）和 `term`（子分类）进行分组。
3. **Schema 格式**:
   ```yaml
   - taxonomy: 分类名称
     list:
     - term: 子分类名称
       links:
       - title: 标题
         url: 链接
         description: 描述
   ```
4. **保存文件**: 将整理后的内容写入项目根目录下的 `updates.yaml` 文件。

## 注意事项

- **对比基准**: 使用 `git diff origin/main` 而不是本地提交历史，确保只提取真正新增的项目。
- **精简字段**: 提取到 `updates.yaml` 时，移除 `logo:`、`favicon:`、`icon:` 等标签，仅保留 `title`, `url`, `description`（这是 c2linkding.py 脚本需要的字段）。
- **增量同步**: 仅包含本次更新中实际新增的项目，避免在 linkding 中产生大量重复检查。
