#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pyyaml>=6.0",
#     "requests>=2.31",
# ]
# ///
"""
把 data/navsites.yml 中新增的导航条目同步为 linkding 书签。

流程：
  1. git diff origin/main -- data/navsites.yml 找出新增条目
  2. 对每个涉及的 term，取该 term 下已有条目反查 tag_names（取得即止）
  3. 逐条幂等检查后创建书签

默认 dry-run，只打印待创建清单；加 --apply 才真正写入。

用法（依赖由 PEP 723 内联声明，uv 会自动装进临时环境）：
    ./sync.py                       # 预览
    ./sync.py --apply               # 执行创建
    ./sync.py --apply -y            # 跳过二次确认

也可用已装好 pyyaml/requests 的解释器直接跑：
    python3 sync.py

外部依赖：git；环境变量 LINKDING_API_TOKEN。
"""

import argparse
import os
import subprocess
import sys
from urllib.parse import quote

import requests
import yaml

API_BASE = "https://link.asfd.cn/api/bookmarks/"
NAVSITES = "data/navsites.yml"
UPDATES = "updates.yaml"

# 不同步到 linkding 的栏目（个人主页/社交入口等，不属于公共书签）
EXCLUDED_TAXONOMIES = {"杰森"}

# link.asfd.cn 在 Cloudflare 后面，会按 User-Agent 拦截 python-requests
# 并返回 403 (error code 1010)。必须伪装成常规浏览器 UA。
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

TIMEOUT = 30


def repo_root() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def load_token() -> str:
    """步骤 0：环境检查。未设置/空串/纯空白一律视为缺失。"""
    token = os.getenv("LINKDING_API_TOKEN") or ""
    if not token.strip():
        sys.exit("未设置 LINKDING_API_TOKEN，跳过同步")
    return token.strip()


def load_yaml(path: str):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def git_added_urls(base: str) -> set:
    """从 git diff 中取出新增行里的 url，作为「本次新增」的判定依据。"""
    subprocess.run(["git", "fetch", "origin", "main"],
                   capture_output=True, check=False)
    diff = subprocess.run(
        ["git", "diff", base, "--", NAVSITES],
        capture_output=True, text=True, check=True,
    ).stdout

    urls = set()
    for line in diff.splitlines():
        # 只看新增行，排除 +++ 文件头
        if line.startswith("+") and not line.startswith("+++"):
            stripped = line[1:].strip()
            if stripped.startswith("- url:") or stripped.startswith("url:"):
                url = stripped.split("url:", 1)[1].strip()
                if url:
                    urls.add(url)
    return urls


def collect(nav, added_urls: set):
    """遍历 yml，按 term 分出「新增条目」与「已有条目」。

    返回 (groups, missing, excluded)：
      groups   [(taxonomy, term, [新增条目...], [已有条目 url...]), ...]
      missing  缺少 url 被跳过的条目，用于报告
      excluded 命中 EXCLUDED_TAXONOMIES 而整栏跳过的新增条目，用于报告
    """
    groups, missing, excluded = [], [], []

    for tax_entry in nav or []:
        taxonomy = tax_entry.get("taxonomy", "")

        # 整个栏目不同步：连带其下所有 term 一起跳过，
        # 既不进 updates.yaml，也不做标签反查
        if taxonomy in EXCLUDED_TAXONOMIES:
            for item in tax_entry.get("list", []) or []:
                for link in item.get("links", []) or []:
                    url = (link.get("url") or "").strip()
                    if url in added_urls:
                        excluded.append((taxonomy, item.get("term", ""),
                                         link.get("title", "")))
            continue

        for item in tax_entry.get("list", []) or []:
            term = item.get("term", "")
            new_links, existing_urls = [], []

            for link in item.get("links", []) or []:
                url = (link.get("url") or "").strip()
                title = link.get("title", "")
                if not url:
                    # 仅有二维码等无 url 的条目
                    if title:
                        missing.append((taxonomy, term, title))
                    continue
                if url in added_urls:
                    new_links.append({
                        "title": title,
                        "url": url,
                        "description": link.get("description") or "",
                    })
                else:
                    existing_urls.append(url)

            if new_links:
                groups.append((taxonomy, term, new_links, existing_urls))

    return groups, missing, excluded


class Linkding:
    def __init__(self, token: str):
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Token {token}",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        })

    def check(self, url: str):
        """返回 (bookmark_or_None, error_or_None)。"""
        try:
            r = self.s.get(f"{API_BASE}check/?url={quote(url, safe='')}",
                           timeout=TIMEOUT)
            r.raise_for_status()
            return r.json().get("bookmark"), None
        except Exception as e:
            return None, str(e)

    def create(self, item: dict, tags: list):
        payload = {
            "url": item["url"],
            "title": item["title"],
            "description": item["description"],
            "tag_names": tags,
            "is_archived": False,
            "unread": False,
            "shared": True,
        }
        try:
            r = self.s.post(API_BASE, json=payload, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json(), None
        except Exception as e:
            detail = ""
            resp = getattr(e, "response", None)
            if resp is not None:
                detail = f" {resp.text[:150]}"
            return None, f"{e}{detail}"


def inherit_tags(ld: Linkding, existing_urls: list):
    """步骤 2：取单个参照条目的 tag_names，取得即止。

    bookmark 为 null 或请求失败 -> 顺延下一个。
    bookmark 非 null -> 立即返回其 tag_names，即便是空数组。
    全部耗尽 -> 返回 []。
    """
    for url in existing_urls:
        bookmark, err = ld.check(url)
        if err:
            print(f"    · 参照 {url} 查询失败（顺延）: {err}")
            continue
        if bookmark is None:
            continue
        # 空数组也是有效结论，不触发顺延
        return bookmark.get("tag_names", []), url
    return [], None


def write_updates(root: str, groups):
    """写出 updates.yaml，仅保留 title/url/description。"""
    by_tax = {}
    for taxonomy, term, links, _ in groups:
        by_tax.setdefault(taxonomy, []).append({"term": term, "links": links})

    data = [{"taxonomy": t, "list": lst} for t, lst in by_tax.items()]
    path = os.path.join(root, UPDATES)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False,
                       default_flow_style=False)
    return path


def main():
    ap = argparse.ArgumentParser(description="同步 navsites.yml 新增条目到 linkding")
    ap.add_argument("--apply", action="store_true",
                    help="真正创建书签（缺省为 dry-run，只打印清单）")
    ap.add_argument("-y", "--yes", action="store_true",
                    help="配合 --apply 跳过二次确认")
    ap.add_argument("--base", default="origin/main", help="diff 比较基准")
    args = ap.parse_args()

    token = load_token()
    root = repo_root()
    os.chdir(root)

    added = git_added_urls(args.base)
    if not added:
        print("无新增内容")
        return

    nav = load_yaml(os.path.join(root, NAVSITES))
    groups, missing, excluded = collect(nav, added)

    for taxonomy, term, title in excluded:
        print(f"[跳过-栏目排除] {taxonomy} / {term} / {title}")
    for taxonomy, term, title in missing:
        print(f"[跳过-缺URL] {taxonomy} / {term} / {title}")

    if not groups:
        if excluded:
            print(f"\n无需同步的新增内容（{len(excluded)} 条均属排除栏目）")
        else:
            print("无新增内容")
        return

    path = write_updates(root, groups)
    print(f"已写入 {path}\n")

    ld = Linkding(token)

    # 步骤 2 + 3：解析标签并打印待创建清单
    plan = []
    for taxonomy, term, links, existing in groups:
        tags, src = inherit_tags(ld, existing)
        print(f"[{taxonomy} / {term}] tag_names={tags}"
              + (f"  ← 继承自 {src}" if src else "  ← 无可用参照，留空"))
        for item in links:
            print(f"    - {item['title']}  {item['url']}")
            plan.append((item, tags))
        print()

    total = len(plan)
    if not args.apply:
        print(f"[dry-run] 共 {total} 条待创建。确认后加 --apply 执行。")
        return

    if not args.yes:
        try:
            if input(f"确认创建以上 {total} 条书签？[y/N] ").strip().lower() != "y":
                print("已取消")
                return
        except EOFError:
            sys.exit("非交互环境请使用 --apply -y")

    # 步骤 4：幂等检查 + 创建
    ok, exists, failed = [], [], []
    for item, tags in plan:
        bookmark, err = ld.check(item["url"])
        if err:
            failed.append((item, f"check 失败: {err}"))
            print(f"[失败] {item['title']} — check: {err}")
            continue
        if bookmark:
            exists.append(item)
            print(f"[跳过-已存在] {item['title']}")
            continue

        created, err = ld.create(item, tags)
        if err:
            failed.append((item, err))
            print(f"[失败] {item['title']} — {err}")
        else:
            ok.append(item)
            print(f"[成功] {item['title']} — id={created.get('id')} "
                  f"tags={created.get('tag_names')}")

    # 步骤 5：汇总报告
    print("\n" + "=" * 46)
    print(f"总数 {total} | 成功 {len(ok)} | 已存在 {len(exists)} | "
          f"栏目排除 {len(excluded)} | 缺URL跳过 {len(missing)} | "
          f"失败 {len(failed)}")
    for item, reason in failed:
        print(f"  失败: {item['title']} ({item['url']})\n    原因: {reason}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
