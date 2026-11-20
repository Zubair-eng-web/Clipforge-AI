"""FFmpeg audio mixing: background music + original audio.
The video stream is COPIED (never re-encoded): same picture, resolution, fps, cuts and duration."""
from backend.video_processing.ffmpeg_service import _run

SR = 44100
_STEREO = f"aresample={SR},aformat=sample_fmts=fltp:channel_layouts=stereo"


def build_filter(dur, has_orig, orig_on, orig_vol, tracks):
    """Returns (extra input args, filter_complex, number of mixed sources).
    tracks: dicts with path, tdur, volume(0..1), start, trim_in, trim_out, fade_in, fade_out, loop."""
    inputs, parts, labels = [], [], []
    if orig_on and has_orig and orig_vol > 0:
        parts.append(f"[0:a:0]{_STEREO},volume={orig_vol:.3f}[o]")
        labels.append("[o]")
    idx = 1
    for t in tracks:
        start = min(max(float(t["start"]), 0.0), dur)
        avail = dur - start
        tdur = float(t["tdur"])
        if avail < 0.05 or float(t["volume"]) <= 0 or tdur <= 0:
            continue
        ti = max(float(t["trim_in"]), 0.0)
        to = float(t["trim_out"]) if t.get("trim_out") else tdur
        to = min(to, tdur)
        seg = to - ti
        if seg < 0.05:
            continue
        trim_needed = ti > 0.001 or to < tdur - 0.05
        opts, chain = [], [_STEREO]
        if t["loop"] and not trim_needed:
            opts = ["-stream_loop", "-1"]  # loops the whole file, no memory used
            play = avail
        else:
            if trim_needed:
                chain += [f"atrim=start={ti:.3f}:end={to:.3f}", "asetpts=PTS-STARTPTS"]
            if t["loop"]:
                chain.append(f"aloop=loop=-1:size={max(int(seg * SR), 1)}")  # loops only the trimmed part
                play = avail
            else:
                play = min(avail, seg)
        chain += [f"atrim=duration={play:.3f}", "asetpts=PTS-STARTPTS"]
        fi = min(float(t["fade_in"]), play / 2)
        fo = min(float(t["fade_out"]), play / 2)
        if fi > 0.01:
            chain.append(f"afade=t=in:st=0:d={fi:.3f}")
        if fo > 0.01:
            chain.append(f"afade=t=out:st={play - fo:.3f}:d={fo:.3f}")
        chain.append(f"volume={float(t['volume']):.3f}")
        if start > 0.001:
            ms = int(round(start * 1000))
            chain.append(f"adelay={ms}|{ms}")
        inputs += [*opts, "-i", str(t["path"])]
        parts.append(f"[{idx}:a]" + ",".join(chain) + f"[m{idx}]")
        labels.append(f"[m{idx}]")
        idx += 1
    n = len(labels)
    if idx == 1:  # no music track made it into the mix
        raise ValueError("Nothing audible: add a music track with volume above 0")
    tail = f"apad=whole_dur={dur:.3f},alimiter=limit=0.97[aout]"
    if n == 1:
        parts.append(f"{labels[0]}{tail}")
    else:
        parts.append("".join(labels) + f"amix=inputs={n}:duration=longest:normalize=0:dropout_transition=0," + tail)
    return inputs, ";".join(parts), n


def codec_args(codec: str, kbps: int):
    lib = {"aac": "aac", "mp3": "libmp3lame", "opus": "libopus"}.get(codec, "aac")
    return ["-c:a", lib, "-b:a", f"{int(kbps)}k"]


def mix_audio(src, dst, dur, has_orig, orig_on, orig_vol, tracks, codec="aac", kbps=192, limit=None, on_progress=None):
    inputs, fc, _n = build_filter(dur, has_orig, orig_on, orig_vol, tracks)
    out_dur = min(dur, limit) if limit else dur
    args = ["-i", str(src), *inputs, "-filter_complex", fc, "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", *codec_args(codec, kbps), "-t", f"{out_dur:.3f}", "-movflags", "+faststart", str(dst)]
    _run(args, out_dur, on_progress)
    return out_dur