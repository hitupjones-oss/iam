"""Picture: render every timeline event to a graded 1920x1080 23.976 segment,
concatenate, then composite typography + grain and mux the final mix.

Outputs (exports/):
  IAM_I_AM_THE_ASSET_v01_REVIEW.mp4        H.264, timecode + shot burn-in
  IAM_I_AM_THE_ASSET_v01_CLEAN_REVIEW.mp4  H.264, no burn-in

Sources are 480p/400p Higgsfield reference renders upscaled to 1080 for review.
This is NOT a 4K or native-HD master.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edl  # noqa: E402

ROOT = edl.ROOT
BUILD = os.path.join(ROOT, "build", "video")
EXPORTS = os.path.join(ROOT, "exports")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FPS = f"{edl.FPS_NUM}/{edl.FPS_DEN}"

# Grades: restrained per-section looks (see brief "COLOR DIRECTION").
# Talent stays slightly under; blacks get a small lift so they never clip to
# featureless; no orange skin, no sci-fi blue shadows.
LIFT = "curves=all='0/0.018 0.25/0.22 0.75/0.73 1/0.955'"
GRADES = {
    "identity_amber": f"{LIFT},colorbalance=rs=0.015:bs=-0.012:rm=0.01:bm=-0.015:rh=-0.01,eq=saturation=0.92:gamma=0.96",
    "identity_teal": f"{LIFT},colorbalance=rs=0.01:bs=0.01:rh=0.012:bh=-0.01,eq=saturation=0.88:gamma=0.96",
    "identity_mixed": f"{LIFT},colorbalance=bs=0.015:rh=0.01,eq=saturation=0.9:gamma=0.97",
    "identity_crowd": f"{LIFT},colorbalance=bs=0.01:bh=0.01,eq=saturation=0.9",
    "problem_commercial": "curves=all='0/0.02 0.5/0.52 0.9/0.9 1/0.96',eq=contrast=1.05:saturation=0.95:brightness=0.012",
    "problem_billboard": f"{LIFT},colorbalance=bs=0.01,eq=saturation=0.9",
    "inversion_steel": f"{LIFT},colorbalance=rs=-0.02:bs=0.035:rm=-0.01:bm=0.015:rh=-0.01:bh=0.01,eq=saturation=0.74:gamma=0.98",
    "inversion_cyan": f"{LIFT},colorbalance=rs=-0.015:bs=0.025:bh=0.005,eq=saturation=0.8",
    "iam_split": f"{LIFT},colorbalance=rs=-0.02:bs=0.03:rh=0.03:bh=-0.02,eq=saturation=0.88:gamma=0.97",
    "machine_warm": f"{LIFT},colorbalance=rs=-0.01:bs=0.02:rh=0.025:bh=-0.02,eq=saturation=0.85",
    "machine_steel": f"{LIFT},colorbalance=rs=-0.02:bs=0.03:rh=0.01,eq=saturation=0.78",
    "close_tungsten": f"{LIFT},colorbalance=rs=0.01:bs=-0.01:rh=0.02:bh=-0.015,eq=saturation=0.86:gamma=0.95",
    "close_stage": f"{LIFT},colorbalance=rh=0.015:bh=-0.01,eq=saturation=0.85",
}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(" ".join(cmd))
        print(r.stderr[-3000:])
        raise SystemExit(r.returncode)


def segment_filter(s, nframes):
    shot = s["shot"]
    src = os.path.join(edl.VIDEO_DIR, edl.SHOTS[shot] + ".mp4")
    fx = s["fx"]
    sp = s["speed"]
    span = s["dur"] * sp + 0.25
    f = [f"trim=start={s['src_in']:.4f}:duration={span:.4f}", "setpts=PTS-STARTPTS"]
    if sp < 0.999:
        f.append(f"setpts=PTS/{sp:.5f}")
    f.append(f"fps={FPS}")
    # 736x400 sources are wider than 16:9 -> centre-crop first
    f.append("crop='min(iw,ih*16/9)':'min(ih,iw*9/16)'")
    punch = fx.get("punch")
    if punch:
        cx, cy = fx.get("cx", 0.5), fx.get("cy", 0.5)
        f.append(f"crop=iw/{punch}:ih/{punch}:'max(0,min(iw-ow,{cx}*iw-ow/2))':'max(0,min(ih-oh,{cy}*ih-oh/2))'")
    push = fx.get("push")
    if push:
        # slow push-in across the shot; zoompan on a 2x raster keeps it smooth
        f.append("scale=3840:2160:flags=lanczos")
        z = f"1+{push - 1:.4f}*on/{max(1, nframes - 1)}"
        f.append(f"zoompan=z='{z}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1920x1080:fps={FPS}")
    else:
        f.append("scale=1920:1080:flags=lanczos")
    f.append("unsharp=5:5:0.45:5:5:0.0")
    f.append("setsar=1")
    if s["grade"]:
        f.append(GRADES[s["grade"]])
    if fx.get("billboard_die"):
        # natural dim in the source (2.5-3.75s), then two flickers and the light dies
        t0 = s["dur"]
        f.append("eq=brightness='-0.10*(between(t,%.3f,%.3f)+between(t,%.3f,%.3f))':eval=frame"
                 % (t0 - 0.95, t0 - 0.90, t0 - 0.78, t0 - 0.70))
        f.append(f"fade=t=out:st={t0 - 0.55:.3f}:d=0.5")
    if fx.get("bloom"):
        # warm halation on the stage light only; done in RGB so chroma isn't screened
        f.append("format=gbrp,split[a][b];[b]lutrgb=r='if(gt(val,200),val,0)':g='if(gt(val,200),val,0)':"
                 "b='if(gt(val,200),val,0)',gblur=sigma=26,colorchannelmixer=rr=1.0:gg=0.78:bb=0.55[h];"
                 "[a][h]blend=all_mode=screen:all_opacity=0.28,format=yuv420p")
    f.append("vignette=angle=PI/5.5")
    f.append("tpad=stop_mode=clone:stop_duration=3")
    f.append("format=yuv420p")
    return src, ",".join(f)


def render_segments(tl):
    os.makedirs(BUILD, exist_ok=True)
    seg_files = []
    t_frames = 0
    only = None
    for a in sys.argv:
        if a.startswith("--only="):
            only = {int(x) for x in a.split("=", 1)[1].split(",")}
    for i, s in enumerate(tl.shots):
        f0, f1 = edl.frames(s["start"]), edl.frames(s["end"])
        n = f1 - f0
        out = os.path.join(BUILD, f"seg_{i:02d}_{s['shot']}.mp4")
        if only is not None and i not in only and os.path.exists(out):
            seg_files.append(out)
            t_frames += n
            continue
        if s["shot"] in edl.SHOTS:
            src, vf = segment_filter(s, n)
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", src, "-filter_complex", vf]
        else:
            cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                   f"color=c=0x0A0A0A:s=1920x1080:r={FPS}", "-vf", "format=yuv420p"]
        cmd += ["-frames:v", str(n), "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "9",
                "-pix_fmt", "yuv420p", "-r", FPS, "-video_track_timescale", "24000", out]
        run(cmd)
        seg_files.append(out)
        t_frames += n
        print(f"  seg {i:02d} {s['shot']:>5} {n:4d}f  x{s['speed']:.2f}")
    lst = os.path.join(BUILD, "concat.txt")
    with open(lst, "w") as fh:
        for p in seg_files:
            fh.write(f"file '{p}'\n")
    picture = os.path.join(BUILD, "picture.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", picture])
    print(f"  picture: {t_frames} frames ({t_frames / edl.FPS:.3f}s)")
    return picture, t_frames


def gfx_inputs_and_filters(tl, layers):
    """Overlay chain for every graphics layer: opacity fade in/out + 16px rise."""
    by_comp = {}
    for l in layers:
        by_comp.setdefault(l["comp"], []).append(l)
    inputs, chain = [], []
    idx = 2  # 0 = picture, 1 = audio
    last = "[0:v]"
    k = 0
    for g in tl.gfx:
        for l in by_comp[g["comp"]]:
            a = g["start"] + l["t_in"]
            b = g["end"]
            inputs += ["-loop", "1", "-framerate", FPS, "-t", f"{b + 0.1:.3f}", "-i", os.path.join(ROOT, l["file"])]
            fades = f"fade=t=in:st={a:.3f}:d={l['d_in']:.3f}:alpha=1"
            if not l["hold_to_end"]:
                fades += f",fade=t=out:st={b - l['d_out']:.3f}:d={l['d_out']:.3f}:alpha=1"
            chain.append(f"[{idx}:v]format=rgba,{fades}[g{k}]")
            y = "0" if not l["dy"] else f"'{l['dy']}*pow(1-min(1,max(0,(t-{a:.3f})/{l['d_in']:.3f})),3)'"
            chain.append(f"{last}[g{k}]overlay=x=0:y={y}:eval=frame:enable='between(t,{a:.3f},{b:.3f})'[v{k}]")
            last = f"[v{k}]"
            idx += 1
            k += 1
    return inputs, chain, last


def burnin(tl):
    """Review burn-in: version, 23.976 NDF timecode, current shot id."""
    parts = [f"drawtext=fontfile={FONT}:fontsize=26:fontcolor=white@0.85:box=1:boxcolor=black@0.55:boxborderw=8:"
             f"x=w-tw-36:y=30:timecode='00\\:00\\:00\\:00':rate={FPS}",
             f"drawtext=fontfile={FONT}:fontsize=22:fontcolor=white@0.8:box=1:boxcolor=black@0.55:boxborderw=8:"
             f"x=36:y=30:text='IAM  I AM THE ASSET  v01 REVIEW  |  REF-GRADE SOURCES (480p UPSCALE)'"]
    for s in tl.shots:
        label = f"SHOT {s['shot']}" if s["shot"] in edl.SHOTS else "BLACK"
        if s["speed"] < 0.999:
            label += f"  {s['speed'] * 100:.0f}%"
        parts.append(f"drawtext=fontfile={FONT}:fontsize=22:fontcolor=white@0.8:box=1:boxcolor=black@0.55:"
                     f"boxborderw=8:x=36:y=h-60:text='{label}':enable='between(t,{s['start']:.3f},{s['end'] - 0.001:.3f})'")
    return ",".join(parts)


def final(tl, picture, nframes, mix, layers):
    os.makedirs(EXPORTS, exist_ok=True)
    g_inputs, g_chain, last = gfx_inputs_and_filters(tl, layers)
    grain = "noise=c0s=5:c0f=t+u"
    outs = {}
    for kind in ("CLEAN_REVIEW", "REVIEW"):
        out = os.path.join(EXPORTS, f"IAM_I_AM_THE_ASSET_v01_{kind}.mp4")
        tail = f"{last}{grain}"
        if kind == "REVIEW":
            tail += "," + burnin(tl)
        tail += ",format=yuv420p[out]"
        fc = ";".join(g_chain + [tail])
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", picture, "-i", mix] + g_inputs + [
            "-filter_complex", fc, "-map", "[out]", "-map", "1:a",
            "-frames:v", str(nframes), "-r", FPS,
            "-c:v", "libx264", "-preset", "slow", "-b:v", "16M", "-maxrate", "24M", "-bufsize", "32M",
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-colorspace", "bt709", "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
            "-movflags", "+faststart", "-shortest", out]
        run(cmd)
        outs[kind] = out
        print("  wrote", os.path.relpath(out, ROOT))
    return outs


if __name__ == "__main__":
    tl = edl.build()
    layers = json.load(open(os.path.join(ROOT, "media", "03_GFX", "layers.json")))
    mix = os.path.join(ROOT, "media", "02_AUDIO", "MIX", "IAM_v01_MIX.wav")
    if "--segments-only" in sys.argv or not os.path.exists(os.path.join(BUILD, "picture.mp4")) or "--rebuild" in sys.argv:
        picture, n = render_segments(tl)
    else:
        picture = os.path.join(BUILD, "picture.mp4")
        n = sum(edl.frames(s["end"]) - edl.frames(s["start"]) for s in tl.shots)
    if "--segments-only" not in sys.argv:
        final(tl, picture, n, mix, layers)
