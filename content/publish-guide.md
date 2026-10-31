---
title: 在这个博客上发文：三条路，从电脑到手机
date: 2026-10-31
tag: 教程
summary: GitHub Pages 没有后台，所以「发布」只有一种本质：写文件再推送。这里把它拆成三条不同重量的路。
slug: publish-guide
---

这个站点是丢在 GitHub Pages 上的静态文件，没有数据库、没有后台、没有登录框。所以它天生不会给你一个「新建文章」的按钮——按钮背后得有人替你写文件、改列表、再推上去。

想通这一点，剩下的只是「谁来做这几步」。三条路，从重到轻。

## 一、电脑上一条命令（写长文用这条）

仓库根目录有个 `publish.py`，只用 Python 标准库，不用装依赖。

先起草：

```bash
python3 publish.py new --title "标题" --tag 教程
```

它会在 `content/` 下生成一个 Markdown 文件，开头是属性区，下面是正文：

```text
---
title: 标题
date: 2026-10-31
tag: 教程
summary: 一句话说清这篇解决什么问题
slug: your-post-name
---
```

`slug` 就是文章地址里那一段，只能用小写字母、数字和连字符。中文标题必须手动给一个。

写完执行：

```bash
python3 publish.py post content/your-post-name.md
```

它做四件事：渲染成 `blog/your-post-name.html`、在 `data/posts.json` 里记一笔、提交、推送。一两分钟后线上就有了。

## 二、手机上直接新建文件（随手记用这条）

不用开电脑，浏览器就能干：

1. 打开仓库的 `content/` 目录
2. Add file → Create new file
3. 文件名写成 `xxx.md`，内容照上面的属性区格式写
4. 提交

仓库里配了一个自动构建（GitHub Actions），只要 `content/` 里的 Markdown 有变化，它就会自动把文章页和列表重新生成好再提交回来，大约一分钟。

> [!提示] 文件名和 slug 要一致
> 文件叫 `xxx.md`，属性区里写 `slug: xxx`，两处一致最不容易出错。地址就是 `/blog/xxx.html`。

## 三、改一条 JSON（加资源链接用这条）

「资源」页不写死在 HTML 里，它读的是 `data/resources.json`。加一条资源就是往数组里加一个对象：

```json
{
  "title": "资源名",
  "desc": "一句话说明包含什么、适合谁",
  "url": "https://付费平台链接",
  "tag": "模板",
  "date": "2026-10-31"
}
```

在 GitHub 网页上点开这个文件、点铅笔图标、加完提交，同样是自动生效。电脑上也可以一条命令：

```bash
python3 publish.py link --title "资源名" --url "https://..." --desc "说明" --tag 模板
```

## 三件容易踩的事

- **资源页是公开的**，别把网盘直链写进去，只放第三方平台的入口。
- **图片**要放进 `assets/`，正文里用 `/assets/xxx.png` 这种站内绝对路径，别用相对路径，否则从不同层级打开会裂。
- **想撤回一篇文章**：删掉 `content/` 里那个 md，再手动删 `blog/xxx.html`，最后从 `data/posts.json` 里删掉那一条。三处都清干净，列表才不会留一个点进去 404 的入口。

---

本质就这么简单：这个博客的「后台」，是一个 Markdown 文件加一次 git 推送。剩下的工作，交给脚本。
