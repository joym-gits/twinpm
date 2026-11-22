"""Mux narration clips onto the recorded walkthrough at each scene's start time.

python mux.py <rec_dir> <clips_dir> <narration.json> <out.mp4>
"""
import json
import subprocess
import sys
from pathlib import Path

rec, clips, narr_path, out = map(Path, sys.argv[1:5])
timeline = json.loads((rec / "timeline.json").read_text())
narration = {s["id"]: s for s in json.loads(narr_path.read_text())}
durations = json.loads((clips / "durations.json").read_text())

inputs = ["-i", str(rec / "walkthrough.webm")]
filters = []
for i, scene in enumerate(timeline, start=1):
    inputs += ["-i", str(clips / f"{scene['id']}.wav")]
    delay = int((scene["start"] + 0.4) * 1000)  # small lead-in after each scene starts
    filters.append(f"[{i}:a]aresample=48000,adelay={delay}|{delay}[a{i}]")
mix = "".join(f"[a{i}]" for i in range(1, len(timeline) + 1))
filters.append(f"{mix}amix=inputs={len(timeline)}:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")

# Chapter markers from the timeline.
meta = [";FFMETADATA1", "title=TwinPM product walkthrough"]
for i, scene in enumerate(timeline):
    start = int(scene["start"] * 1000)
    end = int(timeline[i + 1]["start"] * 1000) if i + 1 < len(timeline) else start + int(
        (durations[scene["id"]] + 2) * 1000)
    meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}",
             f"title={narration[scene['id']]['title']}"]
meta_path = rec / "chapters.txt"
meta_path.write_text("\n".join(meta) + "\n")

cmd = ["ffmpeg", "-y", *inputs, "-i", str(meta_path), "-filter_complex", ";".join(filters),
       "-map", "0:v", "-map", "[aout]", "-map_metadata", str(len(timeline) + 1),
       "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "25",
       "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest", str(out)]
subprocess.run(cmd, check=True)
print("wrote", out)
