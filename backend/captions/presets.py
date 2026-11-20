"""Captions Studio: 8 presets, customization, ASS export (line / word-by-word / karaoke), VTT."""
import re
from typing import Any, Dict, List

from backend.captions.builder import _ass_time, _esc, _has_valid_words, _srt_time

FONTS = ["Arial", "Impact", "Segoe UI", "Verdana", "Georgia", "Courier New", "Comic Sans MS", "Trebuchet MS", "Tahoma"]
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# primary = text colour (and the colour a karaoke word turns into); secondary = karaoke base colour
BASE: Dict[str, Any] = dict(
    font="Arial", font_size=0, scale=1.0, primary="#FFFFFF", secondary="#FFFFFF", outline_color="#000000",
    outline=3.0, shadow=1.0, bold=True, italic=False, uppercase=False, position="bottom", align="center",
    spacing=0.0, words_per_line=6, mode="line", animation="none", offset=0.0, margin_pct=8.0,
)

PRESETS: Dict[str, Dict[str, Any]] = {
    "gaming": {"label": "Gaming", "config": dict(font="Impact", primary="#00FF66", secondary="#FFFFFF", outline=4, shadow=2,
               uppercase=True, mode="karaoke", words_per_line=4, animation="pop", scale=1.2)},
    "viral_reels": {"label": "Viral Reels", "config": dict(font="Arial", primary="#FFE600", outline=5, shadow=2,
               uppercase=True, mode="word", words_per_line=1, animation="pop", position="center", scale=1.5)},
    "cinematic": {"label": "Cinematic", "config": dict(font="Georgia", bold=False, primary="#FFFFFF", outline=1, shadow=2,
               mode="line", words_per_line=8, animation="fade", spacing=1, scale=0.85)},
    "bold_highlight": {"label": "Bold Highlight", "config": dict(font="Arial", primary="#FFE600", secondary="#FFFFFF",
               outline=4, mode="karaoke", words_per_line=5, scale=1.1)},
    "minimal": {"label": "Minimal", "config": dict(font="Segoe UI", bold=False, primary="#FFFFFF", outline=1, shadow=0,
               mode="line", words_per_line=8, scale=0.8)},
    "word_by_word": {"label": "Word-by-Word", "config": dict(font="Verdana", primary="#FFFFFF", outline=4, mode="word",
               words_per_line=1, animation="fade", position="center", scale=1.4)},
    "karaoke": {"label": "Karaoke", "config": dict(font="Arial", primary="#00D2FF", secondary="#FFFFFF", outline=4,
               mode="karaoke", words_per_line=6, scale=1.1)},
    "custom": {"label": "Custom", "config": {}},
}

_NUM = {"font_size": (0, 300), "scale": (0.4, 3.0), "outline": (0, 12), "shadow": (0, 10), "spacing": (-2, 20),
        "words_per_line": (1, 12), "offset": (-10, 10), "margin_pct": (0, 40)}
_ENUM = {"position": ("bottom", "center", "top"), "align": ("left", "center", "right"),
         "mode": ("line", "word", "karaoke"), "animation": ("none", "fade", "pop")}
_COL = ("primary", "secondary", "outline_color")
_BOOL = ("bold", "italic", "uppercase")
_ANIM = {"none": "", "fade": "{\\fad(120,120)}", "pop": "{\\fscx85\\fscy85\\t(0,140,\\fscx100\\fscy100)}"}


def resolve(preset: str, overrides: Dict[str, Any] = None) -> Dict[str, Any]:
    cfg = dict(BASE)
    cfg.update(PRESETS.get(preset, PRESETS["custom"])["config"])
    for k, v in (overrides or {}).items():
        if k == "font":
            f = re.sub(r"[^\w \-]", "", str(v))[:60].strip()
            if f:
                cfg["font"] = f
        elif k in _NUM:
            try:
                x = float(v)
            except (TypeError, ValueError):
                continue
            if x != x:
                continue
            lo, hi = _NUM[k]
            x = min(max(x, lo), hi)
            cfg[k] = int(round(x)) if k in ("font_size", "words_per_line") else x
        elif k in _ENUM:
            if v in _ENUM[k]:
                cfg[k] = v
        elif k in _COL:
            if isinstance(v, str) and HEX.match(v):
                cfg[k] = v.upper()
        elif k in _BOOL:
            cfg[k] = bool(v)
    return cfg


def list_presets() -> List[Dict[str, Any]]:
    return [{"id": k, "label": v["label"], "config": resolve(k)} for k, v in PRESETS.items()]


def _c(hexc: str) -> str:  # #RRGGBB -> &H00BBGGRR
    return ("&H00" + hexc[5:7] + hexc[3:5] + hexc[1:3]).upper()


def regroup(lines, n: int):
    """Split lines (that still have word timing) into chunks of n words."""
    n = max(1, int(n))
    out = []
    for ln in lines:
        ws = ln.get("words") if _has_valid_words(ln) else None
        if not ws or len(ws) <= n:
            out.append(ln)
            continue
        for i in range(0, len(ws), n):
            ch = ws[i:i + n]
            last = i + n >= len(ws)
            end = ln["end"] if last else (ws[i + n]["start"] if ws[i + n]["start"] > ch[0]["start"] else ch[-1]["end"])
            out.append({"start": ch[0]["start"], "end": max(end, ch[0]["start"] + 0.2),
                        "text": " ".join(w["word"] for w in ch), "words": ch})
    return out


def _events(lines, cfg):
    fix = (lambda s: s.upper()) if cfg["uppercase"] else (lambda s: s)
    ev = []
    if cfg["mode"] == "word":
        for ln in lines:
            ws = ln.get("words") if _has_valid_words(ln) else None
            if not ws:
                ev.append((ln["start"], ln["end"], _esc(fix(ln["text"]))))
                continue
            for i, w in enumerate(ws):
                end = ws[i + 1]["start"] if i + 1 < len(ws) else ln["end"]
                if end <= w["start"]:
                    end = w["end"]
                ev.append((w["start"], max(end, w["start"] + 0.15), _esc(fix(w["word"]))))
        return ev
    for ln in regroup(lines, cfg["words_per_line"]):
        if cfg["mode"] == "karaoke" and _has_valid_words(ln):
            ws, parts = ln["words"], []
            for i, w in enumerate(ws):
                nxt = ws[i + 1]["start"] if i + 1 < len(ws) else ln["end"]
                cs = max(1, int(round((nxt - w["start"]) * 100)))
                parts.append("{\\kf%d}%s" % (cs, _esc(fix(w["word"]))))
            ev.append((ln["start"], ln["end"], " ".join(parts)))
        else:
            ev.append((ln["start"], ln["end"], _esc(fix(ln["text"]))))
    return ev


def to_ass_studio(lines, width: int, height: int, studio: Dict[str, Any]) -> str:
    cfg = resolve(studio.get("preset", "custom"), studio.get("config") or {})
    overlays = studio.get("overlays") or []
    fs = int(cfg["font_size"]) or max(12, round(min(width, height) * 0.07 * cfg["scale"]))
    row = {"bottom": 0, "center": 3, "top": 6}[cfg["position"]]
    col = {"left": 1, "center": 2, "right": 3}[cfg["align"]]
    align = row + col
    margin_v = 0 if cfg["position"] == "center" else round(height * cfg["margin_pct"] / 100)
    mlr = round(width * 0.06)
    off = float(cfg["offset"])
    out = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {int(width)}", f"PlayResY: {int(height)}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{cfg['font']},{fs},{_c(cfg['primary'])},{_c(cfg['secondary'])},{_c(cfg['outline_color'])},&H64000000,"
        f"{-1 if cfg['bold'] else 0},{-1 if cfg['italic'] else 0},0,0,100,100,{cfg['spacing']},0,1,{cfg['outline']},"
        f"{cfg['shadow']},{align},{mlr},{mlr},{margin_v},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    anim = _ANIM[cfg["animation"]]
    for s, e, text in _events(lines, cfg):
        s2, e2 = max(0.0, s + off), e + off
        if e2 <= 0:
            continue
        out.append(f"Dialogue: 0,{_ass_time(s2)},{_ass_time(max(e2, s2 + 0.05))},Default,,0,0,0,,{anim}{text}")
    for o in overlays:
        an = {"top": 8, "center": 5, "bottom": 2}.get(o.get("position", "center"), 5)
        mv = 0 if an == 5 else round(height * cfg["margin_pct"] / 100)
        s, e = float(o["start"]), float(o["end"])
        out.append("Dialogue: 1,%s,%s,Default,,0,0,%d,,{\\an%d}%s" % (_ass_time(s), _ass_time(max(e, s + 0.05)), mv, an, _esc(str(o["text"]))))
    return "\n".join(out) + "\n"


def to_vtt(lines) -> str:
    blocks = ["WEBVTT\n"]
    for ln in lines:
        blocks.append(f"{_srt_time(ln['start']).replace(',', '.')} --> {_srt_time(ln['end']).replace(',', '.')}\n{ln['text']}\n")
    return "\n".join(blocks)