"""Keep a Pocket TTS or Phonon model and the selected voice loaded between turns. The qwen engine speaks through
the medium voice server and keeps Phonon loaded as its fallback."""

import argparse
import collections
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import math
import operator
import os
import queue
import re
import select
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import wave

import desk

# The medium voice must send its first sound within this many seconds, or the item uses the small voice.
FIRST_AUDIO_SECONDS = 2.5
# A medium voice stream that sends nothing for this long mid-item stops that item.
STALL_SECONDS = 10
# A cold load of the medium voice model takes 8 to 11 seconds. It runs in the background.
LOAD_SECONDS = 60
# A mic open after this many seconds with no medium request sends one silent warm-up: an idle server wakes slowly.
WARM_IDLE_SECONDS = 60
# A warm-up gives up after this many seconds. Its failure is silent.
WARM_SECONDS = 10
WARM_TEXT = "Ready."
# The medium voice server takes at most this many characters per request.
TEXT_LIMIT = 2000
# Pitch-preserving tempo filter for the medium voice when speed is not 50 (1.0x).
FFMPEG = desk.ffmpeg_exe()
# The band where Qwen speech stays clean.
MEDIUM_TEMPERATURE_BAND = (0.6, 1.1)
# Fallback medium voice temperature range (default, min, max), used for mapping only.
MEDIUM_TEMPERATURE = (0.9, *MEDIUM_TEMPERATURE_BAND)
# Seconds per reported speech level block.
LEVEL_STEP = 0.05
# Match pw-play's 40 ms PipeWire buffer so levels align with heard sound.
PLAYBACK_LATENCY = 0.04


class LevelMeter:
    """Emit audible audio levels on the playback clock for one playing item."""

    def __init__(self, item_id, sample_rate, stop, emit=None, latency=PLAYBACK_LATENCY, step=LEVEL_STEP):
        self.item_id = item_id
        self.sample_rate = sample_rate
        self.stop = stop
        self.emit = emit or (lambda event: print(json.dumps(event), flush=True))
        self.latency = latency
        self.step = step
        self.block_samples = max(1, int(round(sample_rate * step)))
        self.blocks = []
        self.tail = bytearray()
        self.samples = 0
        self.started_at = None
        self.finished = False
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, daemon=True)

    @staticmethod
    def _rms(samples):
        if not samples:
            return 0.0
        total = sum(map(operator.mul, samples, samples))
        return min(1.0, math.sqrt(total / len(samples)) / 32768.0)

    def push(self, audio):
        """Compute 50 ms block RMS values for audio about to enter pw-play."""
        if not audio:
            return
        now = time.monotonic()
        with self.lock:
            total_samples = self.samples + len(self.tail) // 2
            if self.started_at is None:
                self.started_at = now + self.latency
                self.thread.start()
            elif now > self.started_at + total_samples / self.sample_rate:
                # Playback drained during a stall, so new audio plays after latency.
                self.started_at = now + self.latency - total_samples / self.sample_rate
            buf = self.tail + audio if self.tail else audio
            block_bytes = self.block_samples * 2
            full = (len(buf) // block_bytes) * block_bytes
            if full:
                wave = memoryview(buf)[:full].cast("h")
                step = self.block_samples
                self.blocks.extend(self._rms(wave[i:i + step]) for i in range(0, len(wave), step))
                self.samples += len(wave)
            self.tail = bytearray(buf[full:])

    def finish(self):
        """Flush any trailing partial block once all audio is written."""
        with self.lock:
            even = len(self.tail) - (len(self.tail) % 2)
            if even:
                with memoryview(bytes(self.tail[:even])).cast("h") as wave:
                    self.blocks.append(self._rms(wave))
                    self.samples += len(wave)
            self.tail.clear()
            self.finished = True

    def close(self):
        """Stop emitting levels and wait for the timer thread."""
        self.done.set()
        if self.thread.is_alive():
            self.thread.join(timeout=0.5)

    def _run(self):
        last_idx = -1
        while not self.done.is_set() and not self.stop.is_set():
            with self.lock:
                started_at = self.started_at
                now = time.monotonic()
                idx = math.floor((now - started_at) / self.step)
                if idx <= last_idx:
                    wait = started_at + (last_idx + 1) * self.step - now
                    level = None
                elif idx < len(self.blocks):
                    level = self.blocks[idx]
                    last_idx = idx
                    wait = started_at + (idx + 1) * self.step - now
                elif self.finished:
                    return
                else:
                    level = 0.0
                    wait = self.step
            if level is not None:
                if self.done.is_set() or self.stop.is_set():
                    return
                self.emit({"event": "level", "id": self.item_id, "level": round(level, 4)})
            if wait > 0 and self.done.wait(wait):
                return


# Words the voice reads wrong, respelled for speech only. Captions keep the original text.
# Written as "BiS", the voice says the letters B and S. Written as "WoW", it says something like "walvo".
# Written as "WoWFriend" (or "WoW Friend"), the voice can say "woah friend", so every form is spoken as "wow friend".
# Written as "Everystate", the voice says "ever stite", so every form is spoken as "every state".
# The colon in the game's name makes the voice pause, so the name is spoken without it.
RESPELL = ((re.compile(r"\bBiS\b", re.IGNORECASE), "biss"),
           (re.compile(r"\bwow\s*friends\b", re.IGNORECASE), "wow friends"),
           (re.compile(r"\bwow\s*friend\b", re.IGNORECASE), "wow friend"),
           (re.compile(r"\beverystates\b", re.IGNORECASE), "every states"),
           (re.compile(r"\beverystate\b", re.IGNORECASE), "every state"),
           (re.compile(r"\bW[oO]W:\s*Forever\b"), "Wow Forever"),
           (re.compile(r"\bW[oO]W\b"), "Wow"))
# Both voices read "live" as the verb in most adjective uses.
# Respell it per engine unless a verb marker comes right before it.
# On Qwen3-TTS, "lyve" came back as "leave" in 1 of 12 probes, and "lighve" as "live" in 24 of 24.
# A recogniser cannot hear the vowel, so the owner picks the medium spelling by ear.
LIVE_SPELLING = {"small": "lyve", "medium": "lighve"}
# The owner's own respellings, for speech only: {"words": {WORD: SPELLING}, "small": {...}, "medium": {...}}.
# An engine's entries win over "words". A missing or broken file gives no entries.
PRONUNCIATIONS = desk.config_dir() / "rook/pronunciations.json"
_pronounced = [None, {}]  # The file's (mtime, size) and its compiled entries per engine.
LIVE_VERB_BEFORE = frozenset((
    "i", "you", "we", "they", "can", "could", "will", "would", "should",
    "must", "might", "may", "shall", "do", "does", "did", "don't", "doesn't",
    "didn't", "can't", "cannot", "won't", "wouldn't", "couldn't", "shouldn't",
    "mustn't", "who",
))
# "to live" is usually the adjective ("ship to live"), unless a verb like "want" precedes "to".
TO_LIVE_VERB_BEFORE = frozenset((
    "want", "wants", "wanted", "need", "needs", "have", "has", "had",
    "going", "how", "where", "able", "used",
))
PREV_WORD = re.compile(r"\b([A-Za-z]+(?:['\u2019][A-Za-z]+)?)\s+\Z")
LIVE_WORD = re.compile(r"\blive\b", re.IGNORECASE)
# Both voices read "6:24" as "six thousand twenty-four", so clock times are spoken in words.
# The time must stand alone: not inside a URL, path or code, and not a ratio like "3:1" or "10:12 odds".
# A final "p.m." keeps its dot when it ends the sentence.
CLOCK = re.compile(r"(?<![^\s(\"'\u201c\u2018])([01]?\d|2[0-3]):([0-5]\d)"
                   r"(?:\s*([AaPp])\.?\s?[Mm]\b(?:\.(?!\s*(?:[A-Z]|$)))?)?"
                   r"(?![\w:/]|\.\d|\s*(?:odds|ratio)\b)")
ONES = ("", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
        "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
TENS = ("", "", "twenty", "thirty", "forty", "fifty")


def clock_words(match):
    """Speak an H:MM or HH:MM time: "6:05" as "six oh five", "18:30" as "six thirty PM", "12:00" as "twelve o'clock"."""
    hour, minute, half = int(match.group(1)), int(match.group(2)), match.group(3)
    if not half and (hour > 12 or match.group(1).startswith("0")):  # 24-hour time: "18:30" or "08:15".
        half = "p" if hour >= 12 else "a"
    if half:
        hour = hour % 12 or 12
    words = ONES[hour]
    if minute:
        words += " " + ("oh " + ONES[minute] if minute < 10 else ONES[minute] if minute < 20
                        else TENS[minute // 10] + ("-" + ONES[minute % 10] if minute % 10 else ""))
    return f"{words} {half.upper()}M" if half else words if minute else words + " o'clock"


def read_pronunciations(path=None):
    """Return the pronunciations file as {"words"|"small"|"medium": {WORD: SPELLING}}, or {} when missing or broken."""
    try:
        data = json.loads((path or PRONUNCIATIONS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {group: {w.strip(): s.strip() for w, s in entries.items()
                    if isinstance(w, str) and isinstance(s, str) and w.strip() and s.strip()}
            for group, entries in data.items() if group in ("words", "small", "medium") and isinstance(entries, dict)}


def pronunciations(engine):
    """Return the owner's (pattern, spelling) pairs for engine, rereading the file only when it changes.
    A word with a capital letter matches that case only. A lowercase word matches any case."""
    try:
        info = PRONUNCIATIONS.stat()
        key = (info.st_mtime_ns, info.st_size)
    except OSError:
        key = None
    if key != _pronounced[0]:
        data = read_pronunciations() if key else {}
        compiled = {}
        for name in ("small", "medium"):
            entries = {**data.get("words", {}), **data.get(name, {})}
            compiled[name] = [(re.compile(rf"(?<!\w){re.escape(w)}(?!\w)", 0 if w != w.lower() else re.IGNORECASE), s)
                              for w, s in sorted(entries.items(), key=lambda item: -len(item[0]))]
        _pronounced[:] = [key, compiled]
    return _pronounced[1].get(engine, ())


def respell(text, engine="small"):
    """Respell words the voice of engine ("small" or "medium") reads wrong, for speech only. Captions keep the text."""
    text = CLOCK.sub(clock_words, text)
    for pattern, spelling in pronunciations(engine):
        text = pattern.sub(lambda m: spelling[:1].upper() + spelling[1:]
                           if m.group(0)[:1].isupper() and spelling[:1].islower() else spelling, text)
    for pattern, replacement in RESPELL:
        text = pattern.sub(replacement, text)

    def replace_live(match):
        prev = PREV_WORD.search(text[:match.start()])
        if prev:
            word = prev.group(1).replace("\u2019", "'").lower()
            if word in LIVE_VERB_BEFORE or word.endswith(("'ll", "'d")):
                return match.group(0)
            if word == "to":
                before_to = PREV_WORD.search(text[:prev.start()])
                if before_to and before_to.group(1).lower() in TO_LIVE_VERB_BEFORE:
                    return match.group(0)
        spelling = LIVE_SPELLING[engine]
        return spelling if match.group(0).islower() else spelling.capitalize()

    return LIVE_WORD.sub(replace_live, text)


def load(args):
    """Return the sample rate and a function that yields s16 audio chunks for a text until stopped."""
    # Two threads each, so speech does not steal CPU from the game.
    if args.engine in ("phonon", "qwen"):
        import numpy as np
        import ptts
        ptts.set_num_threads(2)
        model = ptts.TTS(args.model, quant="q8", lang="en",  # None is the runtime's pinned phonon-31m-en.
                         temperature=args.temperature, conditions={"duration_delta": args.pace} if args.pace else None)
        voice = args.voice or "Miles"
        model.synth("Ready.", voice=voice)  # Downloads a catalog voice now, not on the first reply.

        def generate(text, stop, voices=None):  # voices may name another voice for this item only.
            with model.stream(respell(text), voice=(voices or {}).get("voice") or voice) as audio:
                for chunk in audio:
                    if stop.is_set():
                        return
                    yield (np.clip(chunk, -1, 1) * 32767).astype(np.int16).tobytes()
        if args.engine == "qwen":
            return model.sample_rate, medium(args.url, args.voice_medium, model.sample_rate, generate,
                                             pace=args.pace, temperature=args.temperature)
        return model.sample_rate, generate
    import torch
    from pocket_tts import TTSModel
    torch.set_num_threads(2)
    model = TTSModel.load_model(language=args.model or "english_7m_2026-10", quantize=args.int8)
    voice = model.get_state_for_audio_prompt(args.voice or "alba")

    def generate(text, stop, voices=None):
        for chunk in model.generate_audio_stream(voice, respell(text), stop=stop):
            yield (chunk.clamp(-1, 1) * 32767).short().numpy().tobytes()
    return model.sample_rate, generate


def pieces(text, limit=TEXT_LIMIT):
    """Split text into one piece per sentence, and a sentence over limit characters at a space.
    The medium voice gets one request per sentence: on a long request it sometimes stops early and clips the end."""
    out = []
    for piece in re.split(r"(?<=[.!?])\s+", text.strip()):
        while len(piece) > limit:  # One sentence over the limit.
            cut = piece.rfind(" ", 0, limit + 1)
            cut = cut if cut > 0 else limit
            out.append(piece[:cut])
            piece = piece[cut:].lstrip()
        if piece:
            out.append(piece)
    return out


def voiced(span, audio):
    """Add an s16 chunk to span, a list of [samples, first voiced sample, last voiced sample]. The voice ends each item
    with over half a second of silence. Captions pace themselves on the spoken part, so they time only the sound."""
    wave = memoryview(audio).cast("h")
    first = next((i for i, level in enumerate(wave) if abs(level) > 655), None)
    if first is not None:
        last = next(i for i in range(len(wave) - 1, -1, -1) if abs(wave[i]) > 655)
        span[1] = span[1] or span[0] + first + 1
        span[2] = span[0] + last + 1
    span[0] += len(wave)


def medium_tempo(pace):
    """Map voice_pace (-0.5 to 0.5, negative is faster) to a pitch-preserving tempo (0.8 to 1.2)."""
    return round(max(0.8, min(1.2, 1.0 - 0.4 * (pace or 0.0))), 6)


def temperature_range(data):
    """Return (default, min, max) from a server /health JSON dict, or None when absent or invalid."""
    block = data.get("temperature") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return None
    vals = [block.get(k) for k in ("default", "min", "max")]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vals):
        return None
    default, low, high = (float(v) for v in vals)
    return (default, low, high) if low <= default <= high else None


def medium_temperature(temperature, limits=MEDIUM_TEMPERATURE):
    """Map voice_temperature (1 to 100 points as 0.01 to 1.0) onto the clean Qwen band clipped by limits."""
    default, server_low, server_high = limits
    low = max(MEDIUM_TEMPERATURE_BAND[0], server_low)
    high = min(MEDIUM_TEMPERATURE_BAND[1], server_high)
    if low > high:
        low, high = server_low, server_high
    anchor = max(low, min(high, default))
    points = max(1, min(100, round((temperature or 0.0) * 100)))
    if points <= 50:
        value = low + (points - 1) / 49 * (anchor - low)
    else:
        value = anchor + (points - 50) / 50 * (high - anchor)
    return round(max(low, min(high, value)), 4)


def medium(url, voice, sample_rate, small, pace=0.0, temperature=0.5, ffmpeg=FFMPEG):
    """Return a generate that speaks each item with the medium voice server, or with small when the server cannot
    be reached, sends an error, or starts too slowly. An item never switches voices midway. After each item,
    generate.problem says what went wrong, or is None.
    A cold model takes about 10 seconds to its first sound, so items use the small voice until a /load succeeds."""
    server = urllib.parse.urlsplit(url)
    https = server.scheme == "https"
    port = server.port or (443 if https else 80)
    connect = http.client.HTTPSConnection if https else http.client.HTTPConnection
    tempo = medium_tempo(pace)
    temp_range = None
    fallbacks = 0
    ffmpeg_warned = False
    loaded, loading = threading.Event(), threading.Lock()
    not_ready = "it has not answered yet"

    def ask(method, path, timeout, mark_loaded=True):
        """Send GET /health or POST /load, wait up to timeout seconds, and note whether the model is loaded."""
        nonlocal not_ready, temp_range
        connection = connect(server.hostname, port, timeout=timeout)
        try:
            connection.request(method, path)
            answer = connection.getresponse()
            if answer.status == 200:
                data = json.loads(answer.read() or b"{}")
                if found := temperature_range(data):
                    temp_range = found
                if isinstance(data, dict) and data.get("loaded") is True:
                    if mark_loaded:
                        loaded.set()
                    return True
            not_ready = f"{path} answered {answer.status} with the model not loaded"
        except Exception as error:  # Any answer that is not a clear "loaded" leaves the small voice speaking.
            not_ready = f"{path} failed: {error if isinstance(error, OSError) else type(error).__name__}"
        finally:
            connection.close()
        print(f"The medium voice is not ready: {not_ready}", file=sys.stderr, flush=True)
        return False

    def load_model():
        """Ask the server to load its model in the background, unless a load already runs."""
        def run():
            try:
                if ask("POST", "/load", LOAD_SECONDS, mark_loaded=False):
                    if temp_range is None:
                        ask("GET", "/health", FIRST_AUDIO_SECONDS)
                    loaded.set()
            finally:
                loading.release()
        if loading.acquire(blocking=False):
            threading.Thread(target=run, daemon=True).start()

    # /health answers at once. A warm model serves the first item; a cold one loads in the background.
    ask("GET", "/health", FIRST_AUDIO_SECONDS)
    if not loaded.is_set():
        load_model()

    def generate(text, stop, voices=None):
        nonlocal fallbacks, ffmpeg_warned
        generate.problem = None
        voices = voices or {}
        if voices.get("voice") and not voices.get("voice_medium"):  # An item that names a small voice gets it.
            yield from small(text, stop, voices)
            return
        # An audition line waits longer for its first sound and never falls back: its voice is the point of it.
        audition = bool(voices.get("first_audio"))
        first_audio = float(voices.get("first_audio") or FIRST_AUDIO_SECONDS)
        started, got_audio, connected, sock, connection, status = False, False, False, None, None, None
        proc, feeder, feed_error, local_error, request = None, None, None, False, None
        deadline = time.monotonic() + first_audio
        done, abort = threading.Event(), threading.Event()

        def kill_proc():
            p = proc
            if p is not None:
                try:
                    p.kill()
                except OSError:
                    pass

        def shutdown_sock():
            s = sock
            if s is not None:
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        def watch():
            # A stop closes the socket and kills ffmpeg, so any wait ends at once.
            while not done.wait(0.05):
                if stop.is_set() or abort.is_set():
                    kill_proc()
                    shutdown_sock()

        def wait():
            # Until the first network audio, every read shares one deadline. After it, a read may stall STALL_SECONDS.
            left = STALL_SECONDS if started or got_audio else deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError
            sock.settimeout(left)

        def read(answer, size):
            wait()
            data = answer.read(size)
            if len(data) < size:
                raise ValueError("the WAV header ended early")
            return data

        def raw_audio():
            nonlocal connection, sock, connected, status, got_audio, request
            for piece in pieces(respell(text, "medium")):
                if stop.is_set() or abort.is_set():
                    return
                connection = connect(server.hostname, port,
                                     timeout=STALL_SECONDS if started or got_audio else first_audio)
                try:
                    payload = {"text": piece, "voice": voices.get("voice_medium") or voice, "language": "English"}
                    if (limits := temp_range) is not None:
                        payload["temperature"] = medium_temperature(temperature, limits)
                    rid, sent = os.urandom(4).hex(), time.monotonic()
                    request, generate.last_request = rid, sent
                    print(f"Medium voice request {rid}: sent", file=sys.stderr, flush=True)
                    connection.request("POST", "/tts", json.dumps(payload),
                                       {"Content-Type": "application/json", "X-Request-Id": rid})
                    sock = connection.sock  # A reply that closes the connection drops connection.sock, not its reads.
                    if sock is not None:
                        connected = True
                    if stop.is_set() or abort.is_set():
                        return
                    wait()
                    answer = connection.getresponse()
                    if answer.status != 200:
                        status = answer.status
                        raise ValueError(f"the server answered {status}")  # Its body may hold the text: never logged.
                    if read(answer, 12)[8:] != b"WAVE":
                        raise ValueError("the server did not send a WAV stream")
                    fmt = None
                    while (chunk := struct.unpack("<4sI", read(answer, 8)))[0] != b"data":
                        body = read(answer, chunk[1] + chunk[1] % 2)  # Chunks pad to an even length.
                        if chunk[0] == b"fmt ":
                            fmt = struct.unpack("<HHIIHH", body[:16])
                    # 1 is plain PCM, 0xFFFE the extensible form of it.
                    if not fmt or fmt[0] not in (1, 0xFFFE) or (fmt[1], fmt[2], fmt[5]) != (1, sample_rate, 16):
                        raise ValueError(f"the server sent audio as {fmt}, not {sample_rate} Hz mono 16-bit")
                    odd = b""
                    while not (stop.is_set() or abort.is_set()) and not answer.isclosed():
                        wait()
                        audio = answer.read1(8192)
                        if not audio:
                            break
                        audio, odd = odd + audio, b""
                        if len(audio) % 2:  # A sample may straddle two reads.
                            audio, odd = audio[:-1], audio[-1:]
                        if audio:
                            if sent is not None:
                                print(f"Medium voice request {rid}: first audio after {time.monotonic() - sent:.2f} s",
                                      file=sys.stderr, flush=True)
                                sent = None
                            got_audio = True
                            yield audio
                finally:
                    generate.last_request = time.monotonic()
                    conn, connection, sock = connection, None, None
                    if conn:
                        conn.close()

        threading.Thread(target=watch, daemon=True).start()
        try:
            if not loaded.is_set():
                load_model()
                raise ValueError(f"the model is not loaded yet ({not_ready})")
            if tempo != 1.0:
                cmd = [
                    ffmpeg, "-hide_banner", "-loglevel", "error",
                    "-fflags", "+nobuffer", "-flags", "low_delay",
                    "-probesize", "32", "-analyzeduration", "0",
                    "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0",
                    "-af", f"atempo={tempo}",
                    "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-flush_packets", "1", "pipe:1",
                ]
                try:
                    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                except OSError as error:
                    if not ffmpeg_warned:
                        ffmpeg_warned = True
                        print(f"Medium voice tempo skipped because ffmpeg could not start: {error}",
                              file=sys.stderr, flush=True)
            if proc is None:
                for audio in raw_audio():
                    started = True
                    yield audio
                    if stop.is_set():
                        return
            else:

                def feed():
                    nonlocal feed_error
                    try:
                        for audio in raw_audio():
                            if stop.is_set() or abort.is_set():
                                return
                            try:
                                proc.stdin.write(audio)
                                proc.stdin.flush()
                            except OSError:
                                return  # ffmpeg closed stdin; the reader checks its exit status.
                    except Exception as error:
                        if not (stop.is_set() or abort.is_set()):
                            feed_error = error
                            if not started:
                                kill_proc()  # Never flush partial broken audio before fallback.
                    finally:
                        try:
                            proc.stdin.close()
                        except OSError:
                            pass

                feeder = threading.Thread(target=feed, daemon=True)
                feeder.start()
                stdout_fd = proc.stdout.fileno()
                odd = b""
                stall_deadline = deadline
                while not stop.is_set():
                    left = stall_deadline - time.monotonic()
                    if left <= 0:
                        raise TimeoutError
                    ready, _, _ = select.select([stdout_fd], [], [], min(left, 0.05))
                    if not ready:
                        continue
                    audio = os.read(stdout_fd, 8192)
                    if not audio:
                        break
                    audio, odd = odd + audio, b""
                    if len(audio) % 2:  # A sample may straddle two reads.
                        audio, odd = audio[:-1], audio[-1:]
                    if audio:
                        started = True
                        yield audio
                        stall_deadline = time.monotonic() + STALL_SECONDS
                if stop.is_set():
                    return
                err = proc.stderr.read(4096).decode(errors="replace").strip()
                rc = proc.wait()
                if feed_error is None and rc != 0:
                    abort.set()
                    shutdown_sock()
                feeder.join(timeout=2)
                if stop.is_set():
                    return
                if feed_error is not None:
                    raise feed_error
                if rc != 0:
                    local_error = True
                    raise ValueError(f"ffmpeg failed (exit {rc})" + (f": {err}" if err else ""))
            if stop.is_set():
                return
            if not started:
                raise ValueError("the server sent no audio")
            return
        except Exception as error:  # Any failure: the owner must still hear the item.
            reason = str(error) if isinstance(error, (OSError, ValueError)) else type(error).__name__
            if isinstance(error, TimeoutError):
                reason = (f"no sound within {first_audio:g} seconds" if not started
                          else f"no sound for {STALL_SECONDS} seconds")
            # A 400 is a bad request or voice, and a slow start after the request arrived is no sign the model left.
            # Anything else may be, a connect that timed out (not connected) too. Local ffmpeg errors never reload.
            reload = (not started and not local_error and status != 400
                      and not (isinstance(error, TimeoutError) and connected) and loaded.is_set())
        finally:
            done.set()
            abort.set()
            if proc is not None and proc.poll() is None:
                kill_proc()
            shutdown_sock()
            if proc is not None:
                proc.wait()
            if feeder is not None and feeder.is_alive():
                feeder.join(timeout=0.5)
            if proc is not None:
                for pipe in (proc.stdin, proc.stdout, proc.stderr):
                    if pipe:
                        try:
                            pipe.close()
                        except OSError:
                            pass
            conn, connection = connection, None
            if conn:
                conn.close()
        if stop.is_set():
            return  # The owner stopped Rook: no fallback and no count.
        if reload:
            loaded.clear()
            load_model()
        if started:
            generate.problem = f"The medium voice stopped mid-item, so the rest of it was skipped: {reason}"
            print(generate.problem, file=sys.stderr, flush=True)
            return
        if audition:
            generate.problem = f"The medium voice could not speak this audition line, so nothing played: {reason}"
            print(generate.problem, file=sys.stderr, flush=True)
            return
        fallbacks += 1
        generate.problem = f"The small voice spoke this item, because the medium voice failed: {reason}"
        print(f"Medium voice fallback {fallbacks} (request {request}): {reason}", file=sys.stderr, flush=True)
        yield from small(text, stop, voices)

    def warm(report):
        """Send one short /tts when no medium request went out for WARM_IDLE_SECONDS, so a server gone cold wakes
        while the owner talks. The audio is dropped at its first byte. report gets one row; a failure is silent."""
        idle = generate.last_request is None or time.monotonic() - generate.last_request >= WARM_IDLE_SECONDS
        if not (loaded.is_set() and idle and warming.acquire(blocking=False)):
            return
        rid, sent = os.urandom(4).hex(), time.monotonic()
        generate.last_request = sent

        def run():
            error = None
            connection = connect(server.hostname, port, timeout=WARM_SECONDS)
            try:
                payload = {"text": WARM_TEXT, "voice": voice, "language": "English"}
                if (limits := temp_range) is not None:
                    payload["temperature"] = medium_temperature(temperature, limits)
                print(f"Medium voice warm-up {rid}: sent", file=sys.stderr, flush=True)
                connection.request("POST", "/tts", json.dumps(payload),
                                   {"Content-Type": "application/json", "X-Request-Id": rid})
                answer = connection.getresponse()  # The server sends its headers with the first audio.
                if answer.status != 200:
                    raise ValueError(f"the server answered {answer.status}")
                answer.read(45)  # The 44-byte WAV header and the first audio byte.
            except Exception as exc:
                error = str(exc) if isinstance(exc, (OSError, ValueError)) else type(exc).__name__
            finally:
                connection.close()
                seconds = round(time.monotonic() - sent, 2)
                generate.last_request = time.monotonic()
                warming.release()
            print(f"Medium voice warm-up {rid}: " + (f"failed after {seconds:g} s: {error}" if error
                  else f"first audio after {seconds:g} s"), file=sys.stderr, flush=True)
            report({"type": "warm", "request": rid, "seconds": seconds, "error": error})
        threading.Thread(target=run, daemon=True).start()

    warming = threading.Lock()  # At most one warm-up in flight.
    generate.problem = generate.last_request = None  # last_request: when the last /tts went out or ended.
    generate.warm = warm
    return generate


def check_words():
    """Self-check speech respellings for WoW Friend, WoW, BiS, and live across both voice engines."""
    global PRONUNCIATIONS
    import http.server
    import io
    import tempfile
    scratch = tempfile.TemporaryDirectory()  # Never the owner's file. It is removed at exit, also after a failure.
    saved, PRONUNCIATIONS = PRONUNCIATIONS, type(PRONUNCIATIONS)(scratch.name) / "pronunciations.json"
    assert respell("Best BiS in WoW: Forever and WoW.") == "Best biss in Wow Forever and Wow."
    assert respell("WOW and WoW's bags.") == "Wow and Wow's bags."
    # Every spelling of WoW Friend (plain, possessive, plural) reaches speech as "wow friend(s)".
    wow_friend_cases = (
        ("Open WoWFriend now.", "Open wow friend now."),
        ("Open WowFriend now.", "Open wow friend now."),
        ("Open wowfriend now.", "Open wow friend now."),
        ("Open WOWFRIEND now.", "Open wow friend now."),
        ("Open WoW Friend now.", "Open wow friend now."),
        ("Open Wow Friend now.", "Open wow friend now."),
        ("WoWFriend's strip is fresh.", "wow friend's strip is fresh."),
        ("WoWFriend\u2019s strip is fresh.", "wow friend\u2019s strip is fresh."),
        ("WowFriend's strip is fresh.", "wow friend's strip is fresh."),
        ("wowfriend's strip is fresh.", "wow friend's strip is fresh."),
        ("WoW Friend's strip is fresh.", "wow friend's strip is fresh."),
        ("Wow Friend's strip is fresh.", "wow friend's strip is fresh."),
        ("Both WoWFriends and WowFriends work.", "Both wow friends and wow friends work."),
        ("Both wowfriends and WOWFRIENDS work.", "Both wow friends and wow friends work."),
        ("WoW Friends and Wow Friends' notes.", "wow friends and wow friends' notes."),
        ("WoWFriends' notes and WoWFriends\u2019 strips.", "wow friends' notes and wow friends\u2019 strips."),
        ("Check mywowfriend and wowfriendly too.", "Check mywowfriend and wowfriendly too."),
    )
    for text, want in wow_friend_cases:
        assert respell(text) == want, (text, respell(text), want)
    assert respell("Everystate, everystate, EveryState and EVERYSTATE's Everystates.") == \
        "every state, every state, every state and every state's every states."
    assert respell("Check myeverystate and everystatement.") == "Check myeverystate and everystatement."
    # Clock times are spoken as times, not "six thousand twenty-four". Ratios, URLs, paths and code keep their digits.
    for text, want in (
        ("Meet at 6:24 PM.", "Meet at six twenty-four PM."),
        ("It starts at 6:05.", "It starts at six oh five."),
        ("Dinner at 6:00 PM.", "Dinner at six PM."),
        ("Doors at 18:30.", "Doors at six thirty PM."),
        ("Leave at 08:15.", "Leave at eight fifteen AM."),
        ("Lunch at 12:00.", "Lunch at twelve o'clock."),
        ("By 12:30 tonight.", "By twelve thirty tonight."),
        ("At 0:45 am, then 11:59 P.M. today.", "At twelve forty-five AM, then eleven fifty-nine PM today."),
        ("Call at 6:24 p.m.", "Call at six twenty-four PM."),
        ("Call at 6:24 p.m. Then rest.", "Call at six twenty-four PM. Then rest."),
        ("From 9:15am to 5:45pm (or 10:10).", "From nine fifteen AM to five forty-five PM (or ten ten)."),
        ("Odds are 3:1 and 10:12 odds.", "Odds are 3:1 and 10:12 odds."),
        ("See https://x.io/at/6:24 and http://10.0.0.1:22 now.", "See https://x.io/at/6:24 and http://10.0.0.1:22 now."),
        ("Run `a[6:24]` on line 12:30:45, at 6:24.5 s, or 24:00.", "Run `a[6:24]` on line 12:30:45, at 6:24.5 s, or 24:00."),
        ("Read main.py:12:4 and 6:24x.", "Read main.py:12:4 and 6:24x."),
    ):
        assert respell(text) == want == respell(text, "medium"), (text, respell(text), want)

    # Stand-in check: verify respelled text reaches both medium (Qwen HTTP /tts) and small-voice paths.
    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 240)
    wav_bytes = wav_buf.getvalue()
    med_seen, small_seen, med_fail, load_done = [], [], [False], threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            body = json.dumps({"loaded": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if self.path == "/tts":
                med_seen.append(json.loads(raw)["text"])
                if med_fail[0]:
                    self.send_response(503)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(wav_bytes)))
                self.end_headers()
                self.wfile.write(wav_bytes)
                return
            self.do_GET()
            if self.path == "/load":
                load_done.set()

    def small_standin(text, stop, voices=None):
        small_seen.append(respell(text))
        yield b"\x00\x00" * 240

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        gen = medium(f"http://127.0.0.1:{srv.server_address[1]}", "jarvis-poe", 24000, small_standin)
        samples = (
            ("WoWFriend, WowFriend, wowfriend, WoW Friend, Wow Friend, WoWFriend's, WoWFriends, and WoW.",
             "wow friend, wow friend, wow friend, wow friend, wow friend, wow friend's, wow friends, and Wow."),
            ("WoW: Forever with WoW Friend's strip.", "Wow Forever with wow friend's strip."),
            ("Raid at 6:24 PM.", "Raid at six twenty-four PM."),
        )
        for raw, want in samples:
            # Medium voice (desk / phone render) and audition.
            assert b"".join(gen(raw, threading.Event())) and med_seen[-1] == want, med_seen[-1]
            assert b"".join(gen(raw, threading.Event(), {"voice_medium": "velvet-wit", "first_audio": 5}))
            assert med_seen[-1] == want, med_seen[-1]
            # Direct small voice selection.
            assert b"".join(gen(raw, threading.Event(), {"voice": "Miles"})) and small_seen[-1] == want, small_seen[-1]
        # The medium voice gets its own adjective spelling, and the verb stays "live".
        assert b"".join(gen("It is live now.", threading.Event())) and med_seen[-1] == "It is lighve now.", med_seen[-1]
        assert LIVE_SPELLING["medium"] == "lighve" and respell("Live, where I live.", "medium") == "Lighve, where I live."
        assert respell("We're live and direct, and this is a live demo.", "medium") == \
            "We're lighve and direct, and this is a lighve demo."
        # The owner's pronunciations reach the voice text only. The caller's text, which captions and logs show,
        # stays as written. An engine's own entry wins over a shared one.
        PRONUNCIATIONS.write_text(json.dumps({"words": {"nginx": "engine x", "Nginx Plus": "engine x plus"},
                                              "medium": {"nginx": "engine ex"}}))
        caption = "Nginx is live on nginx."
        assert b"".join(gen(caption, threading.Event())) and med_seen[-1] == "Engine ex is lighve on engine ex."
        assert b"".join(gen(caption, threading.Event(), {"voice": "Miles"})) and \
            small_seen[-1] == "Engine x is lyve on engine x.", small_seen[-1]
        assert caption == "Nginx is live on nginx." and respell("Nginx Plus", "small") == "Engine x plus"
        # Each sentence is its own request, so a long reply is never one long generation.
        assert b"".join(gen("Done: the list is in. It landed.", threading.Event()))
        assert med_seen[-2:] == ["Done: the list is in.", "It landed."], med_seen[-2:]
        # Medium-to-small fallback after 503.
        med_fail[0] = True
        for raw, want in samples:
            assert b"".join(gen(raw, threading.Event())) and small_seen[-1] == want, small_seen[-1]
        # The small-voice fallback still respells "live".
        assert b"".join(gen("It is live now.", threading.Event())) and small_seen[-1] == "It is lyve now.", small_seen[-1]
        load_done.wait(2.0)
    finally:
        srv.shutdown()
        srv.server_close()

    # Adjective uses become lyve.
    for text, want in (
        ("It's live now.", "It's lyve now."),
        ("It goes live today.", "It goes lyve today."),
        ("The live checkout is ready.", "The lyve checkout is ready."),
        ("Live on staging.", "Lyve on staging."),
        ("Both are live.", "Both are lyve."),
        ("Already live.", "Already lyve."),
        ("You're live now.", "You're lyve now."),
        ("We're live.", "We're lyve."),
        ("Who's live?", "Who's lyve?"),
        ("Live-reload works.", "Lyve-reload works."),
        ("You, live from the desk.", "You, lyve from the desk."),
        ("Switch into live mode.", "Switch into lyve mode."),
        ("Ship it straight to live after testing.", "Ship it straight to lyve after testing."),
        ("Switch to live mode.", "Switch to lyve mode."),
        ("Pushed to live.", "Pushed to lyve."),
        ("it isn't live yet", "it isn't lyve yet"),
        ("it isn\u2019t live yet", "it isn\u2019t lyve yet"),
    ):
        assert respell(text) == want, (text, respell(text), want)
    # Verb markers keep live unchanged.
    for marker in (
        "I", "you", "we", "they", "can", "could", "will", "would", "should",
        "must", "might", "may", "shall", "do", "does", "did", "don't", "doesn't",
        "didn't", "don\u2019t", "can't", "can\u2019t", "cannot", "won't", "won\u2019t",
        "wouldn't", "couldn't", "shouldn't", "mustn't", "who", "I'll", "they'll",
        "we\u2019ll", "I'd", "you'd", "I\u2019d",
    ):
        text = f"{marker} live here."
        assert respell(text) == text, (text, respell(text))
    assert respell("I'd live") == "I'd live"
    for lead in (
        "want", "wants", "wanted", "need", "needs", "have", "has", "had",
        "going", "how", "where", "able", "used",
    ):
        text = f"{lead} to live here."
        assert respell(text) == text, (text, respell(text))
    assert respell("I want to live where it's live now.") == "I want to live where it's lyve now."
    # Lowercase stays lowercase; uppercase becomes Lyve so Phonon does not spell it out.
    assert respell("live Live LIVE") == "lyve Lyve Lyve"
    assert respell("We need to live here and WHO LIVE") == "We need to live here and WHO LIVE"
    # Whole words only.
    whole = "It's alive, olive oil lives on, he lived and kept living."
    assert respell(whole) == whole, respell(whole)
    # The pronunciations file: whole words only. A word with a capital letter matches only that case, and a
    # lowercase word matches any case. A rewrite applies at the next sentence. A broken file gives no entries.
    PRONUNCIATIONS.write_text(json.dumps({"words": {"SQL": "sequel", "C#": "see sharp", "us": "uss"},
                                          "small": ["not", "a", "map"], "medium": {"SQL": 3}, "_note": "kept"}))
    assert respell("SQL and sql, mySQL, C# and C#s. US and us.") == "Sequel and sql, mySQL, See sharp and C#s. Uss and uss."
    assert respell("SQL", "medium") == "Sequel"
    for broken in (b"{not json", b"[1, 2]", b'{"words": "nginx"}', b"\xff\xfe"):
        PRONUNCIATIONS.write_bytes(broken)
        assert respell("SQL us live") == "SQL us lyve", broken
    PRONUNCIATIONS.unlink()
    assert respell("SQL us") == "SQL us" and not pronunciations("medium")
    PRONUNCIATIONS = saved
    print("Speech respelling: all checks passed.")


def check_warm():
    """Self-check the silent warm-up through main() and a stand-in medium voice server. Nothing plays."""
    global load
    import http.server
    import io
    seen, small_seen, plays, warm_cfg = [], [], [], {"delay": 0, "status": 200}
    seen_changed, playing, lines, errors = threading.Condition(), threading.Event(), queue.Queue(), []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            body = json.dumps({"loaded": True}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            text = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}").get("text")
            if self.path != "/tts":
                return self.do_GET()
            with seen_changed:
                seen.append((text, self.headers.get("X-Request-Id")))
                seen_changed.notify_all()
            if text == WARM_TEXT:
                time.sleep(warm_cfg["delay"])
                if warm_cfg["status"] != 200:
                    self.send_response(warm_cfg["status"])
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"RIFF\xff\xff\xff\xffWAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 24000, 48000, 2, 16)
                             + b"data\xff\xff\xff\xff" + b"\x00\x00" * 2400)

    class Lines(io.TextIOBase):
        def __init__(self, sink):
            self.sink, self.part = sink, ""

        def write(self, text):
            self.part += text
            *done, self.part = self.part.split("\n")
            for line in done:
                self.sink(line)
            return len(text)

    def small_standin(text, stop, voices=None):
        small_seen.append(text)
        yield b"\x00\x00" * 240

    def fake_play(sample_rate, volume, generate, text, stop, voiced, on_start, on_length, played, levels=None):
        b"".join(generate(text, stop))
        on_start()
        plays.append(text)
        playing.set()
        stop.wait(0.6)  # The item plays for a while. No sound reaches a device.

    def row(match, seconds=5):
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            try:
                line = json.loads(lines.get(timeout=left))
            except queue.Empty:
                break
            if match(line):
                return line
        raise AssertionError("no matching row from speech.py")

    def wait_seen(count):
        with seen_changed:
            assert seen_changed.wait_for(lambda: len(seen) >= count, 5), seen

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    read_fd, write_fd = os.pipe()
    saved = (load, desk.play_pcm, sys.argv, sys.stdin, sys.stdout, sys.stderr)
    gen = medium(f"http://127.0.0.1:{srv.server_address[1]}", "jarvis-poe", 24000, small_standin)
    assert gen.last_request is None
    load, desk.play_pcm, sys.argv = (lambda args: (24000, gen)), fake_play, ["speech.py", "--engine", "qwen"]
    sys.stdin, sys.stdout, sys.stderr = os.fdopen(read_fd), Lines(lines.put), Lines(errors.append)
    runner = threading.Thread(target=main, daemon=True)
    runner.start()
    to_worker = os.fdopen(write_fd, "w")

    def say(**message):
        to_worker.write(json.dumps(message) + "\n")
        to_worker.flush()
    try:
        # 1. A mic open after 60 s idle sends one warm-up; a second mic open right after sends none.
        gen.last_request = time.monotonic() - WARM_IDLE_SECONDS - 1
        say(type="warm")
        say(type="warm")
        warm = row(lambda r: r.get("type") == "warm")
        assert warm["error"] is None and seen == [(WARM_TEXT, warm["request"])], (warm, seen)
        # 2. A mic open after 10 s idle sends none.
        gen.last_request = time.monotonic() - 10
        say(type="warm")
        time.sleep(0.3)
        assert len(seen) == 1 and not plays, (seen, plays)
        # 3. None while speech plays, even when the last request is old.
        say(type="speak", id="s1", text="Playing now.")
        assert playing.wait(5)
        gen.last_request = time.monotonic() - WARM_IDLE_SECONDS - 1
        say(type="warm")
        assert row(lambda r: r.get("id") == "s1" and "event" not in r)["error"] is None
        assert [text for text, _ in seen] == [WARM_TEXT, "Playing now."], seen
        # 4. A slow warm-up never blocks a real request, and the real request's ID reaches the server and the log.
        warm_cfg["delay"] = 1.5
        gen.last_request = time.monotonic() - WARM_IDLE_SECONDS - 1
        say(type="warm")
        wait_seen(3)
        began = time.monotonic()
        say(type="speak", id="s2", text="Real line.")
        spoke = row(lambda r: r.get("id") == "s2" and "event" not in r)
        assert spoke["error"] is None and "medium_voice" not in spoke and time.monotonic() - began < 1.4, spoke
        warm = row(lambda r: r.get("type") == "warm")
        assert warm["error"] is None and warm["seconds"] >= 1.5, warm
        (rid,) = [rid for text, rid in seen if text == "Real line."]
        assert f"Medium voice request {rid}: sent" in errors and any(
            line.startswith(f"Medium voice request {rid}: first audio after ") for line in errors), errors
        assert f"Medium voice warm-up {warm['request']}: first audio after {warm['seconds']:g} s" in errors, errors
        # 5. A failed warm-up is silent: no small voice, no fallback, and the next item still uses the medium voice.
        warm_cfg.update(delay=0, status=500)
        gen.last_request = time.monotonic() - WARM_IDLE_SECONDS - 1
        say(type="warm")
        assert row(lambda r: r.get("type") == "warm")["error"] == "the server answered 500"
        say(type="speak", id="s3", text="Still medium.")
        assert "medium_voice" not in row(lambda r: r.get("id") == "s3" and "event" not in r)
        assert seen[-1][0] == "Still medium." and not small_seen and not [e for e in errors if "fallback" in e], errors
        # Only the three spoken items played. No warm-up reached playback.
        assert plays == ["Playing now.", "Real line.", "Still medium."], plays
        to_worker.close()
        runner.join(5)
        assert not runner.is_alive()
    finally:
        load, desk.play_pcm, sys.argv, sys.stdin, sys.stdout, sys.stderr = saved
        srv.shutdown()
    print("Medium voice warm-up: all checks passed.")


def encode_render(pcm, sample_rate, dest_path, stop):
    """Encode s16le mono PCM to Ogg Opus (32 kbps) when ffmpeg is on PATH, else WAV, writing mode 0600 to dest_path.
    Return (content_type, error). Never opens pw-play."""
    if stop.is_set():
        return None, "cancelled"
    if not pcm:
        return None, "No audio was generated."
    dest = str(dest_path)
    tmp = f"{dest}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        ffmpeg = desk.find_tool("ffmpeg")
        if ffmpeg:
            proc = subprocess.Popen(
                [ffmpeg, "-v", "error", "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0",
                 "-c:a", "libopus", "-b:a", "32k", "-application", "voip", "-f", "ogg", "pipe:1"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            try:
                out, _ = proc.communicate(pcm, timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                return None, "ffmpeg timed out while encoding audio."
            if stop.is_set():
                return None, "cancelled"
            if proc.returncode != 0 or not out:
                return None, "ffmpeg could not encode audio."
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(out)
            os.replace(tmp, dest)
            return "audio/ogg", None
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as handle:
            with wave.open(handle, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(pcm)
        if stop.is_set():
            return None, "cancelled"
        os.replace(tmp, dest)
        return "audio/wav", None
    except Exception as exc:
        return None, f"{type(exc).__name__}"
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-words", action="store_true", help="Check speech respellings and exit.")
    parser.add_argument("--check-warm", action="store_true", help="Check the medium voice warm-up and exit.")
    parser.add_argument("--engine", choices=("pocket", "phonon", "qwen"), default="pocket",
                        help="qwen speaks through the medium voice server, with Phonon and --voice as its fallback.")
    parser.add_argument("--url", help="qwen only. The medium voice server, such as https://voice.example:8090.")
    parser.add_argument("--voice-medium", default="jarvis-poe", help="qwen only. The medium voice server's voice.")
    parser.add_argument("--model", help="Default: english_7m_2026-10 for Pocket TTS, phonon-31m-en for Phonon.")
    parser.add_argument("--voice", help="Default: alba for Pocket TTS, Miles for Phonon.")
    parser.add_argument("--int8", action="store_true", help="Pocket TTS only. Phonon always loads its 8-bit weights.")
    parser.add_argument("--pace", type=float, default=0.0,
                        help="Phonon and qwen. Negative speaks faster, positive slower. It works from about -0.5 to 0.5.")
    parser.add_argument("--temperature", type=float, default=0.3,
                        help="Phonon and qwen. Lower is steadier, higher is more varied. 0 is the same every time on Phonon.")
    parser.add_argument("--volume", type=float, default=0.5, help="Speech volume for pw-play. 0 is silent.")
    args = parser.parse_args()
    if args.check_words:
        return check_words()
    if args.check_warm:
        return check_warm()
    sample_rate, generate = load(args)
    lock = threading.Condition()
    speaks = collections.deque()
    speech_stops = {}
    renders = collections.deque()
    render_stops = {}
    active_render_id = None
    active_render_stop = None
    eof = False
    busy = False  # The model loop is speaking or rendering an item.
    current = threading.Event()
    stdout_lock = threading.Lock()
    encoders = ThreadPoolExecutor(max_workers=2, thread_name_prefix="speech-encode")

    def emit(payload):
        with stdout_lock:
            print(json.dumps(payload), flush=True)

    def commands():
        # Ordinary desk speech shares a generation. A permission prompt can also be stopped on its own.
        # Renders each carry their own stop event, so desk stop never cancels a render and cancel_render never stops speech.
        nonlocal current, eof
        for line in sys.stdin:
            message = json.loads(line)
            kind = message.get("type")
            with lock:
                if kind == "speak":
                    stop = current
                    if message.get("cancelable"):
                        stop = speech_stops[message["id"]] = threading.Event()
                    speaks.append((message, stop))
                    if active_render_stop is not None:
                        active_render_stop.set()
                elif kind == "cancel_speak":
                    if stop := speech_stops.get(message.get("id")):
                        stop.set()
                elif kind == "render":
                    stop = threading.Event()
                    render_stops[message["id"]] = stop
                    renders.append((message, stop))
                elif kind == "warm":  # The owner opened the mic. Only an idle medium voice warms up.
                    if not (speaks or renders or busy) and hasattr(generate, "warm"):
                        generate.warm(emit)
                elif kind == "cancel_render":
                    rid = message.get("id")
                    if stop := render_stops.get(rid):
                        stop.set()
                        if active_render_stop is not None and active_render_id == rid:
                            active_render_stop.set()
                else:
                    current.set()
                    for stop in speech_stops.values():
                        stop.set()
                    current = threading.Event()
                lock.notify()
        with lock:
            eof = True
            current.set()
            for stop in speech_stops.values():
                stop.set()
            lock.notify()

    def finish_render(rid, pcm, dest_path, seconds, stop, problem=None):
        extra = {"medium_voice": problem} if problem else {}
        try:
            content_type, error = encode_render(pcm, sample_rate, dest_path, stop)
            if error == "cancelled":
                emit({"type": "render", "id": rid, "cancelled": True, "error": "cancelled", **extra})
            elif error:
                emit({"type": "render", "id": rid, "error": error, **extra})
            else:
                emit({"type": "render", "id": rid, "content_type": content_type, "seconds": seconds, "error": None,
                      **extra})
        finally:
            with lock:
                render_stops.pop(rid, None)

    threading.Thread(target=commands, daemon=True).start()
    while True:
        with lock:
            busy = False
            while not speaks and not renders and not eof:
                lock.wait()
            busy = True
            if speaks:
                kind = "speak"
                message, stop = speaks.popleft()
            elif renders:
                kind = "render"
                message, stop = renders.popleft()
            else:
                break
        if kind == "render":
            rid = message["id"]
            if stop.is_set():
                with lock:
                    render_stops.pop(rid, None)
                emit({"type": "render", "id": rid, "cancelled": True, "error": "cancelled"})
                continue
            run_stop = threading.Event()
            with lock:
                if speaks:
                    renders.appendleft((message, stop))
                    continue
                active_render_id = rid
                active_render_stop = run_stop
                if stop.is_set():
                    run_stop.set()
            chunks = []
            error = None
            preempted = False
            try:
                for audio in generate(message["text"], run_stop):
                    if stop.is_set():
                        break
                    with lock:
                        if speaks:
                            preempted = True
                            run_stop.set()
                            break
                    chunks.append(audio)
            except Exception as exc:
                error = type(exc).__name__
            finally:
                with lock:
                    if not stop.is_set() and (preempted or run_stop.is_set()):
                        preempted = True
                    active_render_id = None
                    active_render_stop = None
            problem, generate.__dict__["problem"] = getattr(generate, "problem", None), None
            extra = {"medium_voice": problem} if problem else {}
            if stop.is_set():
                with lock:
                    render_stops.pop(rid, None)
                emit({"type": "render", "id": rid, "cancelled": True, "error": "cancelled", **extra})
                continue
            if preempted:
                with lock:
                    renders.appendleft((message, stop))
                continue
            if error:
                with lock:
                    render_stops.pop(rid, None)
                emit({"type": "render", "id": rid, "error": error, **extra})
                continue
            pcm = b"".join(chunks)
            seconds = round(len(pcm) / (2 * sample_rate), 2)
            # Encode off the model loop so a desk speak request queued meanwhile starts immediately.
            encoders.submit(finish_render, rid, pcm, message["path"], seconds, stop, problem)
            continue
        error = None
        played = [0, 0, 0]
        try:
            # An item may carry its own volume: a voice swap's silent probe speaks at 0.
            volume = message.get("volume", args.volume)
            if not stop.is_set() and volume > 0:
                levels = LevelMeter(message["id"], sample_rate, stop, emit=emit)
                error = desk.play_pcm(
                    # An item's own voices, such as an audition line's, reach generate with it.
                    sample_rate, volume, lambda text, stop: generate(text, stop, message.get("voices")),
                    message["text"], stop, voiced,
                    lambda: emit({"id": message["id"], "event": "start"}),
                    lambda secs: emit({"id": message["id"], "event": "length", "seconds": secs}),
                    played, levels=levels,
                )
        except Exception as exc:
            error = str(exc)
        if message.get("cancelable"):
            with lock:
                speech_stops.pop(message["id"], None)
        problem, generate.__dict__["problem"] = getattr(generate, "problem", None), None
        emit({"id": message["id"], "volume": volume, "error": error,
              "seconds": round(max(0, played[2] - played[1]) / sample_rate, 2),
              **({"medium_voice": problem} if problem else {})})
    encoders.shutdown(wait=True)


if __name__ == "__main__":
    main()
