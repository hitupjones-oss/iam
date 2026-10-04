# IAM — "I AM THE ASSET" · 1:30 brand film · V1

V1 review cut built from the 20 Higgsfield reference clips, the Brand OS
type system and a scratch VO. Exports are review-grade only. The sources
are 480p/400p renders upscaled to 1080, so this is not a master.

## What's here

| Path | Contents |
|---|---|
| `tools/edl.py` | The cut. One source of truth: VO placement, picture cuts, retimes, grades, graphics timing. `python3 tools/edl.py` prints the timeline. |
| `tools/build_graphics.py` | AE_01–AE_09 typography/logo layers as 1920×1080 RGBA PNGs + timing (`media/03_GFX/layers.json`). |
| `tools/build_audio.py` | VO processing, procedural **temp** score, synthesized sound design, ducking, loudness (-16 LUFS / ≤ -1 dBTP). |
| `tools/build_video.py` | Graded 23.976 segments → assembly → typography overlay, grain, burn-in → H.264 exports. |
| `media/01_VIDEO/` | The 20 clips, renamed per the handoff table. |
| `media/02_AUDIO/VO/` | 27 scratch VO takes (Higgsfield Seed Audio, voice "Landon"), plus `vo_words.json` transcript and `vo_regions.json` speech boundaries. |
| `media/02_AUDIO/STEMS_FLAC/` | VO stem, temp score, SFX, final mix. |
| `media/03_GFX/` | Title/logo layers. |
| `assets/` | Montserrat, DM Mono, Playfair Display (OFL), IAM logo (source + white/black PNG). |

Rebuild everything (Python 3 + numpy/scipy/pillow, ffmpeg with librubberband):

```
python3 tools/build_graphics.py && python3 tools/build_audio.py && python3 tools/build_video.py --rebuild
```

Outputs land in `exports/` (gitignored): `IAM_I_AM_THE_ASSET_v01_REVIEW.mp4` (TC + shot burn-in),
`IAM_I_AM_THE_ASSET_v01_CLEAN_REVIEW.mp4`, both H.264 1920×1080 23.976, 16 Mb/s, AAC 320k.

## The cut (actual section times)

| Section | Start | Notes |
|---|---|---|
| Identity | 00:00 | 01 → 04 → 02 → 03 → 05 → 06. "I am the asset" lands on 06 with a hold. |
| The Problem | 00:18:15 | Strobe pop on the cut. "A campaign / A deal / A fee" each land on a cut (07, 08 punch-in, 09). Billboard dims, flickers, dies; sound collapses to black. "Trust was" on 02 as her eyes open. |
| The Inversion | 00:35:13 | 10 → 11 → 12 ("Capital.", hold) → 10 punch-in → black: DEMAND CANNOT BE RENTED. |
| Introduce IAM | 00:50:19 | 13 with the IAM mark, 14, 15, 16. "I am... builds the companies" lands, then a hold. |
| The Machine | 01:07:13 | 17 UNDERWRITE / MATCH / FORM → 16 → 18 OPERATE / COMPOUND → 14 punch-in. |
| Close | 01:20:05 | 19: eyes closed on "Not rented by the business", open on "An owner of it". 20 walks into the light. Silence, then the end card at 01:27:08. |

## Decisions that differ from the brief (for review)

- **VO runs 10% faster (pitch preserved).** At a measured pace the 27 lines take about 69 s. With the brief's black holds, title card and end card, that doesn't fit in 1:30. Section starts drift 1.5–3 s later than the brief's map, and Close lands on time.
- **The end card is 2.6 s.** The legal line is on screen for about 2.4 s, which is short for 13 words. Options: lengthen the end card (a 1:32–1:33 film), or trim VO copy.
- **Shot 13 (5 s in the brief) and other long holds are slowed** (71–94%) because every source is 4.04 s. Retimes are burned into the REVIEW export.
- **Temp score is procedural.** It follows the brief's arc but is a placeholder. Replace it with a licensed track.
- **Sound design is synthesized** (no library access in this environment). Spot effects and ambiences sit where the brief asks, and need a proper library pass.

## QC flags

- **Shot 12 (founder portrait), and the centre figure in 16 (and possibly 13), read as a specific, recognisable real-world celebrity.** For an investor-facing piece about talent and ownership, that implies endorsement and raises right-of-publicity risk. Regenerate these before anything leaves the building.
- All 20 clips: no hand, jewellery or face breakage visible at review resolution. Shot 02's eye-close (src 1.85–3.2 s) is avoided in the main use and used deliberately in the "Trust was" reprise. Shot 19's eye-close is used as the "owner" beat.
- OPERATE sits over the woman's head silhouette in 18. Consider a left-third layout in V2.
- Regenerate or upscale for the master: everything is 480p (12/16/18 are 400p). Priority order: 01, 02, 03, 12, 14, 15, 19 (the portraits).

## Premiere / After Effects

The Adobe hosts were not connected during this build. Once the Higgsfield panel is connected in Premiere Pro and After Effects, the same EDL drives building `IAM_I_AM_THE_ASSET_v01` with the bins and sequences from the handoff (`IAM_MASTER_90`, `IAM_PICTURE_EDIT`, `IAM_SOUND_DESIGN`, `IAM_GRADE`) and the AE_01–AE_09 comps.
