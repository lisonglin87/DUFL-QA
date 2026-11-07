#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从大连外国语大学官网抓取公开资料，转成知识库用的 Markdown。

    python scripts/crawl_dlufl.py             # 抓全部栏目（并发，约 2-4 分钟）
    python scripts/crawl_dlufl.py --limit 3   # 每个列表页只取 3 篇，用于调试

规则：
- 只抓公开页面，不登录、不绕过权限；不抓 pdf/doc 附件。
- 站点证书链不完整，urllib 需要关闭校验（仅读取公开内容）。
- 已存在的同名文件会跳过，所以可以反复运行、增量补抓。
- 输出到 data/<栏目>/<标题>.md，文件名即标题，方便人工核对。
"""
from __future__ import annotations

import argparse
import re
import ssl
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

CTX = ssl._create_unverified_context()
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 15
WORKERS = 6

# 栏目 → [(入口页, 最多取几篇)]；入口页本身是文章时直接收
SEEDS: dict[str, list[tuple[str, int]]] = {
    "01-学校概况": [
        ("https://www.dlufl.edu.cn/xygk/xxjj.htm", 1),
        ("https://www.dlufl.edu.cn/xygk/xxbs.htm", 1),
        ("https://www.dlufl.edu.cn/xygk/xxxg.htm", 1),
        ("https://www.dlufl.edu.cn/xygk/xhxs.htm", 1),
    ],
    "02-院系专业": [
        ("https://www.dlufl.edu.cn/jgsz/yxsz.htm", 1),
        ("https://www.dlufl.edu.cn/jgsz/zzjg.htm", 1),
    ],
    "03-教务与选课": [
        ("https://jiaowu.dlufl.edu.cn/jwgl/xk.htm", 8),
        ("https://jiaowu.dlufl.edu.cn/jwgl/wzy_fx.htm", 5),
        ("https://jiaowu.dlufl.edu.cn/jwgl/glks.htm", 5),
    ],
    "04-学籍与转专业": [
        ("https://jiaowu.dlufl.edu.cn/xjgl/zzy.htm", 8),
        ("https://jiaowu.dlufl.edu.cn/xjgl/xjgl.htm", 5),
    ],
    "05-考试与成绩": [
        ("https://jiaowu.dlufl.edu.cn/jwgl/qmks.htm", 6),
    ],
    "06-实践与竞赛": [
        ("https://jiaowu.dlufl.edu.cn/sjjx/glbs.htm", 6),
        ("https://jiaowu.dlufl.edu.cn/sjjx/bysj.htm", 4),
        ("https://jiaowu.dlufl.edu.cn/sjjx/sxsx.htm", 4),
    ],
    "08-国际交流": [
        ("http://ieo.dlufl.edu.cn/", 8),
        ("https://htb.dlufl.edu.cn/", 4),
    ],
    "09-校园生活": [
        ("http://lib.dlufl.edu.cn/", 4),
        ("https://jiaowu.dlufl.edu.cn/fwxx/zxsj.htm", 2),
        ("https://jiaowu.dlufl.edu.cn/fwxx/lnxl.htm", 2),
    ],
    "10-新闻动态": [
        ("https://news.dlufl.edu.cn/", 12),
        ("https://news.dlufl.edu.cn/mtdw.htm", 6),
    ],
    "12-就业与深造": [
        ("https://www.dlufl.edu.cn/zsjy.htm", 1),
    ],
}

BAD_TITLE = re.compile(r"^(更多|查看|首页|上一页|下一页|尾页|下页|上页|返回|打印|关闭|分享|详情)$")
BAD_URL = re.compile(r"(javascript:|^#|\.pdf$|\.docx?$|\.xlsx?$|\.jpe?g$|\.png$|\.zip$)")



def clean_title(t: str) -> str:
    """去掉站点后缀，得到干净的文章标题。"""
    t = t.replace("您的位置", "").strip()
    for site in ("大连外国语大学", "孔子学院工作处", "国际交流与合作处"):
        t = re.split(r"[-_｜|]\s*" + site, t)[0]
    t = re.sub(r"\s+", " ", t).strip(" -_|｜")
    return t[:44].strip()


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as resp:
        raw = resp.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def clean_lines(node: BeautifulSoup) -> str:
    for tag in node(["script", "style", "nav", "header", "footer", "form", "iframe", "noscript"]):
        tag.decompose()
    out: list[str] = []
    for line in node.get_text("\n").split("\n"):
        line = line.replace("\u3000", " ").strip()
        if not line or len(line) < 2:
            continue
        if re.fullmatch(r"[|\-·—\s]{1,8}", line):
            continue
        if out and out[-1] == line:
            continue
        out.append(line)
    return "\n".join(out)


def extract(html: str) -> tuple[str, str]:
    """返回 (标题, 正文)。先找常见正文容器，找不到就取文字最多的块。"""
    soup = BeautifulSoup(html, "lxml")
    # 有的站点 h1 是面包屑（"您的位置：首页>教务管理>选课>"），
    # 所以把 <title> 也作为候选，优先取不像面包屑的那个。
    candidates = []
    for sel in ("h1", ".arti_title", ".article-title", ".title", "title"):
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            candidates.append(el.get_text(strip=True))
    title = ""
    for cand in candidates:
        if "您的位置" in cand or len(cand) < 6:
            continue
        title = clean_title(cand)
        break
    if not title and candidates:
        title = clean_title(candidates[0])

    nodes = []
    for sel in ("div.v_news_content", "div#vsb_content", "div.article-content",
                "div.article_content", "div.TRS_Editor", "div.content",
                "div.main-content", "article", "div.detail"):
        nodes += soup.select(sel)
    if not nodes:
        nodes = sorted(soup.find_all(["div", "td"]),
                       key=lambda d: len(d.get_text(strip=True)), reverse=True)[:3]

    best = max(nodes, key=lambda d: len(d.get_text(strip=True))) if nodes else soup
    text = clean_lines(best)
    if len(text) < 100:
        text = clean_lines(soup)
    return title, text


def safe_name(title: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', " ", title)
    name = re.sub(r"\s+", " ", name).strip()
    return (name[:46] or "未命名").strip()


def article_links(html: str, base: str, limit: int) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"])
        label = a.get_text(strip=True)
        if len(label) < 6 or BAD_TITLE.match(label) or BAD_URL.search(href):
            continue
        if "dlufl.edu.cn" not in urlparse(href).netloc:
            continue
        if not re.search(r"/(info|content|art|detail)/|/\d{4,}/", href):
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append((label, href))
        if len(out) >= limit:
            break
    return out


def save(category: str, title: str, url: str, body: str) -> str | None:
    if len(body) < 150:
        return None
    path = DATA / category / f"{safe_name(title)}.md"
    if path.exists():
        return "skip"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n> 来源：{url}\n\n{body}\n", encoding="utf-8")
    return path.name


def handle_entry(category: str, url: str, limit: int) -> list[str]:
    """入口页 → 文章链接列表 → 抓正文。入口页本身是文章时只收它自己。"""
    made = []
    try:
        html = fetch(url)
    except Exception as exc:
        return [f"! {url} {type(exc).__name__}"]

    links = article_links(html, url, limit)
    if not links:                              # 单页文章
        title, body = extract(html)
        r = save(category, title or url, url, body)
        return [f"{category}/{r}"] if r and r != "skip" else []

    for label, link in links:
        try:
            t, body = extract(fetch(link))
        except Exception:
            continue
        r = save(category, t or label, link, body)
        if r and r != "skip":
            made.append(f"{category}/{r}")
    return made


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="覆盖每个列表页的抓取篇数")
    args = ap.parse_args()

    tasks = []
    for category, entries in SEEDS.items():
        for url, cap in entries:
            tasks.append((category, url, args.limit or cap))

    added: list[str] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(handle_entry, *t): t for t in tasks}
        for fut in as_completed(futures):
            cat, url, _ = futures[fut]
            try:
                for item in fut.result():
                    print("  +", item)
                    added.append(item)
            except Exception as exc:
                print("  !", url, type(exc).__name__)

    print(f"\n完成：新增 {len(added)} 篇 → {DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
