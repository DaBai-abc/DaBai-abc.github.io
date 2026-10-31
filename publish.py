#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大白博客 · 发布器（只用 Python 标准库，不需要装任何东西）

平时怎么发文
------------
1. 起草一篇：

       python3 publish.py new --title "GitHub Pages 从零到上线" --tag 教程

   它会在 content/ 下生成一个 .md 文件并用默认编辑器打开，
   开头那段 --- 之间是「属性」（标题、日期、标签、摘要、链接短名），
   下面就是正文，正常写 Markdown 就行。

2. 写完之后发布（生成 HTML + 更新列表 + 提交推送一步到位）：

       python3 publish.py post content/xxx.md

3. 加一条资源链接：

       python3 publish.py link --title "Notion 模板合集" \
           --url "https://afdian.com/a/xxx" --desc "12 套模板，含使用说明" --tag 模板

4. 看看现在有哪些文章：

       python3 publish.py list

手机上发文（不用开电脑）
------------------------
在 GitHub 网页版进入 content/ 目录 → Add file → Create new file，
文件名写 xxx.md，内容照上面的 front matter 格式写，提交即可。
仓库里的 GitHub Actions 会自动跑 publish.py build，把文章页和列表生成好。
（第一次需要等 1 分钟左右，之后再改任何 content/*.md 都会自动重建。）

常用开关
--------
    --no-push    只提交到本地，不推送到 GitHub
    --no-commit  只生成文件，不碰 git（想先本地预览时用）

正文支持的 Markdown 语法
------------------------
    标题 # ## ### ####    粗体 **x**    斜体 *x*    行内代码 `x`
    代码块 ```lang ... ```    无序/有序列表    引用 >    分隔线 ---
    图片 ![说明](/path.png)    链接 [文字](https://...)
    提示框（引用块里写标签即可）：

        > [!提示] 注意
        > 这里是要强调的内容。

    URL 用站内绝对路径（/blog/xxx.html），因为站点部署在仓库根目录。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BLOG_DIR = ROOT / "blog"
DATA_DIR = ROOT / "data"
CONTENT_DIR = ROOT / "content"
TPL = ROOT / "templates" / "post-template.html"
POSTS_JSON = DATA_DIR / "posts.json"
RES_JSON = DATA_DIR / "resources.json"


# ---------------------------------------------------------------- 基础工具

def die(msg: str, code: int = 1) -> "NoReturn":  # type: ignore[name-defined]
    print(f"✗ {msg}", file=sys.stderr)
    raise SystemExit(code)


def ok(msg: str) -> None:
    print(f"✓ {msg}")


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def today() -> str:
    return dt.date.today().isoformat()


def slugify(text: str) -> str | None:
    """纯英文标题转成 URL 短名；含中文则返回 None（需要用户自己给 --slug）。"""
    if re.search(r"[\u4e00-\u9fff]", text):
        return None
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or None


# ---------------------------------------------------------------- Markdown

def inline(text: str) -> str:
    codes: list[str] = []

    def stash(m: re.Match) -> str:
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    t = esc(text)
    t = re.sub(r"`([^`]+)`", stash, t)
    t = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)",
        lambda m: '<img src="%s" alt="%s"%s />' % (
            m.group(2), m.group(1), f' title="{m.group(3)}"' if m.group(3) else ""),
        t,
    )
    t = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)",
        lambda m: '<a href="%s"%s>%s</a>' % (
            m.group(2), f' title="{m.group(3)}"' if m.group(3) else "", m.group(1)),
        t,
    )
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![A-Za-z0-9*])\*([^*\n]+)\*(?![A-Za-z0-9*])", r"<em>\1</em>", t)
    t = re.sub(r"\x00(\d+)\x00", lambda m: "<code>%s</code>" % codes[int(m.group(1))], t)
    return t


def join_lines(chunks: list[str]) -> str:
    """中文行之间不插空格，英文单词之间补一个空格。"""
    out = ""
    for i, c in enumerate(chunks):
        if i and out and c:
            if re.match(r"[A-Za-z0-9]", out[-1]) and re.match(r"[A-Za-z0-9]", c[0]):
                out += " "
        out += c
    return out


def md_to_html(md: str) -> str:
    lines = md.split("\n")
    n = len(lines)
    out: list[str] = []
    i = 0

    while i < n:
        raw = lines[i]
        s = raw.strip()

        if not s:
            i += 1
            continue

        # 代码块
        if s.startswith("```"):
            i += 1
            buf: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>%s</code></pre>" % esc("\n".join(buf)))
            continue

        # 分隔线
        if s in ("---", "***", "___"):
            out.append("<hr />")
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            lv = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (lv, inline(m.group(2)), lv))
            i += 1
            continue

        # 引用 / 提示框
        if s.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].lstrip())
                i += 1
            label = None
            cm = re.match(r"^\[!(.+?)\]\s*(.*)$", buf[0]) if buf else None
            if cm:
                label = cm.group(2).strip() or cm.group(1).strip()
                buf = buf[1:]
            inner_md = "\n".join(buf).strip()
            if label:
                out.append(
                    '<div class="callout"><span class="label">%s</span>%s</div>'
                    % (esc(label), md_to_html(inner_md) if inner_md else "")
                )
            else:
                out.append("<blockquote>%s</blockquote>" % (md_to_html(inner_md) if inner_md else ""))
            continue

        # 无序列表
        if re.match(r"^[-*+]\s+", s):
            items = []
            while i < n:
                t = lines[i].strip()
                mm = re.match(r"^[-*+]\s+(.*)$", t)
                if mm:
                    items.append(mm.group(1))
                    i += 1
                elif not t and i + 1 < n and re.match(r"^[-*+]\s+", lines[i + 1].strip()):
                    i += 1
                else:
                    break
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline(x) for x in items))
            continue

        # 有序列表
        if re.match(r"^\d+\.\s+", s):
            items = []
            while i < n:
                t = lines[i].strip()
                mm = re.match(r"^\d+\.\s+(.*)$", t)
                if mm:
                    items.append(mm.group(1))
                    i += 1
                elif not t and i + 1 < n and re.match(r"^\d+\.\s+", lines[i + 1].strip()):
                    i += 1
                else:
                    break
            out.append("<ol>%s</ol>" % "".join("<li>%s</li>" % inline(x) for x in items))
            continue

        # 段落
        buf = []
        while i < n:
            t = lines[i].strip()
            if not t:
                break
            if re.match(r"^(#{1,4}\s|```|>|[-*+]\s+|\d+\.\s+)", t) or t in ("---", "***", "___"):
                break
            buf.append(t)
            i += 1
        out.append("<p>%s</p>" % inline(join_lines(buf)))

    return "\n\n".join(out)


# ---------------------------------------------------------------- 数据文件

def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path.relative_to(ROOT)} 不是合法 JSON：{e}")


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sort_posts(posts: list[dict]) -> list[dict]:
    # 先按日期，同一天再按写入时刻，保证后发的排前面
    return sorted(posts, key=lambda p: (p.get("date", ""), p.get("ts", ""), p.get("slug", "")), reverse=True)


# ---------------------------------------------------------------- 命令：new

def cmd_new(args) -> None:
    title = args.title
    if not title:
        title = input("文章标题：").strip()
        if not title:
            die("标题不能为空")
    tag = args.tag or input("标签（回车默认「笔记」）：").strip() or "笔记"
    slug = args.slug or slugify(title) or f"p{dt.date.today().strftime('%Y%m%d')}"
    path = CONTENT_DIR / f"{slug}.md"
    if path.exists() and not args.force:
        die(f"{path.relative_to(ROOT)} 已存在，换个 --slug 或加 --force")

    summary = args.summary or "一句话说清这篇解决什么问题、适合谁。"
    body = f"""---
title: {title}
date: {today()}
tag: {tag}
summary: {summary}
slug: {slug}
---

开头一段，说清这篇文章解决什么问题、读者能带走什么。

## 小标题

正文。

- 列表项一
- 列表项二

```bash
# 代码块示例
echo "hello"
```

> [!提示] 注意
> 需要强调的注意事项写在这里。

---
"""
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    ok(f"草稿已建：{path.relative_to(ROOT)}")
    print("   写完正文后运行：python3 publish.py post " + str(path.relative_to(ROOT)))
    if sys.platform == "darwin":
        subprocess.run(["open", "-t", str(path)], check=False)


# ---------------------------------------------------------------- 命令：post

def parse_front_matter(text: str) -> tuple[dict, str]:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict[str, str] = {}
    for idx in range(1, len(lines)):
        line = lines[idx]
        if line.strip() == "---":
            return meta, "\n".join(lines[idx + 1:])
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip('"').strip("'")
    return {}, text


def render_post(src: Path, *, force: bool, override_title=None,
                override_date=None, override_slug=None) -> dict:
    """把一篇 Markdown 渲染成 blog/<slug>.html，并写入 data/posts.json。"""
    meta, body_md = parse_front_matter(src.read_text(encoding="utf-8"))
    if not meta:
        die(f"{src.name}: 文件开头缺少 front matter（第一行必须是 ---，见 publish.py 顶部说明）")

    title = meta.get("title") or override_title
    if not title:
        die(f"{src.name}: 缺少 title")
    date = meta.get("date") or override_date or today()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        die(f"{src.name}: date 格式应为 YYYY-MM-DD，当前是 {date}")

    tags = [t.strip() for t in re.split(r"[,，]", meta.get("tag", "") or meta.get("tags", "")) if t.strip()]
    if not tags:
        tags = ["笔记"]

    slug = meta.get("slug") or override_slug or slugify(title)
    if not slug:
        die(f"{src.name}: 中文标题需要指定短名（英文 URL 名），"
            f"在 front matter 里加一行 slug: your-post-name")

    summary = meta.get("summary") or meta.get("description") or ""
    html_body = md_to_html(body_md)
    if not summary:
        first = re.search(r"<p>(.*?)</p>", html_body, re.S)
        plain = re.sub(r"<[^>]+>", "", first.group(1)) if first else ""
        summary = (plain[:80] + "…") if len(plain) > 80 else plain

    tpl = TPL.read_text(encoding="utf-8")
    tokens = {
        "{{TITLE}}": esc(title),
        "{{SUMMARY}}": esc(summary),
        "{{DATE}}": esc(date),
        "{{TAGS}}": "".join('<span class="tag">%s</span>' % esc(t) for t in tags),
        "{{CONTENT}}": html_body,
    }
    for token, value in tokens.items():
        tpl = tpl.replace(token, value)
    leftover = [t for t in tokens if t in tpl]
    if leftover:
        die("模板里还有未替换的占位符：%s" % " ".join(leftover))

    out_path = BLOG_DIR / f"{slug}.html"
    if out_path.exists() and not force:
        die(f"blog/{slug}.html 已存在，换个 slug 或加 --force")
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(tpl, encoding="utf-8")

    posts = load_json(POSTS_JSON, [])
    old = next((p for p in posts if p.get("slug") == slug), None)
    posts = [p for p in posts if p.get("slug") != slug]
    posts.append({
        "slug": slug,
        "title": title,
        "date": date,
        "tag": tags[0],
        "tags": tags,
        "summary": summary,
        # 重复构建时沿用原时间戳，避免每次重排顺序
        "ts": (old or {}).get("ts") or dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    })
    save_json(POSTS_JSON, sort_posts(posts))
    return {"slug": slug, "title": title, "total": len(posts)}


def cmd_post(args) -> None:
    src = Path(args.markdown).expanduser()
    if not src.is_absolute():
        src = (Path.cwd() / src).resolve()
    if not src.exists():
        die(f"找不到文件：{src}")

    info = render_post(src, force=args.force, override_title=args.title,
                       override_date=args.date, override_slug=args.slug)
    ok(f"页面生成：blog/{info['slug']}.html")
    ok(f"列表已更新：data/posts.json（共 {info['total']} 篇）")
    git_commit_and_push(f"post: {info['title']}", args)


def cmd_build(args) -> None:
    """把 content/*.md 全部重新渲染一遍（GitHub Actions 用这个）。"""
    files = sorted(CONTENT_DIR.glob("*.md"))
    if not files:
        print("content/ 下没有 .md 文件，跳过。")
        return
    total = 0
    for f in files:
        info = render_post(f, force=True)
        total = info["total"]
        ok(f"{f.name} → blog/{info['slug']}.html")
    print(f"\n共 {len(files)} 篇，posts.json 现 {total} 条")



# ---------------------------------------------------------------- 命令：link

def cmd_link(args) -> None:
    if not args.title or not args.url:
        die("--title 和 --url 必填")
    if not re.match(r"^https?://", args.url):
        die("--url 必须以 http:// 或 https:// 开头")
    if re.search(r"(pan\.baidu\.com|aliyundrive|alipan\.com|夸克|123pan|drive\.google)", args.url):
        print("⚠ 这个链接看着像网盘直链。资源页是公开页面，直链等于公开分享，请确认没问题。")

    items = load_json(RES_JSON, [])
    items = [it for it in items if it.get("url") != args.url]
    items.insert(0, {
        "title": args.title,
        "desc": args.desc or "",
        "url": args.url,
        "tag": args.tag or "",
        "date": today(),
    })
    save_json(RES_JSON, items)
    ok(f"资源已加入：data/resources.json（共 {len(items)} 条）")

    git_commit_and_push(f"resource: {args.title}", args)


# ---------------------------------------------------------------- 命令：list

def cmd_list(args) -> None:
    posts = sort_posts(load_json(POSTS_JSON, []))
    if not posts:
        print("还没有文章。")
        return
    print(f"共 {len(posts)} 篇：\n")
    for p in posts:
        print(f"  {p.get('date','')}  [{p.get('tag','')}]  {p.get('title','')}  →  /blog/{p.get('slug','')}.html")


# ---------------------------------------------------------------- git

def _mask(text: str) -> str:
    return re.sub(r"(//)[^/@\s]+@", r"\1***@", text)


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def git_commit_and_push(message: str, args) -> None:
    if getattr(args, "no_commit", False):
        print("（--no-commit：已跳过 git，本地文件已就绪）")
        print("   预览：cd %s && python3 -m http.server 8080" % ROOT)
        return

    add = _git(["add", "-A"])
    if add.returncode != 0:
        die("git add 失败：" + _mask(add.stderr.strip()))

    diff = _git(["diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        print("（没有改动，跳过提交）")
        return

    commit = _git(["commit", "-m", message])
    if commit.returncode != 0:
        die("git commit 失败：" + _mask(commit.stderr.strip()[-400:]))
    ok("已提交：" + message)

    if getattr(args, "no_push", False):
        print("（--no-push：未推送。手动推送：git push）")
        return

    push = _git(["push"])
    if push.returncode != 0:
        print(_mask(push.stderr.strip())[-600:])
        die("推送失败，请检查 GitHub 凭据；文件已在本地提交，可稍后手动 git push")
    ok("已推送。1~2 分钟后生效：https://dabai-abc.github.io/")


# ---------------------------------------------------------------- CLI

def main() -> None:
    ap = argparse.ArgumentParser(
        description="大白博客发布器：Markdown → 文章页 → 列表 → 推送",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("正文支持的")[0],
    )
    sub = ap.add_subparsers(dest="cmd")

    p_new = sub.add_parser("new", help="新建一篇草稿（Markdown）")
    p_new.add_argument("--title")
    p_new.add_argument("--tag")
    p_new.add_argument("--slug")
    p_new.add_argument("--summary")
    p_new.add_argument("--force", action="store_true")
    p_new.set_defaults(func=cmd_new)

    p_post = sub.add_parser("post", help="把 Markdown 发布成文章页")
    p_post.add_argument("markdown")
    p_post.add_argument("--title")
    p_post.add_argument("--date")
    p_post.add_argument("--slug")
    p_post.add_argument("--force", action="store_true")
    p_post.add_argument("--no-commit", action="store_true")
    p_post.add_argument("--no-push", action="store_true")
    p_post.set_defaults(func=cmd_post)

    p_link = sub.add_parser("link", help="在资源页加一条链接")
    p_link.add_argument("--title")
    p_link.add_argument("--url")
    p_link.add_argument("--desc")
    p_link.add_argument("--tag")
    p_link.add_argument("--no-commit", action="store_true")
    p_link.add_argument("--no-push", action="store_true")
    p_link.set_defaults(func=cmd_link)

    p_list = sub.add_parser("list", help="列出已发布文章")
    p_list.set_defaults(func=cmd_list)

    p_build = sub.add_parser("build", help="重建 content/ 下全部文章（自动构建用）")
    p_build.set_defaults(func=cmd_build)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
