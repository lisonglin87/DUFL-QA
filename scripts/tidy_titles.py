#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理抓取下来的文件名：去掉"您的位置：首页>..."这类面包屑标题和站点后缀。

    python scripts/tidy_titles.py            # 只预览，不改名
    python scripts/tidy_titles.py --apply    # 真正改名（同时修正文件里的 H1）

浏览器抓取时，有些页面的 h1 是面包屑（"您的位置：首页>教务管理>选课>"），
文件名就跟着变难看了。这里改为从页面 <title> 取真标题，并去掉
"-大连外国语大学｜教务处" 这类后缀。
"""
from __future__ import annotations

import argparse
import re
import ssl
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CTX = ssl._create_unverified_context()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"

BAD_NAME = re.compile(r"您的位置|正文$|^-|｜教务处|新闻中心|孔子学院工作处|国际交流与合作处")
SUFFIX = re.compile(r"[-_｜|]\s*(大连外国语大学.*|孔子学院工作处.*|国际交流与合作处.*)$")


def clean_title(t: str) -> str:
    t = t.replace("您的位置", "").strip()
    t = re.split(r"[-_｜|]\s*大连外国语大学", t)[0]
    t = re.split(r"[-_｜|]\s*孔子学院工作处", t)[0]
    t = re.split(r"[-_｜|]\s*国际交流与合作处", t)[0]
    t = re.sub(r"\s+", " ", t).strip(" -_|｜")
    return t[:44].strip()


def fetch_title(url: str) -> str:
    req = subprocess.run(["curl", "-sL", "-m", "20", "-A", UA, url],
                         capture_output=True)
    html = req.stdout.decode("utf-8", "ignore")
    soup = BeautifulSoup(html, "lxml")
    if not soup.title:
        return ""
    return clean_title(soup.title.get_text(strip=True))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正执行改名")
    args = ap.parse_args()

    changed = 0
    for path in sorted(DATA.rglob("*.md")):
        stem = path.stem
        if not BAD_NAME.search(stem):
            continue
        text = path.read_text(encoding="utf-8")
        m = re.search(r"^> 来源：(\S+)", text, re.M)
        new = fetch_title(m.group(1)) if m else ""
        if not new or BAD_NAME.search(new) or len(new) < 6:
            print(f"  ? 跳过（拿不到标题）{stem}")
            continue
        target = path.with_name(new + ".md")
        if target.exists():
            target = path.with_name(f"{new}-2.md")
        print(f"  {stem}\n    → {target.stem}")
        if args.apply:
            # 同步修正正文第一行的 H1
            body = re.sub(r"^# .*$", f"# {new}", text, count=1, flags=re.M)
            target.write_text(body, encoding="utf-8")
            path.unlink()
        changed += 1

    print(f"\n{'已改名' if args.apply else '待改名'} {changed} 个文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
