# -*- coding: utf-8 -*-
"""
引用校验扩展验收（M6 补丁）：验证新堵上的两个盲区——
① 格式变体（无书名号的「民法典585条」等紧凑写法）不再漏检为 0；
② 内容忠实度：条号在语料真实存在、但复述内容与原文明显不符（纯编造/张冠李戴）时，
   如实标注 suspect，不静默放行。
同时确认正常整句复述不会误报。

红线：这些是"演示用片段"，用于测试校验器逻辑，不构成新增语料。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.rag.citations import verify_citations, extract_citations, TEXTS

art585 = TEXTS["民法典（合同编）"][585]
art584 = TEXTS["民法典（合同编）"][584]

# (说明, 片段, 期望 invalid 数, 期望 suspect 是否非空)
CASES = [
    ("紧凑写法「民法典585条」→ 识别为真引用，invalid=0",
     "依据民法典585条规定，违约金过分高于造成的损失，当事人可以请求适当减少。",
     0, False),
    ("正文里的「第5条」等无法律名条款 → 不误抓",
     "本合同第5条约定交付期限，第10条约定验收方式。",
     0, False),
    ("纯编造内容 → suspect 非空",
     "《民法典》第五百八十五条 规定：违约金无论约定多高都应当得到支持，任何一方当事人无权请求法院调整该数额。",
     0, True),
    ("张冠李戴（把584条内容安到585条）→ suspect 非空",
     f"《民法典》第五百八十五条 {art584[:100]}，故应赔偿全部损失。",
     0, True),
    ("正常整句复述585原文 → 不误报",
     f"依据《民法典》第585条，{art585[:110]}，故违约金可请求适当调整。",
     0, False),
    ("正常复述585关键句 → 不误报",
     "《民法典》第五百八十五条 约定的违约金过分高于造成的损失的，人民法院可以根据当事人的请求予以适当减少。",
     0, False),
    ("正常复述584原文 → 不误报",
     f"《民法典》第五百八十四条 {art584[:110]}，应赔偿。",
     0, False),
]

fail = 0
for i, (note, text, exp_invalid, exp_suspect) in enumerate(CASES, 1):
    check = verify_citations(text)
    got_invalid = len(check["invalid"])
    got_suspect = bool(check["suspect"])
    ok = got_invalid == exp_invalid and got_suspect == exp_suspect
    if not ok:
        fail += 1
    tag = "PASS ✅" if ok else "FAIL ❌"
    print(f"{i}. {note}")
    print(f"   invalid={got_invalid} 期望={exp_invalid} | suspect={got_suspect} 期望={exp_suspect}  {tag}")
    if check["suspect"]:
        print(f"   suspect: {[s['raw'] for s in check['suspect']]}")
    print()

if fail:
    print(f"=== {fail} 项未过，请检查 ===")
    sys.exit(1)
print("=== 全部通过 = 格式变体不漏检、内容存疑如实标注、正常复述不误报 ===")
