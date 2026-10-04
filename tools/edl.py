"""IAM — "I AM THE ASSET" — V1 edit decision list.

Single source of truth for the cut. Every other build step (picture, graphics,
audio, Premiere XML, AE script) reads the timeline computed here.

The cut is laid out VO-first: each line is placed after the previous one with
an explicit gap, and picture cuts are anchored to those VO events. Changing a
gap or a trim re-flows everything downstream.

Run directly to print the timeline:  python3 tools/edl.py
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO_DIR = os.path.join(ROOT, "media", "01_VIDEO")
VO_DIR = os.path.join(ROOT, "media", "02_AUDIO", "VO")

FPS_NUM, FPS_DEN = 24000, 1001
FPS = FPS_NUM / FPS_DEN
DURATION = 90.0
W, H = 1920, 1080

# Global VO tempo (pitch-preserving). The takes were generated at speech_rate -10;
# the 27-line script runs ~69s at that pace, which leaves too little air in 90s.
VO_TEMPO = 1.10
VO_PRE, VO_POST = 0.04, 0.12  # handles around detected speech (source seconds)

SHOTS = {
    "01": "01_ARTIST_REFLECTIVE",
    "02": "02_DIRECT_PORTRAIT_FEMALE",
    "03": "03_PINK_CANDID",
    "04": "04_INEAR_CHAIN_DETAIL",
    "05": "05_ARTIST_MANAGER_WALK",
    "06": "06_CURTAIN_CROWD",
    "07": "07_CAMPAIGN_SHOOT",
    "08": "08_CONTRACT",
    "09": "09_BILLBOARD_DARK",
    "10": "10_WAREHOUSE",
    "11": "11_PRODUCT_LAB",
    "12": "12_FOUNDER_PORTRAIT",
    "13": "13_NEW_SEAT_TABLE",
    "14": "14_ARTIST_LISTENING",
    "15": "15_MANAGER_PROFILE",
    "16": "16_PRODUCT_COLLAB",
    "17": "17_UNDERWRITE_FORM",
    "18": "18_OPERATE_COMPOUND",
    "19": "19_FINAL_PORTRAIT",
    "20": "20_STAGE_WALK",
}
SRC_LEN = 4.04  # every Higgsfield clip is 97 frames @ 24fps

# VO takes: id -> (take file, source in, source out) in take seconds, speech only.
# Boundaries come from energy detection (see media/02_AUDIO/VO/vo_regions.json)
# and were checked against a Whisper transcript (vo_words.json).
VO = {
    "01": ("VO_01", 0.43, 3.07, "I am not a post."),
    "02": ("VO_02", 0.26, 1.63, "I am not a campaign."),
    "03": ("VO_03", 0.42, 2.31, "I am not somebody's spokesperson."),
    "04": ("VO_04", 0.74, 2.82, "My name means something."),
    "05": ("VO_05", 1.65, 3.95, "My voice means something."),
    "06": ("VO_06", 1.83, 4.24, "My audience trusts something."),
    "07a": ("VO_07", 0.47, 1.28, "I am"),
    "07b": ("VO_07", 2.26, 3.16, "the asset."),
    "08": ("VO_08", 0.69, 5.71, "For decades, the business around talent has been built to monetize attention."),
    "09a": ("VO_09", 0.34, 1.17, "A campaign."),
    "09b": ("VO_09", 1.90, 2.51, "A deal."),
    "09c": ("VO_09", 3.27, 3.84, "A fee."),
    "10": ("VO_10", 1.13, 2.66, "Then it's over."),
    "11": ("VO_11", 2.09, 5.89, "But attention was never the most valuable thing you owned."),
    "12": ("VO_12", 1.15, 2.33, "Trust was."),
    "13": ("VO_13", 1.14, 6.98, "Today, almost everything required to build a company can be rented."),
    "14a": ("VO_14", 0.44, 1.31, "Operators."),
    "14b": ("VO_14", 1.93, 2.91, "Infrastructure."),
    "14c": ("VO_14", 3.58, 4.18, "Technology."),
    "15": ("VO_15", 1.46, 2.05, "Capital."),
    "16": ("VO_16", 0.41, 3.15, "Everything except the demand you already own."),
    "17": ("VO_17", 0.54, 4.89, "I am... is Intellectual Asset Management."),
    "18": ("VO_18", 0.25, 2.06, "A new seat at the talent's table."),
    "19": ("VO_19", 0.52, 5.27, "We treat intellectual property as an asset class."),
    "20": ("VO_20", 0.54, 2.41, "Management runs the career."),
    "21a": ("VO_21", 0.31, 0.88, "I am..."),
    "21b": ("VO_21", 1.67, 2.93, "builds the companies."),
    "22": ("VO_22", 1.17, 5.85, "New businesses are underwritten around intellectual property."),
    "23": ("VO_23", 0.35, 2.40, "Formed with proven operators."),
    "24": ("VO_24", 1.17, 3.24, "Built for recurring revenue."),
    "25": ("VO_25", 0.47, 3.57, "Structured so talent participates as a founder."),
    "26": ("VO_26", 0.52, 2.71, "Not rented by the business."),
    "27": ("VO_27", 0.50, 1.41, "An owner of it."),
}


def vo_len(vid):
    _, a, b, _ = VO[vid]
    return (b - a) / VO_TEMPO


class Timeline:
    def __init__(self):
        self.shots = []      # dicts: start, shot, src_in, speed?, grade, fx
        self.vo = []         # dicts: id, start, end
        self.gfx = []        # dicts: comp, start, end
        self.markers = []    # (time, name)
        self.sections = []   # (time, name)

    def add_vo(self, vid, at):
        end = at + vo_len(vid)
        self.vo.append(dict(id=vid, start=at, end=end))
        return at, end

    def cut(self, at, shot, src_in=0.0, grade=None, **fx):
        self.shots.append(dict(start=at, shot=shot, src_in=src_in, grade=grade, fx=fx))
        return at

    def section(self, at, name):
        self.sections.append((at, name))
        self.markers.append((at, name))

    def finalize(self, end):
        self.shots.sort(key=lambda s: s["start"])
        for i, s in enumerate(self.shots):
            s["end"] = self.shots[i + 1]["start"] if i + 1 < len(self.shots) else end
            s["dur"] = s["end"] - s["start"]
            if s["shot"] in SHOTS:
                avail = SRC_LEN - s["src_in"] - 0.03
                want = s["fx"].get("speed")
                auto = min(1.0, avail / s["dur"])
                s["speed"] = min(want, auto) if want else auto
            else:
                s["speed"] = 1.0
        self.end = end
        return self


def build():
    tl = Timeline()
    V = tl.add_vo

    # ---------------------------------------------------------------- IDENTITY
    tl.section(0.0, "IDENTITY")
    tl.cut(0.0, "01", src_in=0.20, grade="identity_amber")
    _, e = V("01", 0.55)
    c = tl.cut(e + 0.05, "04", src_in=0.0, grade="identity_amber")
    _, e = V("02", c + 0.40)
    c = tl.cut(e + 0.42, "02", src_in=0.0, grade="identity_teal", speed=0.74)  # eyes open 0.0-1.8
    _, e = V("03", c + 0.32)
    c = tl.cut(e + 0.42, "03", src_in=0.45, grade="identity_amber")
    _, e = V("04", c + 0.32)
    c = tl.cut(e + 0.32, "05", src_in=0.30, grade="identity_mixed")
    tl.markers.append((c, "MUSIC MOTIF IN"))
    _, e = V("05", c + 0.38)
    c = tl.cut(e + 0.50, "06", src_in=0.0, grade="identity_crowd", push=1.06)
    _, e = V("06", c + 0.32)
    _, e = V("07a", e + 0.52)
    _, e = V("07b", e + 0.30)
    tl.markers.append((e, "I AM THE ASSET - hold"))

    # ----------------------------------------------------------------- PROBLEM
    c = tl.cut(e + 0.75, "07", src_in=0.25, grade="problem_commercial")
    tl.section(c, "THE PROBLEM")
    s8, e8 = V("08", c + 0.22)
    tl.cut(s8 + 2.55, "08", src_in=0.0, grade="problem_commercial")
    s, e = V("09a", e8 + 0.34)
    tl.cut(s - 0.06, "07", src_in=2.95, grade="problem_commercial", push=1.04)
    s, e = V("09b", e + 0.36)
    tl.cut(s - 0.06, "08", src_in=0.15, grade="problem_commercial", punch=1.18, cx=0.70, cy=0.78)
    s, e = V("09c", e + 0.36)
    c9 = tl.cut(s - 0.06, "09", src_in=0.0, grade="problem_billboard", billboard_die=True)
    V("10", c9 + 1.95)  # lands as the billboard starts to dim (src ~2.5s)
    cb = tl.cut(c9 + SRC_LEN - 0.08, "BLACK")
    tl.markers.append((cb, "BLACK - sound collapses"))
    _, e = V("11", cb + 0.42)
    c = tl.cut(e + 0.22, "02", src_in=2.55, grade="identity_teal")  # eyes open on "Trust"
    _, e = V("12", c + 0.28)

    # --------------------------------------------------------------- INVERSION
    c = tl.cut(e + 0.42, "10", src_in=0.0, grade="inversion_steel")
    tl.section(c, "THE INVERSION")
    s13, e13 = V("13", c + 0.22)
    tl.cut(s13 + 4.05, "11", src_in=0.0, grade="inversion_cyan")  # on "can be rented"
    _, e = V("14a", e13 + 0.40)
    _, e = V("14b", e + 0.26)
    _, e = V("14c", e + 0.26)
    c = tl.cut(e + 0.12, "12", src_in=0.25, grade="inversion_steel")
    _, e = V("15", c + 0.26)
    c = tl.cut(e + 0.95, "10", src_in=1.70, grade="inversion_steel", punch=1.32, cx=0.5, cy=0.72)
    _, e = V("16", c + 0.18)
    cd = tl.cut(e + 0.28, "BLACK")
    tl.gfx.append(dict(comp="AE_01_DEMAND_CANNOT_BE_RENTED", start=cd + 0.12, end=cd + 1.62))

    # --------------------------------------------------------------------- IAM
    c = tl.cut(cd + 1.78, "13", src_in=0.0, grade="iam_split")
    tl.section(c, "INTRODUCE IAM")
    s17, e17 = V("17", c + 0.34)
    tl.gfx.append(dict(comp="AE_02_IAM_INTRO", start=s17 + 0.15, end=e17 + 0.15))
    c = tl.cut(e17 + 0.30, "14", src_in=0.0, grade="iam_split")
    _, e = V("18", c + 0.24)
    c = tl.cut(e + 0.38, "15", src_in=0.0, grade="iam_split")
    _, e = V("19", c + 0.24)
    c = tl.cut(e + 0.22, "16", src_in=0.0, grade="iam_split")
    _, e = V("20", c + 0.28)
    _, e = V("21a", e + 0.55)
    _, e = V("21b", e + 0.32)
    tl.markers.append((e, "I AM... BUILDS THE COMPANIES - lands"))

    # ----------------------------------------------------------------- MACHINE
    c = tl.cut(e + 0.62, "17", src_in=0.0, grade="machine_warm")
    tl.section(c, "THE MACHINE")
    s22, e22 = V("22", c + 0.18)
    step = (e22 - 0.2 - (c + 0.12)) / 3
    tl.gfx.append(dict(comp="AE_03_UNDERWRITE", start=c + 0.12, end=c + 0.12 + step))
    tl.gfx.append(dict(comp="AE_04_MATCH", start=c + 0.12 + step, end=c + 0.12 + 2 * step))
    tl.gfx.append(dict(comp="AE_05_FORM", start=c + 0.12 + 2 * step, end=e22 - 0.2))
    c = tl.cut(e22 - 0.15, "16", src_in=1.30, grade="iam_split", punch=1.12, cx=0.5, cy=0.62)
    _, e = V("23", c + 0.32)
    c18 = tl.cut(e + 0.22, "18", src_in=0.0, grade="machine_steel")
    s, e = V("24", c18 + 0.30)
    half = (e + 0.30 - (c18 + 0.10)) / 2
    tl.gfx.append(dict(comp="AE_06_OPERATE", start=c18 + 0.10, end=c18 + 0.10 + half))
    tl.gfx.append(dict(comp="AE_07_COMPOUND", start=c18 + 0.10 + half, end=e + 0.30))
    c = tl.cut(e + 0.42, "14", src_in=0.90, grade="iam_split", punch=1.15, cx=0.45, cy=0.42)
    _, e = V("25", c + 0.22)

    # ------------------------------------------------------------------- CLOSE
    c19 = tl.cut(e + 0.34, "19", src_in=0.85, grade="close_tungsten")
    tl.section(c19, "CLOSE")
    _, e = V("26", c19 + 0.28)
    _, e = V("27", e + 0.62)
    c20 = tl.cut(e + 0.55, "20", src_in=0.30, grade="close_stage", bloom=True)
    ce = tl.cut(c20 + 2.85, "BLACK")
    tl.markers.append((ce, "SILENCE -> LOGO"))
    tl.gfx.append(dict(comp="AE_08_FINAL_LOCKUP", start=ce + 0.25, end=DURATION))
    tl.gfx.append(dict(comp="AE_09_LEGAL", start=ce + 0.25, end=DURATION))
    tl.end_card = ce
    return tl.finalize(DURATION)


def frames(t):
    return int(round(t * FPS))


def tc(t):
    f = frames(t)
    fr = 24
    s, ff = divmod(f, fr)
    m, s = divmod(s, 60)
    return f"{m:02d}:{s:02d}:{ff:02d}"


if __name__ == "__main__":
    tl = build()
    print(f"VO tempo {VO_TEMPO}  | end card at {tl.end_card:.2f}s | film {tl.end:.2f}s")
    for at, name in tl.sections:
        print(f"  section {tc(at)}  {name}")
    print("\nPICTURE")
    for s in tl.shots:
        flag = "  SLOW" if s["speed"] < 0.999 else ""
        print(f"  {tc(s['start'])}-{tc(s['end'])}  {s['dur']:5.2f}s  {s['shot']:>5}  src {s['src_in']:.2f}  x{s['speed']:.2f}{flag}  {s['grade'] or ''}")
    print("\nVO")
    for v in tl.vo:
        print(f"  {tc(v['start'])}-{tc(v['end'])}  {v['id']:>4}  {VO[v['id']][3]}")
    print("\nGFX")
    for g in tl.gfx:
        print(f"  {tc(g['start'])}-{tc(g['end'])}  {g['comp']}")
