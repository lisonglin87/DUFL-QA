# -*- coding: utf-8 -*-
"""提示词。想改回答风格、引用格式、兜底话术，只改这里。"""

SYSTEM_PROMPT = """你是「校园政策问答助手」，服务对象是本校在读学生。

回答规则：
1. 只能依据下面提供的【资料】回答。资料里没有的内容，直接说"资料里没有查到"，并建议去对应部门确认，不要自己编。
2. 每个结论后面用方括号标注依据序号，例如 [1]；引用多个写 [1][3]。
3. 用口语化中文回答，先给结论，再给条件和办理步骤。
4. 涉及时间、金额、学分、比例等关键数字，必须与资料一致，不要四舍五入或改写。
5. 如果资料之间互相矛盾，指出矛盾并建议以哪份文件为准。"""

NO_HIT_ANSWER = (
    "资料库里没有检索到相关内容。可能是文档还没导入，或者问法差别太大。\n\n"
    "建议：把相关文件放进 data/ 目录，点「重建索引」后再问；紧急问题直接联系教务处/学生处。"
)


def build_context(hits):
    """把检索结果拼成编号资料块：[1] 文件名 · 片段内容"""
    if not hits:
        return "（无相关资料）"
    blocks = []
    for i, h in enumerate(hits, start=1):
        blocks.append(f"【{i}】来源：{h['source']}\n{h['text']}")
    return "\n\n".join(blocks)


def build_messages(question, hits, history=None):
    """组装发给大模型的 messages 列表。"""
    sys = SYSTEM_PROMPT + "\n\n【资料】\n" + build_context(hits)
    msgs = [{"role": "system", "content": sys}]
    for turn in (history or []):
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            msgs.append({"role": turn["role"], "content": turn["content"]})
    msgs.append({"role": "user", "content": question})
    return msgs
