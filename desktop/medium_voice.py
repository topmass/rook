"""Rook's medium voice, run locally: Qwen3-TTS 0.6B, cloning Rook's own voices.

On an Apple Silicon Mac it runs on MLX. On Linux it runs qwentts.cpp (GGML) on an NVIDIA GPU through CUDA.
It answers on loopback with the same HTTP interface as the remote medium voice server, so speech.py needs no change:
  GET  /health   -> {"loaded": bool, "model": ..., "default_voice": ..., "voices": [...], "temperature": {...}}
  POST /load     -> load the model now
  POST /unload   -> free its memory
  POST /tts      {"text": "...", "voice": "jarvis-poe", "language": "English", "temperature": 0.9}
                 -> streamed 24 kHz mono 16-bit WAV; the first byte is the first audio

  python medium_voice.py             serve on 127.0.0.1:8090 (ROOK_MEDIUM_PORT)
  python medium_voice.py --download  fetch the pinned model and exit (the installer runs this)
"""

import gc
import json
import multiprocessing as mp
import os
import struct
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

VOICE_DIR = Path(__file__).resolve().parent.parent / "assets/voices/medium"
# Every voice reference says this line. The voices were designed with Qwen3-TTS VoiceDesign.
REF_TEXT = ("Morning. I went through the overnight logs and nothing is on fire. "
            "The deploy can wait until after coffee, and honestly, so can the inbox.")
VOICES = {path.stem: path for path in sorted(VOICE_DIR.glob("*.wav"))}
DEFAULT_VOICE = "jarvis-poe"
# Measured on an M4 Pro (2026-11-25): 8-bit runs at RTF 0.27 and 4-bit at 0.23, and both read back at 99%.
MODELS = {
    "8bit": ("mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit", "50f45ef0047cde7e84c2ef04326acb8ada2436a7"),
    "4bit": ("mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit", "0d6bb6fe33f92d47a507e23b9148940e8366ab5b"),
}
# Linux: GGUF builds for qwentts.cpp. Measured on an RTX 5090 (2026-11-25): BF16 and Q8_0 both run at RTF 0.07
# with the first audio in 0.05 s, 4 times faster than the torch CUDA-graph route of the remote server.
GGUF = ("Serveurperso/Qwen3-TTS-GGUF", "b7ee2e8c7459c3bea99da23e3d178125a7d1713c")
MAC = sys.platform == "darwin"
QUANT = os.environ.get("ROOK_MEDIUM_QUANT", "8bit" if MAC else "BF16")
MODEL_NAME = MODELS[QUANT][0] if MAC else f"{GGUF[0]}:{QUANT}"
SAMPLE_RATE = 24000
CACHE = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "rook/medium-voice/models"
PORT = int(os.environ.get("ROOK_MEDIUM_PORT", "8090"))
CHUNK_SECONDS = 0.32  # 4 codec steps per chunk, as on the remote server.
MAX_TEXT = 2000
TEMPERATURE = {"default": 0.9, "min": 0.5, "max": 1.2}  # The same limits as the remote server.


def model_path(download=False):
    from huggingface_hub import hf_hub_download, snapshot_download
    if not MAC:  # The talker and the codec, as two GGUF files.
        return [Path(hf_hub_download(GGUF[0], name, revision=GGUF[1], cache_dir=CACHE, local_files_only=not download))
                for name in (f"qwen-talker-0.6b-base-{QUANT}.gguf", f"qwen-tokenizer-12hz-{QUANT}.gguf")]
    repo, revision = MODELS[QUANT]
    return Path(snapshot_download(repo, revision=revision, cache_dir=CACHE, local_files_only=not download))


def load_ggml():
    import ctypes
    import wave

    import nvidia  # The CUDA runtime and cuBLAS come from pip wheels, so the system needs only the NVIDIA driver.
    base = Path(list(nvidia.__path__)[0])
    for lib in ("cuda_runtime/lib/libcudart.so.12", "cublas/lib/libcublasLt.so.12", "cublas/lib/libcublas.so.12"):
        ctypes.CDLL(str(base / lib), mode=ctypes.RTLD_GLOBAL)
    from qwentts_cpp import QwenTTS
    model = QwenTTS(*model_path(), log_level="error")
    refs = {}
    for name, path in VOICES.items():  # The clips are 24 kHz mono 16-bit, with 0.5 s of silence added as upstream does.
        with wave.open(str(path)) as clip:
            audio = np.frombuffer(clip.readframes(clip.getnframes()), "<i2").astype(np.float32) / 32768
        refs[name] = model.extract_voice_ref(np.concatenate([audio, np.zeros(SAMPLE_RATE // 2, np.float32)]))
    return model, refs


class Engine:
    def __init__(self):
        self.lock = threading.Lock()  # ponytail: one request at a time, as on the remote server.
        self.model = None
        self.refs = {}

    def load(self):
        if self.model is not None:
            return
        if MAC:
            from mlx_audio.tts.utils import load_model
            from mlx_audio.utils import load_audio
            model = load_model(model_path())
            refs = {name: load_audio(str(path), sample_rate=model.sample_rate) for name, path in VOICES.items()}
        else:
            model, refs = load_ggml()
        for name in refs:  # Primes each voice's reference cache, so the first real request is fast.
            for _ in self.speak({"text": "Ready.", "voice": name, "language": "English", "temperature": 0.9},
                                model, refs):
                pass
        self.model, self.refs = model, refs  # /health says loaded only once the warm-up is done.

    def unload(self):
        import mlx.core as mx
        self.model, self.refs = None, {}
        gc.collect()
        mx.clear_cache()

    def speak(self, req, model=None, refs=None):
        model, refs = model or self.model, refs or self.refs
        if not MAC:
            ref = refs[req["voice"]]
            for audio, _ in model.stream(
                    text=req["text"], lang=req["language"].lower(), ref_spk_emb=ref.ref_spk_emb,
                    ref_codes=ref.ref_codes, ref_text=REF_TEXT, temperature=req["temperature"],
                    codec_chunk_sec=CHUNK_SECONDS):
                yield audio
            return
        for result in model.generate(
                text=req["text"], ref_audio=refs[req["voice"]], ref_text=REF_TEXT,
                lang_code=req["language"].lower(), temperature=req["temperature"],
                stream=True, streaming_interval=CHUNK_SECONDS):
            yield np.asarray(result.audio, dtype=np.float32).reshape(-1)


def child(conn, cancel):
    engine = Engine()
    engine.load()
    conn.send("ready")
    while True:
        req = conn.recv()
        cancel.clear()
        try:
            for audio in engine.speak(req):
                if cancel.is_set():
                    break
                conn.send(audio)
            conn.send(None)
        except Exception as error:
            conn.send(f"{error!r}")


class ChildEngine:
    """Linux: the model runs in a child process, so /unload gives back all graphics memory and a crash in
    the native library cannot take the server down. The design is the same as the remote server's."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = self.conn = None
        self.cancel = mp.get_context("spawn").Event()

    @property
    def model(self):
        return self.proc if self.proc is not None and self.proc.is_alive() else None

    def load(self):
        if self.model is not None:
            return
        ctx = mp.get_context("spawn")
        self.conn, end = ctx.Pipe()
        self.proc = ctx.Process(target=child, args=(end, self.cancel), daemon=True)
        self.proc.start()
        end.close()  # A crash in the child now raises EOFError here instead of hanging.
        if self.conn.recv() != "ready":
            raise RuntimeError("the model child did not start")

    def unload(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc.join()
        self.proc = self.conn = None

    def speak(self, req):
        self.conn.send(req)
        finished = False
        try:
            while isinstance(item := self.conn.recv(), np.ndarray):
                yield item
            finished = True
        finally:  # A stop: tell the child, then read to its end, so the pipe is clean for the next request.
            if not finished:
                self.cancel.set()
                while isinstance(self.conn.recv(), np.ndarray):
                    pass
        if item is not None:  # The child's error, as text.
            raise RuntimeError(item)


ENGINE = Engine() if MAC else ChildEngine()


def wav_header(sr):
    # Unknown length: data size 0xFFFFFFFF. Players and decoders read to EOF.
    return (b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16)
            + b"data" + struct.pack("<I", 0xFFFFFFFF))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):  # Request lines would log nothing useful; replies never log their text.
        pass

    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path != "/health":
            return self.reply(404, {"error": "not found"})
        self.reply(200, {"loaded": ENGINE.model is not None, "model": MODEL_NAME, "default_voice": DEFAULT_VOICE,
                         "voices": sorted(VOICES), "temperature": TEMPERATURE})

    def do_POST(self):
        if self.path in ("/load", "/unload"):
            with ENGINE.lock:
                try:
                    ENGINE.load() if self.path == "/load" else ENGINE.unload()
                except Exception as error:
                    print(f"The medium voice failed to load: {error!r}", file=sys.stderr, flush=True)
                    ENGINE.unload()
                    return self.reply(500, {"error": "model failed to load, see the server log"})
            return self.reply(200, {"loaded": ENGINE.model is not None})
        if self.path != "/tts":
            return self.reply(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            text = str(body.get("text", "")).strip()
        except (ValueError, AttributeError):
            return self.reply(400, {"error": "body must be JSON with a text field"})
        if not text or len(text) > MAX_TEXT:
            return self.reply(400, {"error": f"text must be 1 to {MAX_TEXT} characters"})
        voice = body.get("voice") or DEFAULT_VOICE
        if voice not in VOICES:
            return self.reply(400, {"error": f"unknown voice {voice!r}; use one of {sorted(VOICES)}"})
        temp = body.get("temperature")
        temp = TEMPERATURE["default"] if temp is None else temp
        if isinstance(temp, bool) or not isinstance(temp, (int, float)) or temp != temp:
            return self.reply(400, {"error": "temperature must be a number"})
        temp = min(max(float(temp), TEMPERATURE["min"]), TEMPERATURE["max"])
        req = {"text": text, "voice": voice, "language": str(body.get("language") or "English"), "temperature": temp}
        with ENGINE.lock:
            if ENGINE.model is None:  # speech.py loads first; a bare /tts gets the same 503 a cold server gives.
                return self.reply(503, {"error": "the model is not loaded; POST /load first"})
            started = False
            try:
                for audio in ENGINE.speak(req):
                    if not started:  # Headers wait for the first chunk: first byte = first audio.
                        self.send_response(200)
                        self.send_header("Content-Type", "audio/wav")
                        self.send_header("X-TTS-Temperature", str(temp))
                        self.end_headers()
                        self.wfile.write(wav_header(SAMPLE_RATE))
                        started = True
                    self.wfile.write((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
                    self.wfile.flush()
            except OSError:
                pass  # The client went away (a stop): leaving the loop stops the generation.
            except Exception as error:
                print(f"The medium voice failed mid-request: {error!r}", file=sys.stderr, flush=True)
                if not started:
                    self.reply(500, {"error": "tts failed, see the server log"})


if __name__ == "__main__":
    if sys.argv[1:] == ["--download"]:
        print(model_path(download=True))
    else:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
