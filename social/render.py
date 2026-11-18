"""Render carousel slides (1080x1350 JPEG) from slide specs with headless Chromium.

Each post is a list of slide dicts: {"kind": ..., ...fields}. Every slide shares the
same brand frame (logo bar, category chip, handle, page counter). Long text is
shrunk to fit by a small script before the screenshot, so a long briefing never
overflows the frame.
"""
from __future__ import annotations

import html
import io
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"
MARK_SVG = (HERE / "mark.svg").read_text(encoding="utf-8")
W, H = 1080, 1350

CATEGORY_COLORS = {
    "Agents": "#2DD4BF", "Science": "#34D399", "World Models": "#60A5FA",
    "Architecture": "#A78BFA", "Interpretability": "#F472B6", "Robotics": "#FBBF24",
    "Evaluation": "#FB923C", "Infrastructure": "#38BDF8", "Training": "#C084FC",
}


def e(s) -> str:
    return html.escape(str(s or ""), quote=True)


CSS = f"""
@font-face {{ font-family: Sora; src: url('{(FONTS / "Sora.ttf").as_uri()}'); font-weight: 100 900; }}
@font-face {{ font-family: Jakarta; src: url('{(FONTS / "PlusJakartaSans.ttf").as_uri()}'); font-weight: 200 800; }}
@font-face {{ font-family: Mono; src: url('{(FONTS / "JetBrainsMono.ttf").as_uri()}'); font-weight: 100 800; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #000; }}
.slide {{
  width: {W}px; height: {H}px; position: relative; overflow: hidden;
  background:
    radial-gradient(900px 700px at 100% -10%, rgba(45,212,191,.22), transparent 60%),
    radial-gradient(700px 600px at -10% 110%, rgba(245,158,11,.12), transparent 60%),
    linear-gradient(160deg, #0B1120 0%, #0E1628 55%, #111A2B 100%);
  color: #E5E9F0; font-family: Jakarta, sans-serif;
  display: flex; flex-direction: column; padding: 76px 84px 70px;
}}
.slide::before {{
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background-image: radial-gradient(rgba(148,163,184,.13) 1.4px, transparent 1.6px);
  background-size: 36px 36px;
  mask-image: linear-gradient(180deg, rgba(0,0,0,.9), rgba(0,0,0,.15));
}}
.top, .foot, .body {{ position: relative; z-index: 1; }}
.wm {{ position: absolute; right: -230px; bottom: 40px; width: 700px; height: 700px; z-index: 0; opacity: .8; }}
.wm.small {{ width: 460px; height: 460px; right: -170px; bottom: 60px; opacity: .45; }}
.top {{ display: flex; align-items: center; gap: 16px; height: 56px; }}
.top svg {{ width: 52px; height: 52px; border-radius: 14px; }}
.brand {{ font-family: Sora; font-weight: 800; font-size: 27px; letter-spacing: -.02em; }}
.spacer {{ flex: 1; }}
.chip {{ font-family: Mono; font-size: 21px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
  padding: 10px 18px; border-radius: 999px; border: 2px solid var(--c); color: var(--c); background: rgba(15,23,42,.6); }}
.body {{ flex: 1; display: flex; flex-direction: column; justify-content: center; min-height: 0; padding: 36px 0 24px; }}
.foot {{ display: flex; align-items: center; height: 44px; font-family: Mono; font-size: 22px; color: #94A3B8; }}
.foot .swipe {{ color: #2DD4BF; font-weight: 700; margin-right: 26px; }}
.kicker {{ font-family: Mono; font-weight: 700; font-size: 25px; letter-spacing: .14em; text-transform: uppercase; color: #2DD4BF; margin-bottom: 30px; }}
.kicker.amber {{ color: #FBBF24; }}
h1 {{ font-family: Sora; font-weight: 800; letter-spacing: -.035em; line-height: 1.03; font-size: 104px; }}
h2 {{ font-family: Sora; font-weight: 800; letter-spacing: -.03em; line-height: 1.1; font-size: 60px; margin-bottom: 30px; }}
.sub {{ font-size: 38px; line-height: 1.38; color: #A6B1C4; margin-top: 36px; font-weight: 500; }}
.p {{ font-size: 38px; line-height: 1.46; color: #D5DCE7; font-weight: 500; }}
.hl {{ color: #2DD4BF; }}
.meta {{ margin-top: 44px; display: flex; gap: 14px; flex-wrap: wrap; }}
.pill {{ font-family: Mono; font-size: 22px; font-weight: 600; padding: 10px 18px; border-radius: 12px; background: rgba(45,212,191,.12); color: #5EEAD4; }}
.pill.amber {{ background: rgba(245,158,11,.14); color: #FCD34D; }}
.pill.violet {{ background: rgba(124,58,237,.2); color: #C4B5FD; }}
.idxnum {{ font-family: Mono; font-weight: 800; font-size: 150px; line-height: 1; color: transparent;
  -webkit-text-stroke: 3px #2DD4BF; margin-bottom: 34px; }}
.idea {{ font-family: Sora; font-weight: 700; font-size: 56px; line-height: 1.22; letter-spacing: -.02em; }}
.nums {{ display: flex; flex-direction: column; gap: 26px; }}
.num {{ border-left: 6px solid #F59E0B; padding: 6px 0 6px 30px; }}
.num b {{ display: block; font-family: Sora; font-weight: 800; font-size: 70px; letter-spacing: -.03em; color: #FCD34D; line-height: 1.05; }}
.num span {{ font-size: 32px; color: #C9D2DF; line-height: 1.35; }}
.tag {{ font-family: Mono; font-size: 19px; font-weight: 700; letter-spacing: .08em; color: #FDA4AF; border: 2px solid #FDA4AF;
  border-radius: 8px; padding: 3px 9px; margin-left: 12px; vertical-align: middle; }}
.bigstat {{ font-family: Sora; font-weight: 800; font-size: 170px; letter-spacing: -.05em; line-height: 1; color: #FCD34D; }}
.statlabel {{ font-family: Sora; font-weight: 700; font-size: 50px; line-height: 1.22; margin-top: 30px; letter-spacing: -.02em; }}
.from {{ margin-top: 40px; font-size: 30px; color: #94A3B8; line-height: 1.4; }}
.q {{ font-family: Sora; font-weight: 800; font-size: 56px; line-height: 1.16; letter-spacing: -.025em; margin-bottom: 40px; }}
.opts {{ display: flex; flex-direction: column; gap: 18px; }}
.opt {{ display: flex; gap: 22px; align-items: flex-start; padding: 22px 26px; border-radius: 20px;
  background: rgba(17,26,43,.85); border: 2px solid #233049; font-size: 33px; line-height: 1.3; font-weight: 600; }}
.opt i {{ font-style: normal; font-family: Mono; font-weight: 800; color: #2DD4BF; min-width: 34px; }}
.opt.right {{ border-color: #22C55E; background: rgba(22,163,74,.16); }}
.opt.right i {{ color: #4ADE80; }}
.opt.dim {{ opacity: .38; }}
.explain {{ margin-top: 34px; font-size: 33px; line-height: 1.45; color: #C9D2DF; }}
.term {{ font-family: Sora; font-weight: 800; font-size: 84px; letter-spacing: -.035em; line-height: 1.06; color: #5EEAD4; }}
.def {{ font-size: 44px; line-height: 1.42; margin-top: 38px; font-weight: 500; color: #E5E9F0; }}
.item {{ display: flex; flex-direction: column; gap: 20px; }}
.item .n {{ font-family: Mono; font-weight: 800; font-size: 30px; color: #FBBF24; letter-spacing: .1em; }}
.item h3 {{ font-family: Sora; font-weight: 800; font-size: 74px; line-height: 1.07; letter-spacing: -.03em; }}
.list {{ display: flex; flex-direction: column; gap: 22px; }}
.li {{ display: flex; gap: 20px; font-size: 34px; line-height: 1.35; font-weight: 600; }}
.li::before {{ content: "→"; color: #2DD4BF; font-family: Mono; font-weight: 800; }}
.src {{ margin-top: 40px; padding-top: 30px; border-top: 2px solid #233049; font-size: 25px; color: #94A3B8; line-height: 1.5; }}
.src b {{ color: #C9D2DF; }}
.cta {{ margin-top: 42px; display: inline-flex; align-self: flex-start; align-items: center; gap: 14px; font-family: Sora; font-weight: 800; font-size: 36px;
  padding: 24px 34px; border-radius: 22px; background: linear-gradient(135deg, #14B8A6, #0F766E); color: #fff; box-shadow: 0 18px 50px -18px rgba(20,184,166,.7); }}
"""

FIT_JS = """
() => {
  for (const s of document.querySelectorAll('.slide')) {
    const body = s.querySelector('.body');
    const fits = [...s.querySelectorAll('.fit, .fit *')].filter(n => n.childElementCount === 0 || n.classList.contains('fit'));
    let guard = 0;
    while (body.scrollHeight > body.clientHeight + 1 && guard++ < 60) {
      for (const n of fits) {
        const fs = parseFloat(getComputedStyle(n).fontSize);
        if (fs > 22) n.style.fontSize = (fs * 0.95) + 'px';
      }
    }
    s.dataset.overflow = body.scrollHeight > body.clientHeight + 1 ? '1' : '0';
  }
}
"""


def _chip(cat: str | None, classic: bool = False) -> str:
    if not cat:
        return ""
    c = "#C4B5FD" if classic else CATEGORY_COLORS.get(cat, "#2DD4BF")
    return f'<span class="chip" style="--c:{c}">{e(cat)}</span>'


def _pills(pills) -> str:
    out = []
    for p in pills or []:
        if isinstance(p, dict):
            out.append(f'<span class="pill {e(p.get("tone", ""))}">{e(p["text"])}</span>')
        else:
            out.append(f'<span class="pill">{e(p)}</span>')
    return f'<div class="meta">{"".join(out)}</div>' if out else ""


def _body(s: dict) -> str:
    k = s["kind"]
    if k == "cover":
        return (f'<div class="kicker">{e(s.get("kicker"))}</div>'
                f'<h1 class="fit">{e(s["title"])}</h1>'
                + (f'<div class="sub fit">{e(s["sub"])}</div>' if s.get("sub") else "")
                + _pills(s.get("pills")))
    if k == "text":
        return (f'<div class="kicker {e(s.get("tone", ""))}">{e(s.get("kicker"))}</div>'
                + (f'<h2 class="fit">{e(s["heading"])}</h2>' if s.get("heading") else "")
                + f'<div class="p fit">{e(s["text"])}</div>')
    if k == "idea":
        return (f'<div class="kicker">{e(s.get("kicker", "Key idea"))}</div>'
                f'<div class="idxnum">{e(s["n"])}</div><div class="idea fit">{e(s["text"])}</div>')
    if k == "numbers":
        rows = "".join(
            f'<div class="num"><b>{e(n["value"])}{"<span class=tag>REPORTED</span>" if not n.get("verified", True) else ""}</b>'
            f'<span>{e(n["label"])}</span></div>' for n in s["items"])
        return f'<div class="kicker amber">{e(s.get("kicker", "By the numbers"))}</div><div class="nums fit">{rows}</div>'
    if k == "stat":
        tag = "<span class=tag>REPORTED</span>" if not s.get("verified", True) else ""
        return (f'<div class="kicker amber">{e(s.get("kicker"))}</div>'
                f'<div class="bigstat fit">{e(s["value"])}</div>'
                f'<div class="statlabel fit">{e(s["label"])}{tag}</div>'
                f'<div class="from fit">{e(s.get("from"))}</div>')
    if k in ("quiz_q", "quiz_a"):
        opts = []
        for i, o in enumerate(s["options"]):
            cls = ""
            if k == "quiz_a":
                cls = "right" if i == s["answer"] else "dim"
            opts.append(f'<div class="opt {cls}"><i>{"ABCD"[i]}</i><span>{e(o)}</span></div>')
        extra = f'<div class="explain fit">{e(s["explain"])}</div>' if k == "quiz_a" else ""
        return (f'<div class="kicker {"amber" if k == "quiz_q" else ""}">{e(s.get("kicker"))}</div>'
                f'<div class="q fit">{e(s["question"])}</div><div class="opts fit">{"".join(opts)}</div>{extra}')
    if k == "term":
        return (f'<div class="kicker">{e(s.get("kicker", "Term to know"))}</div>'
                f'<div class="term fit">{e(s["term"])}</div><div class="def fit">{e(s["definition"])}</div>'
                + (f'<div class="from fit">From: {e(s["from"])}</div>' if s.get("from") else ""))
    if k == "brief_item":
        return (f'<div class="item"><div class="n">{e(s["n"])}</div>'
                f'<h3 class="fit">{e(s["title"])}</h3><div class="sub fit">{e(s["tagline"])}</div></div>'
                + _pills(s.get("pills")))
    if k == "cta":
        items = "".join(f'<div class="li">{e(x)}</div>' for x in s.get("bullets", []))
        src = ""
        if s.get("sources"):
            src = '<div class="src fit"><b>Sources</b><br>' + "<br>".join(e(x) for x in s["sources"]) + "</div>"
        return (f'<div class="kicker">{e(s.get("kicker", "Keep going"))}</div>'
                f'<h2 class="fit">{e(s["heading"])}</h2><div class="list fit">{items}</div>'
                f'<div class="cta">{e(s.get("button", "Play free — link in bio"))}</div>{src}')
    raise ValueError(f"unknown slide kind {k}")


WATERMARK = ('<svg class="wm{cls}" viewBox="0 0 64 64"><path d="M32 11 L37.5 26.5 L53 32 L37.5 37.5 L32 53 L26.5 37.5 L11 32 L26.5 26.5 Z" '
             'fill="rgba(45,212,191,.06)" stroke="rgba(45,212,191,.3)" stroke-width=".35"/></svg>')
BIG_MARK_KINDS = {"cover", "brief_item", "stat", "term", "cta", "idea"}


def slide_html(s: dict, i: int, n: int, handle: str, app_name: str) -> str:
    last = i == n
    wm = WATERMARK.format(cls="" if s["kind"] in BIG_MARK_KINDS else " small")
    swipe = "" if last else '<span class="swipe">SWIPE →</span>'
    return (f'<section class="slide" id="s{i}">{wm}<div class="top">{MARK_SVG}<span class="brand">{e(app_name)}</span>'
            f'<span class="spacer"></span>{_chip(s.get("category"), s.get("classic", False))}</div>'
            f'<div class="body">{_body(s)}</div>'
            f'<div class="foot"><span>{e(handle)}</span><span class="spacer"></span>{swipe}<span>{i}/{n}</span></div></section>')


def page_html(slides: list[dict], handle: str, app_name: str) -> str:
    n = len(slides)
    secs = "".join(slide_html(s, i + 1, n, handle, app_name) for i, s in enumerate(slides))
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{secs}</body></html>"


class Renderer:
    """Keeps one browser open for the whole week's posts."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._page = self._browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        return self

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()

    def render(self, slides: list[dict], out_dir: Path, handle: str, app_name: str, quality: int = 88) -> list[str]:
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp = out_dir / "_page.html"
        tmp.write_text(page_html(slides, handle, app_name), encoding="utf-8")
        self._page.goto(tmp.as_uri())
        self._page.evaluate("document.fonts.ready")
        self._page.evaluate(FIT_JS)
        names, overflow = [], []
        for i in range(1, len(slides) + 1):
            el = self._page.locator(f"#s{i}")
            if el.get_attribute("data-overflow") == "1":
                overflow.append(i)
            png = el.screenshot(type="png")
            name = f"{i:02d}.jpg"
            Image.open(io.BytesIO(png)).convert("RGB").save(out_dir / name, "JPEG", quality=quality, optimize=True)  # baseline JPEG: safest for Meta's fetcher
            names.append(name)
        tmp.unlink()
        if overflow:
            print(f"  warning: text still tight on slides {overflow} in {out_dir.name}")
        return names
