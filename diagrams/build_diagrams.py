# -*- coding: utf-8 -*-
"""Build the course diagrams: HTML (source of truth) and PNG (for README and slides).

Usage: python diagrams/build_diagrams.py
Needs Chrome or Edge installed. All block sizes are fixed so every diagram stays aligned.
"""
import html
import os
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
FONT = "'Noto Sans TC','Microsoft JhengHei','PingFang TC',Arial,sans-serif"
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]
# group colours (course flow) and executor colours (who does the step): fill, border, text
GROUP = {"think": ("#CFE6F7", "#1F618D", "#0B2F4A"), "make": ("#CDEFD9", "#1E8449", "#0B3D20"),
         "check": ("#F9D5D1", "#A93226", "#4A0E0A"), "keep": ("#E5D3F0", "#6C3483", "#2E0F45"),
         "root": ("#1F3A5F", "#0B1E36", "#FFFFFF"), "gold": ("#FFE9AE", "#B7791F", "#3A2500")}
WHO = {"P": ("程式", "#E8EDF2", "#455A64", "#1C272C"), "L": ("LLM", "#D4E9FA", "#1565C0", "#0B2F4A"),
       "H": ("人", "#FFE0B2", "#D35400", "#4A2000")}

# (stage, group, steps) ; step = (who, text, [apis or tools])
STAGES = [
    ("① 規劃", "think", [
        ("H", "定題目與檢索範圍", []),
        ("L", "寫出專案說明書", ["高階模型"]),
        ("H", "補上何時停、怎樣算完成\n花多少錢", []),
        ("H", "資料分級\n分配模型", ["高階判斷／便宜量產"]),
        ("H", "點頭才開工", []),
    ]),
    ("② 研究", "think", [
        ("L", "主代理拆題目\n寫交辦單", ["高階模型"]),
        ("L", "子代理平行查資料", ["PubMed E-utilities", "Europe PMC", "網頁搜尋"]),
        ("L", "主代理抽驗", []),
        ("L", "沒參與的代理查核", []),
        ("H", "決定採納哪些", []),
    ]),
    ("③ 取材", "make", [
        ("P", "檢索候選", ["PubMed E-utilities", "Europe PMC", "OpenAlex"]),
        ("P", "DOI 比對、去重", ["Crossref", "NCBI 編號轉換"]),
        ("P", "抓開放取用全文", ["PMC 開放資料桶", "Unpaywall", "出版社官方 API"]),
        ("H", "校內 VPN\n館際合作", []),
        ("P", "檢查檔案對不對\n分四級", []),
        ("H", "看有疑問的檔案", []),
    ]),
    ("④ 開發", "make", [
        ("H", "開工作單\n寫怎樣算完成", ["GitHub Issues"]),
        ("L", "寫程式\n提示與欄位", ["Claude Code"]),
        ("P", "測試、防止重複執行\n中斷可接續", ["GitHub Actions"]),
        ("H", "審查後合併", ["GitHub"]),
        ("L", "小批試跑\n只看方向", ["便宜模型"]),
        ("L", "全批萃取", ["便宜模型"]),
    ]),
    ("⑤ 驗證", "check", [
        ("L", "換一條路再做一次\n拿無關論文測試", ["便宜模型"]),
        ("P", "兩條路的結果比對", ["Python"]),
        ("L", "沒參與的代理重算", []),
        ("H", "抽查原文、做決定", []),
        ("P", "通過才更新數字", ["Python"]),
    ]),
    ("⑥ 知識庫", "keep", [
        ("P", "原檔轉文字", ["Python", "本機轉錄"]),
        ("L", "整理重點\n提議建卡", []),
        ("H", "核准建卡", []),
        ("L", "寫卡\n一張一個主張", ["Claude Code"]),
        ("P", "格式自動檢查\n缺欄位就退回", ["存檔後自動檢查"]),
        ("H", "審 AI 寫的草稿", ["Obsidian"]),
    ]),
    ("⑦ 迭代", "keep", [
        ("P", "每月排程檢索", ["GitHub Actions", "Europe PMC"]),
        ("L", "篩選候選論文", ["NVIDIA NIM", "Groq", "Cloudflare"]),
        ("P", "開成工作單", ["GitHub Issues"]),
        ("H", "看工作單、做決定", []),
        ("L", "把失敗整理成規則", []),
        ("H", "核准，寫回 ①", []),
    ]),
]

SLUG = ["plan", "research", "sources", "develop", "verify", "knowledge_base", "iterate"]


def esc(t):
    return html.escape(t)


def box(text, group, w, h, size):
    f, b, c = GROUP[group]
    return (f'<div class="box" style="width:{w}px;height:{h}px;background:{f};border-color:{b};color:{c};'
            f'font-size:{size}px">{text}</div>')


def page(title, body, width, extra=""):
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>{esc(title)}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#fff;font-family:{FONT};color:#1a1a1a}}
#c{{width:{width}px;padding:36px}}
h1{{margin:0 0 8px;font-size:38px}}.sub{{font-size:21px;color:#455;margin:0 0 24px}}
.box{{border:5px solid;border-radius:14px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;line-height:1.4;font-weight:700}}
.box small{{font-weight:500;font-size:.72em;line-height:1.45}}
.row{{display:flex;align-items:center}}
.ar{{flex:none;display:flex;align-items:center;justify-content:center;color:#455A64}}
.card{{border:5px solid;border-radius:14px;padding:12px;display:flex;flex-direction:column;gap:8px;position:relative}}
.who{{align-self:flex-start;color:#fff;border-radius:8px;padding:2px 14px;font-weight:700}}
.txt{{font-weight:700;line-height:1.35;text-wrap:balance}}
.api{{margin-top:auto;display:flex;flex-wrap:wrap;gap:5px}}
.api i{{font-style:normal;background:#fff;border:2px solid #2E7D32;color:#1B5E20;border-radius:7px;padding:1px 8px;font-weight:600}}
.lg{{display:flex;gap:26px;font-size:22px;font-weight:700;align-items:center}}
.lg span{{display:flex;align-items:center;gap:9px}}.lg b{{width:34px;height:26px;border:4px solid;border-radius:6px;display:inline-block}}
{extra}</style></head><body><div id="c">{body}</div></body></html>"""


def arrow(w, size=40):
    return (f'<div class="ar" style="width:{w}px"><svg width="{w}" height="{size}" viewBox="0 0 {w} {size}">'
            f'<line x1="3" y1="{size/2}" x2="{w-14}" y2="{size/2}" stroke="#455A64" stroke-width="6"/>'
            f'<path d="M{w-18} {size/2-12} L{w-2} {size/2} L{w-18} {size/2+12} Z" fill="#455A64"/></svg></div>')


def card(step, w, h, size):
    who, text, apis = step
    name, f, b, c = WHO[who]
    chips = "".join(f'<i style="font-size:{round(size*.66)}px">{esc(a)}</i>' for a in apis)
    star = "　★" if who == "H" else ""
    return (f'<div class="card" style="width:{w}px;height:{h}px;background:{f};border-color:{b};color:{c}">'
            f'<div class="who" style="background:{b};font-size:{round(size*.72)}px">{name}{star}</div>'
            f'<div class="txt" style="font-size:{size}px">{esc(text).replace(chr(10),"<br>")}</div><div class="api">{chips}</div></div>')


def legend():
    s = "".join(f'<span><b style="background:{WHO[k][1]};border-color:{WHO[k][2]}"></b>{WHO[k][0]}'
                f'{"（★ human in the loop）" if k == "H" else ""}</span>' for k in "PLH")
    return f'<div class="lg">{s}<span><b style="background:#fff;border-color:#2E7D32"></b>API 或工具</span></div>'


def cycle():
    bl = [("想清楚", "① 規劃<br>② 研究", "think"), ("做出來", "③ 取材<br>④ 開發", "make"),
          ("查清楚", "⑤ 驗證", "check"), ("留下來", "⑥ 知識庫<br>⑦ 迭代", "keep")]
    w, h, gap = 290, 200, 60
    parts = []
    for i, (t, s, g) in enumerate(bl):
        parts.append(box(f'<div style="font-size:38px;margin-top:-6px">{t}</div><small style="font-size:25px;height:74px">{s}</small>', g, w, h, 30))
        if i < 3:
            parts.append(arrow(gap))
    total = 4 * w + 3 * gap
    x1, x2 = w / 2, total - w / 2
    back = (f'<svg width="{total}" height="90" style="display:block"><path d="M{x2} 4 V58 H{x1} V22" fill="none" '
            f'stroke="#455A64" stroke-width="6"/><path d="M{x1-13} 26 L{x1} 4 L{x1+13} 26 Z" fill="#455A64"/>'
            f'<rect x="{total/2-190}" y="30" width="380" height="54" rx="10" fill="#fff"/>'
            f'<text x="{total/2}" y="66" text-anchor="middle" font-size="27" font-weight="700" fill="#1a1a1a" '
            f'font-family="{FONT}">失敗寫成規則，回到規劃</text></svg>')
    return page("課程循環", '<div class="row">' + "".join(parts) + "</div>" + back, total + 72), total + 72, 366


def resource_map():
    rows = [("③ 取材　⑦ 迭代", "1 文獻雷達", "每月自動找新論文", "think"),
            ("① 規劃　② 研究<br>④ 開發　⑤ 驗證", "2 萃取管線", "讀論文、抽數字、查核", "make"),
            ("⑥ 知識庫", "3 知識庫建置", "讓 AI 和自己接得下去", "keep"),
            ("每一段都用得到", "4 資源清單", "工具、API、範本", "check")]
    w, h, vg, ga = 350, 130, 26, 100
    total_h = 4 * h + 3 * vg
    ys = [i * (h + vg) + h / 2 for i in range(4)]
    root = box('<div style="font-size:34px">0 課程全貌</div><small style="font-size:24px">從 README 開始</small>', "root", w, h, 30)
    lines = "".join(f'<path d="M0 {total_h/2} H50 V{y} H{ga-16}" fill="none" stroke="#455A64" stroke-width="6"/>'
                    f'<path d="M{ga-20} {y-12} L{ga-2} {y} L{ga-20} {y+12} Z" fill="#455A64"/>' for y in ys)
    svg = f'<svg width="{ga}" height="{total_h}" style="flex:none">{lines}</svg>'
    body = "".join(f'<div class="row" style="margin-bottom:{vg if i < 3 else 0}px">'
                   + box(f'<div style="font-size:26px">{a}</div>', "gold", w, h, 26) + arrow(90)
                   + box(f'<div style="font-size:30px">{b}</div><small style="font-size:22px">{c}</small>', g, w, h, 30)
                   + "</div>" for i, (a, b, c, g) in enumerate(rows))
    W = w + ga + w + 90 + w + 72
    return (page("課程與資源的關係", f'<div class="row"><div style="flex:none">{root}</div>{svg}<div>{body}</div></div>', W), W, total_h + 72)


def overview():
    cw, ch, ag, lw = 222, 214, 30, 170
    rows = ""
    for name, g, steps in STAGES:
        f, b, c = GROUP[g]
        cells = ""
        for i, s in enumerate(steps):
            cells += (arrow(ag, 30) if i else "") + card(s, cw, ch, 21)
        rows += (f'<div class="row" style="margin-bottom:16px"><div class="box" style="width:{lw}px;height:{ch}px;'
                 f'background:{f};border-color:{b};color:{c};font-size:31px;flex:none;margin-right:18px">{esc(name)}</div>{cells}</div>')
    W = lw + 18 + 6 * cw + 5 * ag + 72
    head = ('<h1>各段細流：哪裡用程式、哪裡用 LLM、哪裡要人</h1>'
            '<p class="sub">建議流程。千篇萃取案當時沒有全部做到，有些做法是事後才整理出來的。</p>')
    body = head + f'<div style="margin-bottom:22px">{legend()}</div>' + rows
    return page("各段細流", body, W), W, 7 * (ch + 16) + 246


def stage(i):
    name, g, steps = STAGES[i]
    cw, ch, ag = 250, 270, 36
    f, b, c = GROUP[g]
    W = 6 * cw + 5 * ag + 72
    cells = "".join((arrow(ag, 40) if k else "") + card(s, cw, ch, 27) for k, s in enumerate(steps))
    head = (f'<div class="row" style="justify-content:space-between;margin-bottom:24px"><div class="box" style="width:230px;'
            f'height:80px;background:{f};border-color:{b};color:{c};font-size:38px">{esc(name)}</div>{legend()}</div>')
    return page(name, head + f'<div class="row">{cells}</div>', W), W, 80 + 24 + ch + 72


def main():
    browser = next((b for b in BROWSERS if os.path.exists(b)), None)
    if not browser:
        sys.exit("Chrome or Edge not found")
    jobs = {"01_cycle": cycle(), "02_resources": resource_map(), "03_flow_overview": overview()}
    for i, (name, _, _) in enumerate(STAGES):
        jobs[f"04_flow_{i + 1}_" + SLUG[i]] = stage(i)
    for stem, (doc, w, h) in jobs.items():
        p = OUT / f"{stem}.html"
        p.write_text(doc, encoding="utf-8")
        png = OUT / f"{stem}.png"
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                        f"--window-size={int(w)},{int(h)}", f"--screenshot={png}", p.as_uri()],
                       check=True, capture_output=True, timeout=120)
        print(stem, int(w), int(h), png.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
