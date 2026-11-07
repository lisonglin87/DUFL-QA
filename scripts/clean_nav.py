#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清洗抓取正文里混进来的站点导航 / 页脚。

    python scripts/clean_nav.py            # 预览会删多少行
    python scripts/clean_nav.py --apply    # 真正写回

为什么需要：官网页面把导航（"首页 / 大外新闻 / 学校概况…"）也渲染成正文文本，
抓下来后每个文件前 20 行都是废话，还会让检索把这些导航词当成内容匹配，
出现"问学院，召回孔子学院新闻"这种离谱结果。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# 整行完全等于这些词就删（导航/栏目名）
NAV_WORDS = {
    "ENGLISH", "日本語", "Pусский", "한국어", "首页", "大外新闻", "媒体大外",
    "重要专题", "通知公告", "学校概况", "学校简介", "现任领导", "学校标识",
    "校训校歌", "校花校树", "新闻中心", "机构设置", "组织机构", "院系设置",
    "教学科研", "招生就业", "合作交流", "国际交流与合作", "孔子学院工作处",
    "校友总会", "信息公开", "信息公开网", "信访通道", "招标采购", "图书资料",
    "校内链接", "精品课堂", "网络孔子学院", "俄语中心", "教育发展基金会",
    "数字大外", "大外要闻", "查看更多", "阅读全文", "正文", "打印", "关闭",
}
# 整行以这些开头就删（页脚/面包屑/栏目头）
PREFIXES = (
    "版权所有", "辽ICP备", "反馈意见", "邮编", "技术支持", "地址：", "地址:",
    "Copyright", "您的位置", "当前位置", "首页 /", "首页>", "MORE", "共",
)
# 一行里出现 3 个以上"栏目名"也算导航（应对被塞成一行的情况）
NAV_HINT = re.compile(r"(学校概况|新闻中心|机构设置|招生就业|信息公开|图书资料)")


def is_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s in NAV_WORDS:
        return True
    if s.startswith(PREFIXES):
        return True
    if len(s) <= 12 and s.count("|") >= 2:
        return True
    if NAV_HINT.search(s) and len(s) < 60 and not s.endswith("。"):
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    files = cleaned = removed = 0
    for path in sorted(DATA.rglob("*.md")):
        lines = path.read_text(encoding="utf-8").split("\n")
        keep = [ln for ln in lines if not is_noise(ln)]
        # 折叠连续空行
        out = []
        for ln in keep:
            if not ln.strip() and out and not out[-1].strip():
                continue
            out.append(ln)
        drop = len(lines) - len(out)
        if drop:
            files += 1
            removed += drop
            if args.apply:
                path.write_text("\n".join(out).strip() + "\n", encoding="utf-8")
                cleaned += 1
    print(f"{'已清洗' if args.apply else '待清洗'} {files} 个文件，删除 {removed} 行导航/页脚")
    return 0


if __name__ == "__main__":
    sys.exit(main())
