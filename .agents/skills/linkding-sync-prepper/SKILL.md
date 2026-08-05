---
name: linkding-sync-prepper
description: 提取 data/navsites.yml 中的新增书签，继承同栏目已有条目的标签，并同步到自建 linkding 实例 link.asfd.cn。
---

# Linkding Sync Prepper

把 `data/navsites.yml` 中新增的导航条目同步为 `https://link.asfd.cn` 上的 linkding 书签。

全部逻辑封装在同目录的 [`sync.py`](./sync.py) 中，本文档只说明怎么用和为什么这么设计。

## 用法

```bash
# 1. 预览：打印待创建清单，不发任何写请求
./.agents/skills/linkding-sync-prepper/sync.py

# 2. 确认无误后执行
./.agents/skills/linkding-sync-prepper/sync.py --apply
```

- **默认 dry-run**，只有加 `--apply` 才会创建书签。
- `--apply` 会交互式询问 `y/N`；非交互环境（Agent、CI）加 `-y` 跳过。
- `--base <ref>` 可改变 diff 比较基准，缺省 `origin/main`。
- 有条目失败时退出码为 1。

**依赖**：脚本用 [PEP 723](https://peps.python.org/pep-0723/) 内联声明 `pyyaml` 与 `requests`，shebang 为 `#!/usr/bin/env -S uv run --script`——直接执行时 uv 会把依赖装进临时环境，无需预先 pip install，也不污染系统 Python。

没有 uv 时，用已装好这两个包的解释器跑也可以：

```bash
python3 .agents/skills/linkding-sync-prepper/sync.py
```

**前置条件**：环境变量 `LINKDING_API_TOKEN`；外部依赖 `git`。
token 未设置、为空或纯空白时脚本立即退出，不发起任何请求。

## 脚本做了什么

1. `git fetch origin main` 后 `git diff origin/main -- data/navsites.yml`，从新增行中提取 url，作为「本次新增」的判定集合。
2. 遍历 `navsites.yml`，按 `term` 把条目分成「本次新增」和「已有」两类；命中排除栏目的整栏跳过（见下），无 `url` 的条目（如仅有二维码的公众号）跳过并记入报告。
3. 新增条目写入根目录 `updates.yaml`，仅保留 `title`/`url`/`description`。
4. 每个 `term` 取**一个**参照条目继承标签（见下）。
5. 逐条幂等检查后 `POST` 创建，固定 `is_archived=false`、`unread=false`、`shared=true`。
6. 输出汇总：总数 / 成功 / 已存在 / 栏目排除 / 缺URL / 失败。

## 关键设计

### 排除栏目

`sync.py` 顶部的 `EXCLUDED_TAXONOMIES` 列出不同步到 linkding 的栏目，当前为 `{"杰森"}`——该栏目是个人主页与社交入口，不属于公共书签。

命中的栏目**整栏跳过**：其下所有 term 的新增条目既不写入 `updates.yaml`，也不参与标签反查和创建，只在输出中列为 `[跳过-栏目排除]`。要增减排除栏目，改这一个常量即可。

### 标签继承：单条参照，取得即止

对每个 `term`，按 yml 顺序取该 term 下**已有条目**的 url，调 `GET /api/bookmarks/check/` 读 `bookmark.tag_names`，原样用作该 term 下全部新增条目的标签。

- `bookmark` 为 `null` 或请求失败 → 顺延下一个已有条目。
- 拿到非 null 的 `bookmark` → **立即停止**，包括 `tag_names` 为空数组的情况（空数组是「确实没标签」的有效结论，不是失败）。
- 已有条目耗尽或该 term 是全新栏目 → 标签为 `[]`，不回退用 `term`/`taxonomy` 名猜测。

不做多条采样、合并或频次统计——结果完全等同于所选那一条。这样每个 term 只需 1 次请求，且没有需要精确复现的统计规则。

代价是标签质量取决于选中的那一条；dry-run 清单就是防止标签污染的人工防线。

### 创建前必须幂等检查

linkding 的 `POST /api/bookmarks/` 对**已存在的 URL 是静默更新而非报错**。不预先 `check` 就直接 POST，会把你在 linkding 后台人工改过的标题、描述、标签覆盖回 yml 的值。

所以这一步不是性能优化，是数据安全要求。也正因如此，重复执行是安全的。

### 必须伪装 User-Agent

`link.asfd.cn` 在 Cloudflare 后面，会按 UA 拦截 `python-requests`，返回 **403 + error code 1010**。脚本里固定了一个浏览器 UA。

这个坑很隐蔽：token 完全正常，curl 也能通，只有 Python 默认 UA 会被挡。若将来换 HTTP 客户端，务必保留 UA 设置。

### 为什么用 git diff 而非本地提交历史

本地可能已有多个未推送的提交，用本地历史会漏掉早先提交中新增的条目。脚本每次会先 `git fetch origin main` 刷新引用，避免陈旧基准把已同步条目误判为新增。

## 注意事项

- `updates.yaml` 是保留的中间产物，供人工复核，也是部分失败后的重试记录。
- **本流程只处理新增，不同步修改**。已有条目的 `description` 等字段在 yml 中被改动时，linkding 上不会更新（那需要 `PATCH /api/bookmarks/<id>/`，目前未实现）。
- 根目录的 `c2linkding.py` 是早期脚本，**不要用**：它把标签硬编码为 `[term]`，没有标签继承，也没有 UA 规避。
- 本流程只用到 `GET /api/bookmarks/check/` 和 `POST /api/bookmarks/` 两个接口。需要其它接口时查 linkding 官方文档：
  <https://github.com/sissbruecker/linkding/blob/master/docs/src/content/docs/api.md>
