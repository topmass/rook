#!/bin/sh
# Rook voice speed test for Apple Silicon Macs. It is silent: it writes WAV files and plays nothing.
# It measures the medium voice (Qwen3-TTS 0.6B on MLX) and AirType's recognizer (Fluid Speech Mini on onnxruntime),
# prints the numbers, and deletes everything it downloaded (about 5 GB) when it ends. It takes about 10 minutes.
#   sh scripts/mac_voice_bench.sh
# Optional: ROOK_BENCH_QUANTS="8bit 4bit bf16" picks the MLX builds; ROOK_BENCH_DIR=<folder> keeps the downloads there;
# ROOK_VOICE_REF=<ref.wav> clones that voice (it must say REF_TEXT below) instead of a macOS `say` voice.
set -eu

if [ "$(uname -s) $(uname -m)" != "Darwin arm64" ]; then
	echo "This test needs a Mac with Apple Silicon." >&2
	exit 1
fi
quants="${ROOK_BENCH_QUANTS:-8bit 4bit}"
if [ -n "${ROOK_BENCH_DIR:-}" ]; then
	dir="$ROOK_BENCH_DIR"
	mkdir -p "$dir"
else
	dir=$(mktemp -d "${TMPDIR:-/tmp}/rook-voice-bench.XXXXXX")
	trap 'rm -rf "$dir"' EXIT INT TERM
fi
export HF_HOME="$dir/hf" UV_CACHE_DIR="$dir/uv-cache" HF_HUB_DISABLE_PROGRESS_BARS=1 TOKENIZERS_PARALLELISM=false

echo "Chip:    $(sysctl -n machdep.cpu.brand_string), $(( $(sysctl -n hw.memsize) / 1073741824 )) GB, macOS $(sw_vers -productVersion)"
echo "Setting up in $dir (a few minutes on the first run)..."

uv=$(command -v uv || true)
if [ -z "$uv" ]; then
	curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$dir/bin" INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null
	uv="$dir/bin/uv"
fi
[ -x "$dir/venv/bin/python" ] || "$uv" venv -q --python 3.12 "$dir/venv"
"$uv" pip install -q --python "$dir/venv/bin/python" mlx-audio==0.6.8 onnxruntime==1.32.0 soundfile huggingface_hub

ref_text="Morning. I went through the overnight logs and nothing is on fire. The deploy can wait until after coffee, and honestly, so can the inbox."
if [ -n "${ROOK_VOICE_REF:-}" ]; then
	cp "$ROOK_VOICE_REF" "$dir/ref.wav"
else
	say -o "$dir/ref.aiff" "$ref_text"  # Writes a file; nothing plays.
	afconvert -f WAVE -d LEI16@24000 -c 1 "$dir/ref.aiff" "$dir/ref.wav"
fi

cat > "$dir/bench.py" <<'PY'
"""bench.py tts <quant> | stt: one model per process, so each peak memory figure is its own."""
import difflib, gc, json, resource, sys, time, wave
from pathlib import Path

import numpy as np

DIR = Path(sys.argv[2])
REF_TEXT = ("Morning. I went through the overnight logs and nothing is on fire. "
            "The deploy can wait until after coffee, and honestly, so can the inbox.")
SHORT = "The build finished cleanly, and both checks passed on the first try."
LONG = ("I looked through the three pull requests you asked about this morning. "
        "The first one is ready to merge, and the tests all pass on the main branch. "
        "The second one changes the speech queue, so I would like you to hear it before it ships. "
        "The third one is still a draft, and its author asked for a review by Friday. "
        "Tell me which one you want first, and I will open it on the left screen.")


def match(text):
    words = lambda s: "".join(c for c in s.lower() if c.isalnum() or c == " ").split()
    return difflib.SequenceMatcher(None, words(LONG), words(text)).ratio()


def rss_gb():  # macOS reports ru_maxrss in bytes.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9


def save(name, audio, rate):
    with wave.open(str(DIR / name), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def tts(quant):
    import mlx.core as mx
    from huggingface_hub import snapshot_download
    from mlx_audio.tts.utils import load_model
    from mlx_audio.utils import load_audio

    t = time.perf_counter()
    path = snapshot_download(f"mlx-community/Qwen3-TTS-12Hz-0.6B-Base-{quant}")
    download = time.perf_counter() - t
    t = time.perf_counter()
    model = load_model(Path(path))
    ref = load_audio(str(DIR / "ref.wav"), sample_rate=model.sample_rate)
    load = time.perf_counter() - t
    rate = model.sample_rate

    def run(text, stream, interval=0.32):
        mx.reset_peak_memory()
        t0, first, parts = time.perf_counter(), None, []
        for r in model.generate(text=text, ref_audio=ref, ref_text=REF_TEXT, lang_code="english",
                                stream=stream, streaming_interval=interval):
            parts.append(np.asarray(r.audio, dtype=np.float32).reshape(-1))
            first = first if first is not None else time.perf_counter() - t0
        took = time.perf_counter() - t0
        audio = np.concatenate(parts)
        return {"first": first, "took": took, "seconds": len(audio) / rate, "rtf": took / (len(audio) / rate),
                "peak_gb": mx.get_peak_memory() / 1e9}, audio

    t = time.perf_counter()
    run("Ready.", True)  # Warm-up, as Rook's server does after a load.
    warm = time.perf_counter() - t
    out = {"quant": quant, "download": download, "load": load, "warmup": warm}
    out["short_stream"], a = run(SHORT, True)
    save(f"short-{quant}.wav", a, rate)
    out["long_stream"], a = run(LONG, True)
    save(f"long-{quant}.wav", a, rate)
    out["long_whole"], a = run(LONG, False)
    save(f"stt-clip-{quant}.wav", a[: 15 * rate], rate)
    out["peak_rss_gb"] = rss_gb()
    print(json.dumps(out))


def stt(clip):
    import onnxruntime as ort
    from huggingface_hub import snapshot_download
    from mlx_audio.utils import load_audio

    # AirType's Fluid Speech Mini (FluidVoice, CC BY 4.0). AirType runs an adapted copy of this repo's transcribe.py.
    model_dir = snapshot_download("FluidVoice-Labs/fluid-speech-mini-onnx",
                                  revision="fc592620325027419883cf272e70588d8a788c0a")
    sys.path.insert(0, model_dir)
    import transcribe

    wav = np.asarray(load_audio(str(DIR / clip), sample_rate=16000), dtype=np.float32).reshape(-1)
    out = {"clip_seconds": len(wav) / 16000}
    plain = ort.InferenceSession
    for name, big in (("cpu", ["CPUExecutionProvider"]),
                      ("coreml", [("CoreMLExecutionProvider", {"MLComputeUnits": "ALL"}), "CPUExecutionProvider"])):
        # The encoder and front end take the provider under test; the small decoder and joint stay on the CPU.
        ort.InferenceSession = lambda path, opts=None, providers=None, _b=big: plain(
            path, opts, providers=_b if "encoder" in path or "frontend" in path else providers)
        model = None
        try:
            t = time.perf_counter()
            model = transcribe.Model(model_dir, threads=4, spin=False)
            loaded = time.perf_counter() - t
            t = time.perf_counter()
            text = model.transcribe(wav)
            cold = time.perf_counter() - t
            warm = []
            for _ in range(3):
                t = time.perf_counter()
                model.transcribe(wav)
                warm.append(time.perf_counter() - t)
            out[name] = {"load": loaded, "first": cold, "warm": sorted(warm)[1], "text": text,
                         "rss_gb": rss_gb()}
            if name == "cpu":  # Word match of each whole long reply: a rough check that the voice stays clear.
                out["match"] = {q.stem[5:]: match(model.transcribe(np.asarray(load_audio(
                    str(q), sample_rate=16000), dtype=np.float32).reshape(-1))) for q in sorted(DIR.glob("long-*.wav"))}
        except Exception as error:
            out[name] = {"error": f"{type(error).__name__}: {error}"[:200]}
        finally:
            ort.InferenceSession = plain
        del model
        gc.collect()
    out["peak_rss_gb"] = rss_gb()
    print(json.dumps(out))


if __name__ == "__main__":
    tts(sys.argv[3]) if sys.argv[1] == "tts" else stt(sys.argv[3])
PY

for q in $quants; do
	echo "Testing the medium voice ($q)..."
	"$dir/venv/bin/python" "$dir/bench.py" tts "$dir" "$q" | tail -1 > "$dir/tts-$q.json"
done
first=$(echo "$quants" | cut -d' ' -f1)
echo "Testing speech to text..."
"$dir/venv/bin/python" "$dir/bench.py" stt "$dir" "stt-clip-$first.wav" | tail -1 > "$dir/stt.json"

"$dir/venv/bin/python" - "$dir" $quants <<'PY'
import json, sys
from pathlib import Path
d = Path(sys.argv[1])
print("\n=== Rook voice results: copy everything below and send it back ===")
for q in sys.argv[2:]:
    r = json.loads((d / f"tts-{q}.json").read_text())
    s, l, w = r["short_stream"], r["long_stream"], r["long_whole"]
    print(f"Medium voice {q}: download {r['download']:.0f} s, load {r['load']:.1f} s, warm-up {r['warmup']:.1f} s, "
          f"process memory {r['peak_rss_gb']:.1f} GB")
    print(f"  short ({s['seconds']:.1f} s audio): first audio {s['first']:.2f} s, RTF {s['rtf']:.2f}, "
          f"GPU peak {s['peak_gb']:.1f} GB")
    print(f"  long  ({l['seconds']:.1f} s audio): first audio {l['first']:.2f} s, RTF {l['rtf']:.2f}, "
          f"GPU peak {l['peak_gb']:.1f} GB streaming; RTF {w['rtf']:.2f}, GPU peak {w['peak_gb']:.1f} GB whole")
r = json.loads((d / "stt.json").read_text())
for name in ("cpu", "coreml"):
    x = r[name]
    if "error" in x:
        print(f"Speech to text {name}: failed: {x['error']}")
    else:
        print(f"Speech to text {name} ({r['clip_seconds']:.0f} s clip): load {x['load']:.1f} s, "
              f"first {x['first']:.2f} s, warm {x['warm']:.2f} s, process memory {x['rss_gb']:.1f} GB")
print("Word match of each long reply, heard by the recognizer: "
      + ", ".join(f"{q} {m:.0%}" for q, m in r.get("match", {}).items()))
print("RTF under 1.0 is faster than real time.")
PY
