"""Caption lines from word timestamps, SRT export and ASS (styled) export."""
SENTENCE_END = (".", "!", "?", "\u061f", "\u06d4", "\u2026")


def build_lines(words, max_chars=28, max_words=6, max_gap=0.7, min_len=0.35):
    """words: [{start, end, word}] -> lines: [{start, end, text, words}]"""
    lines, cur = [], []

    def flush():
        if cur:
            lines.append({
                "start": cur[0]["start"],
                "end": cur[-1]["end"],
                "text": " ".join(w["word"] for w in cur),
                "words": list(cur),
            })
            cur.clear()

    for w in words:
        if cur:
            text_len = len(" ".join(x["word"] for x in cur)) + 1 + len(w["word"])
            gap = w["start"] - cur[-1]["end"]
            if (text_len > max_chars or len(cur) >= max_words or gap > max_gap
                    or (len(cur) >= 2 and cur[-1]["word"].endswith(SENTENCE_END))):
                flush()
        cur.append(w)
    flush()

    for i, ln in enumerate(lines):
        end = max(ln["end"], ln["start"] + min_len)
        if i + 1 < len(lines) and lines[i + 1]["start"] > ln["start"]:
            end = min(end, lines[i + 1]["start"])
        ln["end"] = round(end, 2)
    return lines


def _srt_time(t: float) -> str:
    ms = int(round(max(t, 0.0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_time(t: float) -> str:
    cs = int(round(max(t, 0.0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def to_srt(lines) -> str:
    blocks = []
    for i, ln in enumerate(lines, 1):
        blocks.append(f"{i}\n{_srt_time(ln['start'])} --> {_srt_time(ln['end'])}\n{ln['text']}\n")
    return "\n".join(blocks)


# ASS colours are &HAABBGGRR
STYLES = {
    "classic":   dict(primary="&H00FFFFFF", secondary="&H00FFFFFF", bold=0, outline=3, scale=1.0, karaoke=False),
    "bold":      dict(primary="&H0000FFFF", secondary="&H0000FFFF", bold=1, outline=4, scale=1.2, karaoke=False),
    "highlight": dict(primary="&H0000FFFF", secondary="&H00FFFFFF", bold=1, outline=4, scale=1.1, karaoke=True),
}
POSITIONS = {"bottom": 2, "center": 5, "top": 8}


def _esc(t: str) -> str:
    return t.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def _karaoke(line) -> str:
    ws = line["words"]
    parts = []
    for i, w in enumerate(ws):
        nxt = ws[i + 1]["start"] if i + 1 < len(ws) else line["end"]
        cs = max(1, int(round((nxt - w["start"]) * 100)))
        parts.append("{\\kf%d}%s" % (cs, _esc(w["word"])))
    return " ".join(parts)


def _has_valid_words(line) -> bool:
    ws = line.get("words")
    return bool(ws) and " ".join(w["word"] for w in ws) == line["text"]


def to_ass(lines, width: int, height: int, style: str = "classic", position: str = "bottom",
           font: str = "Arial", font_size=None) -> str:
    st = STYLES.get(style, STYLES["classic"])
    align = POSITIONS.get(position, 2)
    fs = int(font_size) if font_size else max(12, round(min(width, height) * 0.07 * st["scale"]))
    margin_v = 0 if position == "center" else round(height * 0.08)
    margin_lr = round(width * 0.06)
    out = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {int(width)}",
        f"PlayResY: {int(height)}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font},{fs},{st['primary']},{st['secondary']},&H00000000,&H64000000,{st['bold']},0,0,0,"
        f"100,100,0,0,1,{st['outline']},1,{align},{margin_lr},{margin_lr},{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for ln in lines:
        text = _karaoke(ln) if (st["karaoke"] and _has_valid_words(ln)) else _esc(ln["text"])
        out.append(f"Dialogue: 0,{_ass_time(ln['start'])},{_ass_time(ln['end'])},Default,,0,0,0,,{text}")
    return "\n".join(out) + "\n"