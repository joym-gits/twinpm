# Product walkthrough video

`TwinPM-walkthrough.mp4` (repo root, git-ignored): about 14.5 minutes, 1440×900, 21 chapters,
narrated with the Kokoro neural voice `af_heart` (open source, runs locally).

Regenerate after UI changes:

1. Voice: in a separate env, `uv add kokoro soundfile "misaki[en]"` and `brew install espeak-ng`,
   then `python speak.py narration.json <clips_dir> af_heart`.
2. Reset the demo data (Cmd/Ctrl+K → reset, or `POST /api/v1/admin/reset-demo`).
3. Record against the running stack:
   `cd apps/web && node scripts/record-walkthrough.mjs <clips_dir>/durations.json <rec_dir>`
   (`--dry` checks every step quickly without waiting).
4. Mux: `python mux.py <rec_dir> <clips_dir> narration.json TwinPM-walkthrough.mp4`.
