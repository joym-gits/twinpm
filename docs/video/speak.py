"""Synthesize narration clips with Kokoro: python speak.py scenes.json outdir voice"""
import json, sys
import numpy as np, soundfile as sf
import espeakng_loader
from phonemizer.backend.espeak.wrapper import EspeakWrapper
from kokoro import KPipeline

# The pip-packaged espeak-ng has a broken data path; use the Homebrew build instead.
EspeakWrapper.set_library("/opt/homebrew/lib/libespeak-ng.1.dylib")
EspeakWrapper.set_data_path("/opt/homebrew/share/espeak-ng-data")
espeakng_loader.get_library_path = lambda: "/opt/homebrew/lib/libespeak-ng.1.dylib"
espeakng_loader.get_data_path = lambda: "/opt/homebrew/share/espeak-ng-data"
espeakng_loader.make_library_available = lambda: None

scenes, out, voice = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
pipe = KPipeline(lang_code="a")
durations = {}
for s in scenes:
    chunks = [a for _, _, a in pipe(s["text"], voice=voice, speed=1.0, split_pattern=r"\n+")]
    pause = np.zeros(int(24000 * 0.35), dtype=np.float32)
    audio = np.concatenate([np.concatenate([c, pause]) for c in chunks])
    sf.write(f"{out}/{s['id']}.wav", audio, 24000)
    durations[s["id"]] = round(len(audio) / 24000, 2)
    print(s["id"], durations[s["id"]], flush=True)
json.dump(durations, open(f"{out}/durations.json", "w"), indent=1)
