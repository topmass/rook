"""Standalone Pipecat Smart Turn v3.2 (CPU/ONNX) end-of-turn detector for Rook.

Analyses the trailing 8 seconds of mono 16 kHz speech waveform with a pure-NumPy
Whisper log-mel front-end and an ONNX Runtime CPU session (no transformers,
torch, scipy, or librosa dependencies).

Future alternative: if Smart Turn v3.2 cuts off too early on the owner's voice,
LiveKit Turn Detector v1-mini (~310-340 MB RAM, text-based) is a documented
opt-in alternative that can sit behind the same TurnDecider interface.
"""

from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from typing import Literal
import urllib.request
import wave

import numpy as np

# Allow running directly (`python desktop/turn_end.py ...`) or importing from desktop/.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import desk  # noqa: E402

MODEL_FILENAME = "smart-turn-v3.2-cpu.onnx"
MODEL_URL = "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main/smart-turn-v3.2-cpu.onnx"
MODEL_SIZE_BYTES = 8679182
MODEL_SHA256 = "2bb026316b14a660486a75b1733cd3fbab8c2fd0314dc9af7be49f8cca967e4f"
MODEL_ENV_VAR = "ROOK_SMART_TURN_MODEL"

# Audio and Whisper 80-bin log-mel parameters matching Smart Turn v3.2 / WhisperFeatureExtractor(chunk_length=8).
SAMPLE_RATE = 16000
WINDOW_SECONDS = 8
WINDOW_SAMPLES = SAMPLE_RATE * WINDOW_SECONDS  # 128,000 samples
N_FFT = 400
HOP_LENGTH = 160
N_MELS = 80
N_FRAMES = WINDOW_SAMPLES // HOP_LENGTH  # 800 frames (dropping the trailing 801st STFT frame)
MEL_FLOOR = 1e-10
NORM_VARIANCE_EPS = 1e-7

# Benchmark-optimal thread count on a 16-core desktop with session.intra_op.allow_spinning="0" and
# enable_cpu_mem_arena=False: ~51 ms p50 (~58 ms p95), ~91 ms mean CPU, +61.3 MiB RSS delta
# (vs +71.9 MiB with arena=True, and ~154 ms CPU before disabling ORT thread spinning).
DEFAULT_INTRA_OP_THREADS = 2


def default_model_path(model_path: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the Smart Turn v3.2 ONNX path via explicit arg, env override, or desk.data_dir()."""
    if model_path:
        return Path(model_path).expanduser()
    env_path = os.environ.get(MODEL_ENV_VAR, "").strip()
    if env_path:
        return Path(env_path).expanduser()
    return desk.data_dir() / "rook" / "models" / MODEL_FILENAME


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model(
    path: str | os.PathLike[str] | None = None,
    timeout: float = 60.0,
    expected_sha256: str | None = MODEL_SHA256,
    url: str = MODEL_URL,
    max_bytes: int | None = None,
) -> Path:
    """Ensure smart-turn-v3.2-cpu.onnx exists at path, downloading atomically with size and SHA-256 checks.

    Never called implicitly by --check or SmartTurnDetector.predict().
    """
    target = default_model_path(path)
    exact_size = MODEL_SIZE_BYTES if expected_sha256 == MODEL_SHA256 else None
    cap = MODEL_SIZE_BYTES if max_bytes is None and exact_size is not None else max_bytes

    if target.is_file():
        size = target.stat().st_size
        if exact_size is not None and size != exact_size:
            raise ValueError(
                f"Existing Smart Turn model at {target} has unexpected size "
                f"(got {size}, expected {exact_size} bytes)."
            )
        if cap is not None and size > cap:
            raise ValueError(
                f"Existing Smart Turn model at {target} exceeds max size ({size} > {cap} bytes)."
            )
        if expected_sha256:
            actual = _sha256_file(target)
            if actual != expected_sha256:
                raise ValueError(
                    f"Existing Smart Turn model at {target} failed SHA-256 check "
                    f"(got {actual}, expected {expected_sha256})."
                )
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            digest = hashlib.sha256()
            written = 0
            request = urllib.request.Request(url, headers={"User-Agent": "rook-smart-turn/1.0"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                while chunk := response.read(65536):
                    written += len(chunk)
                    if cap is not None and written > cap:
                        raise ValueError(
                            f"Downloaded Smart Turn model exceeded max size ({written} > {cap} bytes)."
                        )
                    tmp_file.write(chunk)
                    digest.update(chunk)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        if exact_size is not None and written != exact_size:
            raise ValueError(
                f"Downloaded Smart Turn model size mismatch (got {written}, expected {exact_size} bytes)."
            )
        actual = digest.hexdigest()
        if expected_sha256 and actual != expected_sha256:
            raise ValueError(
                f"Downloaded Smart Turn model failed SHA-256 check "
                f"(got {actual}, expected {expected_sha256})."
            )
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, target)
        tmp_path = None
        return target
    finally:
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                tmp_path.unlink()


# ---------------------------------------------------------------------------
# Pure-NumPy Whisper 80-bin log-mel front-end (Slaney mel scale + area norm)
# ---------------------------------------------------------------------------


def _hertz_to_mel_slaney(freq: np.ndarray) -> np.ndarray:
    min_log_hertz = 1000.0
    min_log_mel = 15.0
    logstep = 27.0 / np.log(6.4)
    freq = np.atleast_1d(np.asarray(freq, dtype=np.float64))
    mels = 3.0 * freq / 200.0
    log_region = freq >= min_log_hertz
    mels[log_region] = min_log_mel + np.log(freq[log_region] / min_log_hertz) * logstep
    return mels


def _mel_to_hertz_slaney(mels: np.ndarray) -> np.ndarray:
    min_log_hertz = 1000.0
    min_log_mel = 15.0
    logstep = np.log(6.4) / 27.0
    mels = np.atleast_1d(np.asarray(mels, dtype=np.float64))
    freq = 200.0 * mels / 3.0
    log_region = mels >= min_log_mel
    freq[log_region] = min_log_hertz * np.exp(logstep * (mels[log_region] - min_log_mel))
    return freq


def _build_slaney_mel_filterbank(
    num_frequency_bins: int = N_FFT // 2 + 1,
    num_mel_filters: int = N_MELS,
    min_frequency: float = 0.0,
    max_frequency: float = SAMPLE_RATE / 2.0,
    sampling_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Build the (num_frequency_bins, num_mel_filters) Slaney mel filterbank used by Whisper."""
    mel_min = float(_hertz_to_mel_slaney(np.array([min_frequency], dtype=np.float64))[0])
    mel_max = float(_hertz_to_mel_slaney(np.array([max_frequency], dtype=np.float64))[0])
    mel_freqs = np.linspace(mel_min, mel_max, num_mel_filters + 2)
    filter_freqs = _mel_to_hertz_slaney(mel_freqs)
    fft_freqs = np.linspace(0.0, sampling_rate // 2, num_frequency_bins)

    filter_diff = np.diff(filter_freqs)
    slopes = np.expand_dims(filter_freqs, 0) - np.expand_dims(fft_freqs, 1)
    down_slopes = -slopes[:, :-2] / filter_diff[:-1]
    up_slopes = slopes[:, 2:] / filter_diff[1:]
    mel_filters = np.maximum(0.0, np.minimum(down_slopes, up_slopes))

    # Slaney area normalization: each triangular filter integrates to ~1.
    enorm = 2.0 / (filter_freqs[2 : num_mel_filters + 2] - filter_freqs[:num_mel_filters])
    mel_filters *= np.expand_dims(enorm, 0)
    return mel_filters


def _periodic_hann_window(window_length: int = N_FFT) -> np.ndarray:
    """Periodic Hann window matching torch.hann_window(n_fft, periodic=True)."""
    return np.hanning(window_length + 1)[:-1].astype(np.float64)


# Cached immutable DSP constants.
_HANN_WINDOW = _periodic_hann_window(N_FFT)
_MEL_FILTERS = _build_slaney_mel_filterbank()
_HANN_WINDOW.setflags(write=False)
_MEL_FILTERS.setflags(write=False)


def _compile_mel_spans(mel_filters: np.ndarray) -> tuple[tuple[int, int, np.ndarray], ...]:
    """Precompute non-zero (start, end, weights) spans for each triangular mel filter.

    Projecting via these sparse spans avoids invoking BLAS dgemm (`_MEL_FILTERS.T @ power`),
    which otherwise wakes OpenBLAS's multi-threaded spin pool (~800% CPU for ~100ms) on
    systems where OPENBLAS_NUM_THREADS is unset.
    """
    spans: list[tuple[int, int, np.ndarray]] = []
    for col in range(mel_filters.shape[1]):
        nz = np.flatnonzero(mel_filters[:, col])
        start, end = int(nz[0]), int(nz[-1]) + 1
        weights = np.ascontiguousarray(mel_filters[start:end, col], dtype=np.float64)
        weights.setflags(write=False)
        spans.append((start, end, weights))
    return tuple(spans)


_MEL_SPANS = _compile_mel_spans(_MEL_FILTERS)


def _project_mel(power: np.ndarray) -> np.ndarray:
    """Project (201, frames) power spectrogram onto 80 mel bins without triggering BLAS threads."""
    out = np.empty((len(_MEL_SPANS), power.shape[1]), dtype=np.float64)
    for idx, (start, end, weights) in enumerate(_MEL_SPANS):
        out[idx] = (weights[:, None] * power[start:end]).sum(axis=0)
    return out


def _to_mono_float32(audio: np.ndarray | list[float] | None) -> np.ndarray:
    """Convert raw PCM (int16/int32/uint8/float, 1D or multi-channel 2D) to 1D float32 in [-1, 1]."""
    if audio is None:
        return np.empty(0, dtype=np.float32)
    arr = np.asarray(audio)
    if arr.size == 0:
        return np.empty(0, dtype=np.float32)

    if np.issubdtype(arr.dtype, np.integer):
        if arr.dtype == np.uint8:
            arr = (arr.astype(np.float32) - 128.0) / 128.0
        else:
            scale = float(1 << (arr.dtype.itemsize * 8 - 1))
            arr = arr.astype(np.float32) / scale
    else:
        arr = arr.astype(np.float32, copy=False)

    if arr.ndim == 2:
        if arr.shape[1] == 1:
            arr = arr[:, 0]
        elif arr.shape[0] == 1:
            arr = arr[0, :]
        elif arr.shape[0] <= 8 < arr.shape[1]:
            arr = arr.mean(axis=0, dtype=np.float32)
        else:
            arr = arr.mean(axis=1, dtype=np.float32)
    elif arr.ndim > 2:
        arr = arr.reshape(arr.shape[0], -1).mean(axis=1, dtype=np.float32)

    if not np.all(np.isfinite(arr)):
        arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0)
    return np.ascontiguousarray(arr, dtype=np.float32)


def _linear_resample(audio: np.ndarray, src_rate: int, dst_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Linearly resample a 1D float32 waveform from src_rate to dst_rate using pure NumPy."""
    if src_rate <= 0:
        raise ValueError(f"sample_rate must be positive, got {src_rate}")
    if src_rate == dst_rate or audio.size == 0:
        return audio
    if audio.size == 1:
        return audio.copy()
    dst_len = max(1, int(round(audio.size * dst_rate / src_rate)))
    if dst_len == audio.size:
        return audio
    src_idx = np.linspace(0.0, audio.size - 1, num=dst_len, dtype=np.float64)
    return np.interp(src_idx, np.arange(audio.size, dtype=np.float64), audio).astype(np.float32)


def truncate_audio_to_last_n_seconds(
    audio: np.ndarray,
    n_seconds: float = WINDOW_SECONDS,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Match Pipecat's contract: keep the trailing n_seconds, or left-pad shorter clips with zeros."""
    max_samples = int(round(n_seconds * sample_rate))
    if audio.size > max_samples:
        return audio[-max_samples:]
    if audio.size < max_samples:
        return np.pad(audio, (max_samples - audio.size, 0), mode="constant", constant_values=0.0)
    return audio


def extract_whisper_mel(
    audio: np.ndarray | list[float] | None,
    sample_rate: int = SAMPLE_RATE,
    *,
    do_normalize: bool = True,
) -> np.ndarray:
    """Compute the (1, 80, 800) float32 Whisper log-mel spectrogram expected by Smart Turn v3.2.

    Matches Pipecat's `truncate_audio_to_last_n_seconds(audio, 8)` followed by
    HuggingFace `WhisperFeatureExtractor(chunk_length=8)(..., do_normalize=True)`:
      1. Convert to mono float32; slice trailing 8s if resampling from another rate.
      2. Truncate to the last 8s (128,000 samples) or zero-pad at the beginning (left).
      3. Apply zero-mean unit-variance waveform normalization in float32 (when do_normalize=True).
      4. Centered reflect-padded STFT (n_fft=400, hop_length=160, periodic Hann window), |STFT|^2.
      5. Project onto 80 Slaney mel filters (Slaney area norm), clamp to 1e-10, log10, drop last frame.
      6. Clamp to max - 8.0 and normalize with (x + 4.0) / 4.0.
    """
    x = _to_mono_float32(audio)
    if sample_rate != SAMPLE_RATE and x.size > 0:
        # Keep a small margin past 8s before resampling so very long inputs stay O(8s).
        max_src = int(math.ceil(WINDOW_SECONDS * sample_rate)) + 16
        if x.size > max_src:
            x = x[-max_src:]
        x = _linear_resample(x, sample_rate, SAMPLE_RATE)

    x = truncate_audio_to_last_n_seconds(x, n_seconds=WINDOW_SECONDS, sample_rate=SAMPLE_RATE)

    if do_normalize:
        x = (x - x.mean()) / np.sqrt(x.var() + np.float32(NORM_VARIANCE_EPS))

    pad = N_FFT // 2
    padded = np.pad(x.astype(np.float64), (pad, pad), mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, N_FFT)[::HOP_LENGTH]
    spec = np.fft.rfft(frames * _HANN_WINDOW, axis=-1)
    power = (spec.real * spec.real + spec.imag * spec.imag).T  # (201, 801)

    mel_spec = np.maximum(MEL_FLOOR, _project_mel(power))
    log_spec = np.log10(mel_spec)[:, :N_FRAMES]  # (80, 800), drops trailing 801st frame
    log_spec = np.maximum(log_spec, log_spec.max() - 8.0)
    log_spec = (log_spec + 4.0) / 4.0
    return np.ascontiguousarray(log_spec[np.newaxis, :, :], dtype=np.float32)


def trim_trailing_silence(
    audio: np.ndarray,
    sample_rate: int = SAMPLE_RATE,
    *,
    max_tail_s: float = 0.20,
    rms_threshold: float = 0.008,
) -> np.ndarray:
    """Cap trailing silence past the last voiced 20 ms frame to max_tail_s.

    Smart Turn v3.2 was trained on Silero VAD segments with ~0.20s of trailing silence;
    capping longer silence tails preserves genuine mid-thought prosody.
    """
    arr = _to_mono_float32(audio)
    if arr.size == 0 or max_tail_s < 0:
        return arr
    win = max(1, int(round(0.02 * sample_rate)))
    n_frames = arr.size // win
    if n_frames == 0:
        return arr
    offset = arr.size - n_frames * win
    frames = arr[offset:].reshape(n_frames, win)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    voiced = np.flatnonzero(rms >= rms_threshold)
    if voiced.size == 0:
        return arr
    last_voiced = offset + (int(voiced[-1]) + 1) * win
    target_end = min(arr.size, last_voiced + int(round(max_tail_s * sample_rate)))
    return arr[:target_end]


def snapshot_capture_audio(
    capture: object | None,
    max_seconds: float = float(WINDOW_SECONDS),
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Safely copy the trailing max_seconds of mono float32 PCM from an AirType RecordingSession.

    Holds `capture._audio_lock` only long enough to reference the tail chunks needed from
    `capture._audio_data`, never mutating `_audio_data`. Handles None, empty buffers,
    1D (N,) chunks, and 2D (N, 1) / (N, C) sounddevice chunks cleanly.
    """
    if capture is None:
        return np.empty(0, dtype=np.float32)

    max_samples = max(0, int(round(max_seconds * sample_rate)))
    if max_samples == 0:
        return np.empty(0, dtype=np.float32)

    lock = getattr(capture, "_audio_lock", None)
    ctx = lock if lock is not None else contextlib.nullcontext()
    tail_chunks: list[np.ndarray] = []
    collected = 0
    with ctx:
        chunks = getattr(capture, "_audio_data", None)
        if not chunks:
            return np.empty(0, dtype=np.float32)
        for chunk in reversed(chunks):
            arr = np.asarray(chunk)
            if arr.size == 0:
                continue
            n_frames = arr.shape[0] if arr.ndim >= 1 else 0
            if n_frames == 0:
                continue
            tail_chunks.append(arr)
            collected += n_frames
            if collected >= max_samples:
                break

    if not tail_chunks:
        return np.empty(0, dtype=np.float32)

    tail_chunks.reverse()
    mono_chunks = [_to_mono_float32(chunk) for chunk in tail_chunks]
    audio = np.concatenate(mono_chunks, axis=0) if len(mono_chunks) > 1 else mono_chunks[0].copy()
    if audio.size > max_samples:
        audio = audio[-max_samples:].copy()
    return np.ascontiguousarray(audio, dtype=np.float32)


def tail_is_quiet(
    capture: object | None,
    seconds: float,
    *,
    rms_threshold: float = 0.008,
    sample_rate: int = SAMPLE_RATE,
) -> bool:
    """Return True iff every 20 ms frame in the trailing `seconds` of capture stays below rms_threshold."""
    if seconds <= 0:
        return True
    audio = snapshot_capture_audio(capture, max_seconds=seconds, sample_rate=sample_rate)
    if audio.size == 0:
        return True
    win = max(1, int(round(0.02 * sample_rate)))
    usable = (audio.size // win) * win
    if usable > 0:
        frames = audio[audio.size - usable :].reshape(-1, win)
        if float(np.sqrt(np.mean(frames * frames, axis=1)).max()) >= rms_threshold:
            return False
    rem = audio.size - usable
    if rem > 0:
        head = audio[:rem]
        if float(np.sqrt(np.mean(head * head))) >= rms_threshold:
            return False
    return True


# ---------------------------------------------------------------------------
# ONNX Runtime CPU detector & pause decision state machine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnResult:
    complete: bool
    probability: float
    elapsed_ms: float
    error: str | None = None


class SmartTurnDetector:
    """Lazy, fail-open ONNX Runtime CPU wrapper for Pipecat Smart Turn v3.2."""

    def __init__(
        self,
        model_path: str | os.PathLike[str] | None = None,
        *,
        intra_op_num_threads: int = DEFAULT_INTRA_OP_THREADS,
        inter_op_num_threads: int = 1,
        enable_cpu_mem_arena: bool = False,
    ) -> None:
        self.model_path = default_model_path(model_path)
        self.intra_op_num_threads = max(1, int(intra_op_num_threads))
        self.inter_op_num_threads = max(1, int(inter_op_num_threads))
        self.enable_cpu_mem_arena = bool(enable_cpu_mem_arena)
        self._lock = threading.Lock()
        self._session = None
        self._input_name = "input_features"
        self._output_name: str | None = None
        self._last_error: str | None = None
        self._load_failed = False
        self._ort_spec_checked = False
        self._ort_spec_present = False
        self._ort_checked = False
        self._ort_mod = None
        self._model_present: bool | None = None

    @staticmethod
    def _import_ort():
        try:
            import onnxruntime as ort
            return ort
        except Exception:
            return None

    def _has_ort(self) -> bool:
        """Cheap non-importing check for onnxruntime so available() never stalls an event loop."""
        if self._ort_checked:
            return self._ort_mod is not None
        if not self._ort_spec_checked:
            try:
                self._ort_spec_present = importlib.util.find_spec("onnxruntime") is not None
            except Exception:
                self._ort_spec_present = False
            self._ort_spec_checked = True
        return self._ort_spec_present

    def _get_ort(self):
        if not self._ort_checked:
            self._ort_mod = self._import_ort()
            self._ort_checked = True
            self._ort_spec_checked = True
            self._ort_spec_present = self._ort_mod is not None
        return self._ort_mod

    def reset_availability(self) -> None:
        """Clear cached model presence and load-failure state without taking _lock (safe on event loop)."""
        self._model_present = None
        self._load_failed = False

    def available(self, *, refresh: bool = False) -> bool:
        """Return True iff onnxruntime is installed, the ONNX model file exists, and load has not failed."""
        if self._load_failed:
            return False
        if not self._has_ort():
            return False
        if refresh or self._model_present is None:
            self._model_present = self.model_path.is_file()
        return self._model_present

    def load(self) -> bool:
        """Lazily create the CPU ONNX Runtime session. Fail-open: returns False on error."""
        with self._lock:
            if self._session is not None:
                return True
            if self._load_failed:
                return False
            ort = self._get_ort()
            if ort is None:
                self._last_error = "onnxruntime_missing"
                return False
            if not self.model_path.is_file():
                self._model_present = False
                self._last_error = f"model_missing:{self.model_path}"
                return False
            self._model_present = True
            try:
                so = ort.SessionOptions()
                so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                so.inter_op_num_threads = self.inter_op_num_threads
                so.intra_op_num_threads = self.intra_op_num_threads
                so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                so.add_session_config_entry("session.intra_op.allow_spinning", "0")
                so.enable_cpu_mem_arena = self.enable_cpu_mem_arena
                session = ort.InferenceSession(
                    str(self.model_path),
                    sess_options=so,
                    providers=["CPUExecutionProvider"],
                )
                self._input_name = session.get_inputs()[0].name
                self._output_name = session.get_outputs()[0].name
                self._session = session
                self._last_error = None
                return True
            except Exception as exc:
                self._session = None
                self._load_failed = True
                self._last_error = f"{type(exc).__name__}:{exc}"
                return False

    def unload(self) -> None:
        """Release the loaded ONNX Runtime session and reset cached availability/failure state."""
        with self._lock:
            self._session = None
            self._load_failed = False
            self._model_present = None

    def predict(
        self,
        audio: np.ndarray | list[float] | None,
        sample_rate: int = SAMPLE_RATE,
        threshold: float = 0.5,
    ) -> TurnResult:
        """Predict whether the trailing audio ends a spoken turn. Never raises."""
        started = time.perf_counter()
        if not self.load():
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return TurnResult(
                complete=False,
                probability=0.0,
                elapsed_ms=elapsed_ms,
                error=self._last_error or "model_unavailable",
            )
        try:
            features = extract_whisper_mel(audio, sample_rate=sample_rate)
            with self._lock:
                session = self._session
                input_name = self._input_name
                if session is None:
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    return TurnResult(
                        complete=False,
                        probability=0.0,
                        elapsed_ms=elapsed_ms,
                        error="session_unloaded",
                    )
                # The ONNX output tensor is named 'logits' but terminates in a Sigmoid node,
                # so outputs[0] is already the end-of-turn probability in [0, 1].
                outputs = session.run(None, {input_name: features})
            prob = float(np.asarray(outputs[0]).reshape(-1)[0])
            if not math.isfinite(prob):
                raise ValueError(f"non-finite probability {prob!r}")
            prob = max(0.0, min(1.0, prob))
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return TurnResult(
                complete=prob >= threshold,
                probability=prob,
                elapsed_ms=elapsed_ms,
                error=None,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return TurnResult(
                complete=False,
                probability=0.0,
                elapsed_ms=elapsed_ms,
                error=f"{type(exc).__name__}:{exc}",
            )


# A pause after one of these words is a thought left open, not the end of a turn. Every spoken request in the
# turn log that ended on one with no closing punctuation was cut mid-thought (4 of 520 on 2026-11-26).
HANGING_WORDS = frozenset("like um uh and but so because the a an to of my your or then".split())
HANGING_PAIRS = frozenset({("you", "know"), ("i", "mean")})
# The longest the transcript check may hold a Smart Turn "complete". A later answer is dropped, and Smart Turn's stands.
TAIL_TEXT_SECONDS = 1.5


def ends_mid_thought(text: str | None) -> bool:
    """True when a transcript stops on a hanging word with no closing . ? or !. A trailing "..." stays open."""
    text = (text or "").strip()
    if not text or (text[-1] in ".?!" and not text.endswith("...")):
        return False
    words = [w.strip(",;:-\"'.\u2026").lower() for w in text.split()]
    return words[-1] in HANGING_WORDS or tuple(words[-2:]) in HANGING_PAIRS


@dataclass(frozen=True)
class TurnDecision:
    """Action returned by TurnDecider for listen_after().

    - "wait": keep listening (pause too short, speech too short, already decided, rate-limited, or model says incomplete).
    - "complete": Smart Turn detected end-of-turn; caller can stop recording and transcribe now.
    - "fallback": Smart Turn is not deciding this pause (max_wait_s reached, detector unavailable,
      or inference errored); caller falls back to the fixed max_wait_s pause timeout.
    """

    action: Literal["wait", "complete", "fallback"]
    probability: float | None = None
    elapsed_ms: float | None = None
    reason: str = ""


class TurnDecider:
    """Pause decision controller sitting behind the VAD gate in listen_after().

    By default (`recheck_interval_s=None`), runs Smart Turn once per pause (matching Pipecat's
    contract when trailing silence is trimmed to 0.20s). Pass a positive `recheck_interval_s`
    for rate-limited rechecks on untrimmed audio.
    """

    def __init__(
        self,
        detector: SmartTurnDetector | None,
        *,
        threshold: float = 0.5,
        initial_pause_s: float = 0.45,
        recheck_interval_s: float | None = None,
        max_wait_s: float = 4.5,
        min_speech_s: float = 0.25,
        tail_text_fn=None,
        tail_text_timeout_s: float = TAIL_TEXT_SECONDS,
    ) -> None:
        self.detector = detector
        # Optional audio -> transcript of the same clip. A "complete" that ends on a hanging word waits instead.
        self.tail_text_fn = tail_text_fn
        self.tail_text_timeout_s = float(tail_text_timeout_s)
        self.threshold = float(threshold)
        self.initial_pause_s = float(initial_pause_s)
        self.recheck_interval_s = None if recheck_interval_s is None else float(recheck_interval_s)
        self.max_wait_s = float(max_wait_s)
        self.min_speech_s = float(min_speech_s)
        self._last_check_at: float | None = None
        self._checked_pause = False
        self._last_probability: float | None = None
        self._last_quiet_seconds: float | None = None
        self.checks = 0

    def reset(self) -> None:
        """Reset pause check state whenever speech resumes."""
        self._last_check_at = None
        self._checked_pause = False
        self._last_probability = None
        self._last_quiet_seconds = None

    def due(
        self,
        quiet_seconds: float,
        speech_seconds: float,
        now: float,
    ) -> TurnDecision | None:
        """Cheap event-loop gate (zero I/O or inference). Returns None when check() should run."""
        if self._last_quiet_seconds is not None and quiet_seconds < self._last_quiet_seconds:
            self.reset()
        self._last_quiet_seconds = quiet_seconds

        if quiet_seconds >= self.max_wait_s:
            return TurnDecision(
                action="fallback",
                probability=self._last_probability,
                elapsed_ms=None,
                reason="max_wait",
            )
        if speech_seconds < self.min_speech_s:
            return TurnDecision(action="wait", probability=None, elapsed_ms=None, reason="min_speech")
        if quiet_seconds < self.initial_pause_s:
            return TurnDecision(action="wait", probability=None, elapsed_ms=None, reason="initial_pause")
        if self.detector is None or not self.detector.available():
            return TurnDecision(action="fallback", probability=None, elapsed_ms=None, reason="detector_unavailable")

        if self.recheck_interval_s is None:
            if self._checked_pause:
                return TurnDecision(
                    action="wait",
                    probability=self._last_probability,
                    elapsed_ms=None,
                    reason="decided",
                )
        elif self._last_check_at is not None and (now - self._last_check_at) < self.recheck_interval_s:
            return TurnDecision(
                action="wait",
                probability=self._last_probability,
                elapsed_ms=None,
                reason="rate_limited",
            )
        return None

    def check(self, now: float, audio_fn) -> TurnDecision:
        """Run audio snapshot + Smart Turn inference (intended for asyncio.to_thread).

        Mutates pause state from the worker thread; callers must await check() before the next due()/reset().
        """
        self._last_check_at = now
        self._checked_pause = True
        try:
            audio = audio_fn()
        except Exception as exc:
            return TurnDecision(
                action="fallback",
                probability=None,
                elapsed_ms=None,
                reason=f"audio_error:{type(exc).__name__}",
            )

        if audio is None or np.asarray(audio).size == 0:
            return TurnDecision(action="wait", probability=None, elapsed_ms=None, reason="empty_audio")

        if self.detector is None:
            return TurnDecision(action="fallback", probability=None, elapsed_ms=None, reason="detector_unavailable")

        self.checks += 1
        result = self.detector.predict(audio, sample_rate=SAMPLE_RATE, threshold=self.threshold)
        if result.error:
            return TurnDecision(
                action="fallback",
                probability=None,
                elapsed_ms=result.elapsed_ms,
                reason=f"detector_error:{result.error}",
            )
        self._last_probability = result.probability
        if result.complete and self.tail_text_fn is not None:
            # A daemon thread, so a hung recogniser never holds this check, the recording's end or Rook's exit.
            # Fail open: no transcript in time, or an error, keeps the Smart Turn answer.
            box = []
            fn = self.tail_text_fn

            def run():
                with contextlib.suppress(Exception):
                    box.append(fn(audio))

            worker = threading.Thread(target=run, name="rook-tail-text", daemon=True)
            worker.start()
            worker.join(self.tail_text_timeout_s)
            if ends_mid_thought(box[0] if box else None):
                return TurnDecision(
                    action="wait",
                    probability=result.probability,
                    elapsed_ms=result.elapsed_ms,
                    reason="mid_thought",
                )
        if result.complete:
            return TurnDecision(
                action="complete",
                probability=result.probability,
                elapsed_ms=result.elapsed_ms,
                reason="smart_turn",
            )
        return TurnDecision(
            action="wait",
            probability=result.probability,
            elapsed_ms=result.elapsed_ms,
            reason="incomplete",
        )

    def step(
        self,
        quiet_seconds: float,
        speech_seconds: float,
        now: float,
        audio_fn,
    ) -> TurnDecision:
        """Decide whether to wait, end the turn, or fall back to the fixed pause cap."""
        gate = self.due(quiet_seconds, speech_seconds, now)
        if gate is not None:
            return gate
        return self.check(now, audio_fn)


# ---------------------------------------------------------------------------
# Offline self-check (--check)
# ---------------------------------------------------------------------------


def run_check() -> None:
    """Run fast, completely offline unit checks using scratch XDG folders only."""
    # 1. Slaney mel filterbank properties.
    assert _MEL_FILTERS.shape == (N_FFT // 2 + 1, N_MELS), _MEL_FILTERS.shape
    assert np.all(np.isfinite(_MEL_FILTERS))
    assert float(_MEL_FILTERS.min()) >= 0.0
    assert np.all(_MEL_FILTERS.sum(axis=0) > 0.0), "Every mel filter must have positive support."
    assert _HANN_WINDOW.shape == (N_FFT,)
    assert abs(float(_HANN_WINDOW[0])) < 1e-12
    assert abs(float(_HANN_WINDOW[N_FFT // 2]) - 1.0) < 1e-12
    # Sparse mel projection must match dense matrix multiplication to floating-point precision.
    probe_power = np.linspace(0.0, 1.0, (N_FFT // 2 + 1) * 16, dtype=np.float64).reshape(N_FFT // 2 + 1, 16)
    assert np.allclose(_project_mel(probe_power), _MEL_FILTERS.T @ probe_power, atol=1e-12)

    # 2. Silence input -> exact Whisper clamp/normalization value (-1.5).
    mel_silence = extract_whisper_mel(np.zeros(SAMPLE_RATE, dtype=np.float32))
    assert mel_silence.shape == (1, N_MELS, N_FRAMES), mel_silence.shape
    assert mel_silence.dtype == np.float32
    assert np.all(np.isfinite(mel_silence))
    assert np.allclose(mel_silence, -1.5, atol=1e-5), (mel_silence.min(), mel_silence.max())

    # Empty / None input also yields silence features cleanly.
    assert np.allclose(extract_whisper_mel(None), mel_silence)
    assert np.allclose(extract_whisper_mel(np.array([], dtype=np.float32)), mel_silence)

    # 3. Tone signal: dynamic range bound <= 2.0 (8 dB / 4.0) and left-padding vs right-truncation.
    t1 = np.arange(SAMPLE_RATE, dtype=np.float32) / SAMPLE_RATE
    tone_1s = (0.25 * np.sin(2.0 * np.pi * 440.0 * t1)).astype(np.float32)
    mel_1s = extract_whisper_mel(tone_1s)
    assert mel_1s.shape == (1, N_MELS, N_FRAMES)
    assert mel_1s.dtype == np.float32
    assert np.all(np.isfinite(mel_1s))
    assert float(mel_1s.max() - mel_1s.min()) <= 2.0 + 1e-5, (mel_1s.min(), mel_1s.max())
    # Short 1s clip is left-padded, so tone energy must live in the trailing 100 frames, not the first 600.
    leading_peak = float(mel_1s[0, :, :600].max(axis=0).mean())
    trailing_peak = float(mel_1s[0, :, 705:795].max(axis=0).mean())
    assert trailing_peak > leading_peak + 1.0, (leading_peak, trailing_peak)

    # Long 12s clip: leading 4s tone + trailing 8s silence must match silence (right-truncation to last 8s).
    long_old_tone = np.concatenate([
        np.tile(tone_1s, 4),
        np.zeros(WINDOW_SAMPLES, dtype=np.float32),
    ])
    assert np.allclose(extract_whisper_mel(long_old_tone), mel_silence, atol=1e-5)

    # Long 12s clip: leading 11s silence + trailing 1s tone must match the 1s clip exactly.
    long_recent_tone = np.concatenate([
        np.zeros(11 * SAMPLE_RATE, dtype=np.float32),
        tone_1s,
    ])
    assert np.allclose(extract_whisper_mel(long_recent_tone), mel_1s, atol=1e-5)

    # 4. 2D stereo, (N, 1), and int16 inputs.
    mel_col = extract_whisper_mel(tone_1s[:, None])
    mel_stereo = extract_whisper_mel(np.stack([tone_1s, tone_1s], axis=1))
    tone_i16 = np.clip(np.rint(tone_1s * 32768.0), -32768, 32767).astype(np.int16)
    mel_i16 = extract_whisper_mel(tone_i16)
    assert np.allclose(mel_col, mel_1s, atol=1e-5)
    assert np.allclose(mel_stereo, mel_1s, atol=1e-5)
    assert np.allclose(mel_i16, mel_1s, atol=5e-3), float(np.max(np.abs(mel_i16 - mel_1s)))

    # 5. Linear resampling: 24 kHz 440 Hz tone matches native 16 kHz 440 Hz tone closely.
    t24 = np.arange(24000, dtype=np.float32) / 24000.0
    tone_24k = (0.25 * np.sin(2.0 * np.pi * 440.0 * t24)).astype(np.float32)
    mel_24k = extract_whisper_mel(tone_24k, sample_rate=24000)
    assert mel_24k.shape == (1, N_MELS, N_FRAMES)
    # Peak mel bin in the active trailing region must match.
    peak_16k = int(np.argmax(mel_1s[0, :, 720:780].mean(axis=1)))
    peak_24k = int(np.argmax(mel_24k[0, :, 720:780].mean(axis=1)))
    assert peak_16k == peak_24k, (peak_16k, peak_24k)

    # 6. snapshot_capture_audio with fake RecordingSession.
    class FakeCapture:
        def __init__(self, chunks):
            self._audio_lock = threading.RLock()
            self._audio_data = chunks

    assert snapshot_capture_audio(None).size == 0
    assert snapshot_capture_audio(FakeCapture([])).size == 0

    c1 = np.arange(100, dtype=np.float32)
    c2 = np.arange(100, 250, dtype=np.float32).reshape(-1, 1)
    cap_mixed = FakeCapture([c1, c2])
    snap_mixed = snapshot_capture_audio(cap_mixed)
    assert snap_mixed.dtype == np.float32 and snap_mixed.shape == (250,)
    assert np.array_equal(snap_mixed, np.arange(250, dtype=np.float32))
    assert len(cap_mixed._audio_data) == 2

    # >8s buffer: 10 chunks of 1s each -> tail 8s only, original list untouched.
    one_sec_chunks = [np.full((SAMPLE_RATE, 1), float(i), dtype=np.float32) for i in range(10)]
    cap_long = FakeCapture(list(one_sec_chunks))
    snap_long = snapshot_capture_audio(cap_long, max_seconds=8.0, sample_rate=SAMPLE_RATE)
    assert snap_long.shape == (WINDOW_SAMPLES,)
    assert float(snap_long[0]) == 2.0 and float(snap_long[-1]) == 9.0
    assert len(cap_long._audio_data) == 10
    assert float(cap_long._audio_data[0][0, 0]) == 0.0

    # 6b. trim_trailing_silence caps long silence tails without cutting voiced speech,
    # and handles pure silence and <20 ms short clips cleanly.
    with_long_tail = np.concatenate([tone_1s, np.zeros(2 * SAMPLE_RATE, dtype=np.float32)])
    trimmed_tail = trim_trailing_silence(with_long_tail, sample_rate=SAMPLE_RATE, max_tail_s=0.20)
    assert abs(trimmed_tail.size - int(1.20 * SAMPLE_RATE)) <= int(0.03 * SAMPLE_RATE), trimmed_tail.size
    pure_silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
    assert trim_trailing_silence(pure_silence, sample_rate=SAMPLE_RATE).size == pure_silence.size
    short_clip = np.full(int(0.01 * SAMPLE_RATE), 0.2, dtype=np.float32)  # 10 ms < 20 ms window
    assert np.array_equal(trim_trailing_silence(short_clip, sample_rate=SAMPLE_RATE), short_clip)

    # 7. TurnDecider with fake detector.
    class FakeDetector:
        def __init__(self, responses, avail=True):
            self._responses = list(responses)
            self._avail = avail
            self.calls = 0

        def available(self):
            return self._avail

        def predict(self, audio, sample_rate=SAMPLE_RATE, threshold=0.5):
            self.calls += 1
            item = self._responses[min(self.calls - 1, len(self._responses) - 1)]
            if isinstance(item, str):
                return TurnResult(complete=False, probability=0.0, elapsed_ms=1.0, error=item)
            prob = float(item)
            return TurnResult(complete=prob >= threshold, probability=prob, elapsed_ms=12.0, error=None)

    audio_calls = [0]

    def fake_audio():
        audio_calls[0] += 1
        return tone_1s

    # 7a. min_speech_s and initial_pause_s guards, due()/check() split, then immediate completion.
    det_done = FakeDetector([0.91])
    dec = TurnDecider(det_done, threshold=0.5, initial_pause_s=0.45, max_wait_s=4.5, min_speech_s=0.25)
    assert dec.due(quiet_seconds=0.50, speech_seconds=0.10, now=1.00).reason == "min_speech"
    assert dec.due(quiet_seconds=0.20, speech_seconds=1.00, now=1.10).reason == "initial_pause"
    assert det_done.calls == 0 and audio_calls[0] == 0
    assert dec.due(quiet_seconds=0.45, speech_seconds=1.00, now=1.45) is None
    d_complete = dec.check(now=1.45, audio_fn=fake_audio)
    assert d_complete.action == "complete" and abs((d_complete.probability or 0.0) - 0.91) < 1e-6
    assert det_done.calls == 1

    # 7b. Default once-per-pause ("decided") behavior + auto-reset on decreasing quiet_seconds + reset() clears prob.
    det_once = FakeDetector([0.12, 0.89])
    dec_once = TurnDecider(det_once, threshold=0.5, initial_pause_s=0.45, max_wait_s=4.5, min_speech_s=0.25)
    d1 = dec_once.step(0.45, 1.0, 10.00, fake_audio)
    assert d1.action == "wait" and d1.reason == "incomplete" and det_once.calls == 1
    for q, t_now in ((0.60, 10.15), (1.50, 11.05), (3.50, 13.05)):
        d_hold = dec_once.step(q, 1.0, t_now, fake_audio)
        assert d_hold.action == "wait" and d_hold.reason == "decided" and abs((d_hold.probability or 0.0) - 0.12) < 1e-6
    assert det_once.calls == 1
    # Decreasing quiet_seconds without explicit reset() auto-resets for the new pause!
    d_auto = dec_once.step(0.45, 2.0, 14.00, fake_audio)
    assert d_auto.action == "complete" and det_once.calls == 2 and abs((d_auto.probability or 0.0) - 0.89) < 1e-6
    dec_once.reset()
    assert dec_once._last_probability is None and dec_once._checked_pause is False

    # 7c. Explicit recheck_interval_s preserves rate-limited rechecks for untrimmed audio callers.
    det_hold = FakeDetector([0.12, 0.22, 0.87])
    dec2 = TurnDecider(det_hold, threshold=0.5, initial_pause_s=0.45, recheck_interval_s=0.5, max_wait_s=4.5, min_speech_s=0.25)
    assert dec2.step(0.45, 1.0, 10.00, fake_audio).action == "wait"  # call 1 (0.12)
    assert det_hold.calls == 1
    for dt in (0.05, 0.15, 0.30, 0.45):
        d = dec2.step(0.45 + dt, 1.0, 10.00 + dt, fake_audio)
        assert d.action == "wait" and d.reason == "rate_limited"
    assert det_hold.calls == 1
    assert dec2.step(0.95, 1.0, 10.50, fake_audio).action == "wait"
    assert det_hold.calls == 2
    dec2.reset()
    assert dec2._last_probability is None
    d_after_reset = dec2.step(0.45, 2.0, 10.60, fake_audio)
    assert d_after_reset.action == "complete" and det_hold.calls == 3

    # 7d. max_wait_s cap returns fallback without calling detector.
    det_cap = FakeDetector([0.1])
    dec3 = TurnDecider(det_cap, max_wait_s=4.5)
    d_cap = dec3.step(4.5, 1.0, 20.0, fake_audio)
    assert d_cap.action == "fallback" and d_cap.reason == "max_wait" and det_cap.calls == 0

    # 7e. Missing/unavailable, empty_audio, audio_error, and errored detector fall back cleanly.
    det_unavail = FakeDetector([0.9], avail=False)
    dec4 = TurnDecider(det_unavail)
    prev_audio = audio_calls[0]
    d_unavail = dec4.step(0.5, 1.0, 30.0, fake_audio)
    assert d_unavail.action == "fallback" and d_unavail.reason == "detector_unavailable"
    assert audio_calls[0] == prev_audio

    det_empty = FakeDetector([0.9])
    dec_empty = TurnDecider(det_empty)
    d_empty = dec_empty.step(0.5, 1.0, 35.0, lambda: np.empty(0, dtype=np.float32))
    assert d_empty.action == "wait" and d_empty.reason == "empty_audio" and det_empty.calls == 0

    det_aerr = FakeDetector([0.9])
    dec_aerr = TurnDecider(det_aerr)
    d_aerr = dec_aerr.step(0.5, 1.0, 36.0, lambda: (_ for _ in ()).throw(RuntimeError("mic gone")))
    assert d_aerr.action == "fallback" and d_aerr.reason == "audio_error:RuntimeError" and det_aerr.calls == 0

    det_err = FakeDetector(["boom"])
    dec5 = TurnDecider(det_err)
    d_err = dec5.step(0.5, 1.0, 40.0, fake_audio)
    assert d_err.action == "fallback" and d_err.reason.startswith("detector_error:")

    # 8. SmartTurnDetector fail-open on missing file and _load_failed stopping retries on corrupt model.
    missing_path = desk.data_dir() / "rook" / "models" / "does-not-exist.onnx"
    real_det = SmartTurnDetector(model_path=missing_path)
    assert not real_det.available()
    assert not real_det.load()
    res_missing = real_det.predict(tone_1s)
    assert not res_missing.complete and res_missing.error is not None

    corrupt_path = desk.data_dir() / "rook" / "models" / "corrupt.onnx"
    corrupt_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_path.write_bytes(b"not a valid onnx protobuf")
    corrupt_det = SmartTurnDetector(model_path=corrupt_path)
    if corrupt_det._get_ort() is not None:
        assert corrupt_det.available()
        assert not corrupt_det.load()
        assert corrupt_det._load_failed is True
        assert not corrupt_det.available(), "_load_failed must make available() return False"
        assert not corrupt_det.load(), "load() must short-circuit once _load_failed is True"
        corrupt_det.unload()
        assert corrupt_det._load_failed is False and corrupt_det.available()

    # 9. ensure_model offline via file:// URL: good hash, bad hash cleans temp, oversized file rejected.
    src_dir = desk.data_dir() / "rook" / "ensure-src"
    dst_dir = desk.data_dir() / "rook" / "ensure-dst"
    src_dir.mkdir(parents=True, exist_ok=True)
    payload = b"smart-turn-test-weights-1234567890"
    payload_sha = hashlib.sha256(payload).hexdigest()
    src_file = src_dir / "model.onnx"
    src_file.write_bytes(payload)

    good_dst = dst_dir / "good.onnx"
    out_path = ensure_model(good_dst, expected_sha256=payload_sha, url=src_file.as_uri(), max_bytes=len(payload))
    assert out_path == good_dst and good_dst.read_bytes() == payload
    # Re-calling on existing good file succeeds immediately.
    assert ensure_model(good_dst, expected_sha256=payload_sha, url="file:///nonexistent", max_bytes=len(payload)) == good_dst

    bad_dst = dst_dir / "bad.onnx"
    try:
        ensure_model(bad_dst, expected_sha256="0" * 64, url=src_file.as_uri(), max_bytes=len(payload))
        raise AssertionError("Expected ValueError for mismatched SHA-256")
    except ValueError:
        pass
    assert not bad_dst.exists() and not list(dst_dir.glob("*.tmp")), list(dst_dir.iterdir())

    big_src = src_dir / "big.onnx"
    big_src.write_bytes(b"x" * 2048)
    big_dst = dst_dir / "big.onnx"
    try:
        ensure_model(big_dst, expected_sha256=None, url=big_src.as_uri(), max_bytes=1024)
        raise AssertionError("Expected ValueError for oversized download")
    except ValueError:
        pass
    assert not big_dst.exists() and not list(dst_dir.glob("*.tmp")), list(dst_dir.iterdir())

    print("Turn end: all checks passed.")


# ---------------------------------------------------------------------------
# Real ONNX CPU/RAM/latency + qualitative benchmark (--benchmark)
# ---------------------------------------------------------------------------


def _vm_rss_mb() -> float:
    """Read current process VmRSS in MiB from /proc/self/status (Linux)."""
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return kb / 1024.0
    except OSError:
        pass
    return float("nan")


def _find_phonon_python() -> Path | None:
    for candidate in (
        Path.home() / ".local/share/rook/voice-phonon/bin/python",
        Path.home() / ".local/share/wowfriend/voice-phonon/bin/python",
    ):
        if candidate.is_file():
            return candidate
    return None


def _synthesize_phonon_wavs(utterances: list[tuple[str, str]], out_dir: Path) -> list[tuple[str, str, Path]] | None:
    """Silently render WAVs via Phonon TTS into out_dir (no audio playback, no mic)."""
    py = _find_phonon_python()
    if py is None:
        return None
    script = r"""
import json, os, sys, wave
import numpy as np
import ptts

out_dir = sys.argv[1]
items = json.loads(sys.argv[2])
ptts.set_num_threads(2)
model = ptts.TTS(None, quant="q8", lang="en", temperature=0.3)
sr = int(model.sample_rate)
results = []
for idx, (label, text) in enumerate(items):
    chunks = []
    with model.stream(text, voice="Miles") as audio:
        for chunk in audio:
            chunks.append(np.asarray(chunk, dtype=np.float32))
    wav_arr = np.concatenate(chunks) if chunks else np.zeros(sr // 2, dtype=np.float32)
    pcm = (np.clip(wav_arr, -1.0, 1.0) * 32767.0).astype(np.int16)
    path = os.path.join(out_dir, f"utt_{idx:02d}_{label}.wav")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    results.append([label, text, path, sr, int(pcm.size)])
print(json.dumps(results))
"""
    env = os.environ.copy()
    env.setdefault("HF_HOME", str(Path.home() / ".cache/huggingface"))
    env["HF_HUB_OFFLINE"] = "1"
    done = subprocess.run(
        [str(py), "-c", script, str(out_dir), json.dumps(utterances)],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if done.returncode != 0:
        print(f"Phonon TTS synthesis failed (exit {done.returncode}): {done.stderr.strip()}", file=sys.stderr)
        return None
    last_line = done.stdout.strip().splitlines()[-1]
    rows = json.loads(last_line)
    return [(label, text, Path(path)) for label, text, path, _sr, _n in rows]


def _read_wav_float32(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    if sw != 2:
        raise ValueError(f"Unsupported sample width {sw} in {path}")
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    return arr, sr


def run_benchmark(model_path: Path, runs: int = 20, skip_qualitative: bool = False) -> None:
    """Measure model metadata, cold load, RAM delta, 1 vs 2 thread latency/CPU, and qualitative scores."""
    expected_sha256 = MODEL_SHA256 if model_path.name == MODEL_FILENAME else None
    path = ensure_model(model_path, expected_sha256=expected_sha256)
    size_bytes = path.stat().st_size
    sha256 = _sha256_file(path)
    print(f"Model path: {path}")
    print(f"Model size: {size_bytes} bytes ({size_bytes / (1024 * 1024):.2f} MiB)")
    print(f"Model SHA-256: {sha256} (matches constant: {sha256 == MODEL_SHA256})")

    # Synthetic 3s speech-like waveform for deterministic timing benchmarks.
    rng = np.random.default_rng(42)
    t = np.arange(3 * SAMPLE_RATE, dtype=np.float32) / SAMPLE_RATE
    bench_audio = (0.15 * np.sin(2.0 * np.pi * 180.0 * t) + 0.05 * rng.standard_normal(t.size)).astype(np.float32)

    # Cold load + RAM delta (using 1 thread first).
    rss_before = _vm_rss_mb()
    det1 = SmartTurnDetector(path, intra_op_num_threads=1)
    t_load0 = time.perf_counter()
    ok = det1.load()
    cold_load_ms = (time.perf_counter() - t_load0) * 1000.0
    assert ok, f"Failed to load ONNX model: {det1._last_error}"
    rss_after_load = _vm_rss_mb()

    # Print verified ONNX tensor contract.
    sess = det1._session
    inputs_info = [(i.name, i.shape, i.type) for i in sess.get_inputs()]
    outputs_info = [(o.name, o.shape, o.type) for o in sess.get_outputs()]
    print(f"ONNX inputs: {inputs_info}")
    print(f"ONNX outputs: {outputs_info}")
    print(f"ONNX providers: {sess.get_providers()}")

    first_res = det1.predict(bench_audio)
    assert first_res.error is None, first_res.error
    rss_after_first = _vm_rss_mb()
    print(
        f"Cold load: {cold_load_ms:.1f} ms | first predict: {first_res.elapsed_ms:.1f} ms | "
        f"VmRSS before={rss_before:.1f} MiB, after_load={rss_after_load:.1f} MiB (+{rss_after_load - rss_before:.1f} MiB), "
        f"after_first={rss_after_first:.1f} MiB (+{rss_after_first - rss_before:.1f} MiB)"
    )

    # Measure pure-NumPy mel preprocessing alone.
    mel_times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        extract_whisper_mel(bench_audio)
        mel_times.append((time.perf_counter() - t0) * 1000.0)
    print(
        f"Mel preprocess ({runs} runs): p50={np.percentile(mel_times, 50):.2f} ms, "
        f"p95={np.percentile(mel_times, 95):.2f} ms, max={max(mel_times):.2f} ms"
    )

    # Warm latency & CPU cost for intra_op_num_threads=1 and 2.
    ncores = os.cpu_count() or 1
    det1.unload()
    for threads in (1, 2):
        det = SmartTurnDetector(path, intra_op_num_threads=threads)
        assert det.load()
        # 2 warmup runs
        for _ in range(2):
            assert det.predict(bench_audio).error is None
        wall_ms = []
        cpu_ms = []
        for _ in range(runs):
            c0 = time.process_time()
            w0 = time.perf_counter()
            res = det.predict(bench_audio)
            w1 = time.perf_counter()
            c1 = time.process_time()
            assert res.error is None, res.error
            wall_ms.append((w1 - w0) * 1000.0)
            cpu_ms.append((c1 - c0) * 1000.0)
        p50 = float(np.percentile(wall_ms, 50))
        p95 = float(np.percentile(wall_ms, 95))
        wmax = float(max(wall_ms))
        mean_cpu = float(np.mean(cpu_ms))
        # CPU share during the pause check itself, and amortized at 1 check per 0.5s recheck interval.
        check_cpu_of_1core = 100.0 * (mean_cpu / max(1e-6, float(np.mean(wall_ms))))
        amort_1core = 100.0 * (mean_cpu / 500.0)
        amort_all = amort_1core / ncores
        print(
            f"Warm inference (intra_op_num_threads={threads}, {runs} runs): "
            f"p50={p50:.2f} ms, p95={p95:.2f} ms, max={wmax:.2f} ms, "
            f"mean_cpu={mean_cpu:.2f} ms ({check_cpu_of_1core:.0f}% of 1 core during call; "
            f"at 0.5s recheck: {amort_1core:.1f}% of 1 core / {amort_all:.2f}% of {ncores} cores)"
        )
        det.unload()

    if skip_qualitative:
        return

    utterances = [
        ("complete", "What time is it right now?", None),
        ("complete", "Check my inbox for new messages.", None),
        ("complete", "Yeah, go ahead and deploy that.", None),
        # Synthesize full natural sentences and slice mid-clause to preserve genuine
        # continuation prosody (standalone fragments receive TTS <EOS> falling intonation).
        (
            "incomplete",
            "Um, I was thinking we should maybe look at the server logs before we decide anything.",
            0.45,
        ),
        (
            "incomplete",
            "Hold on, let me check if the build finished running on the other machine first.",
            0.45,
        ),
        (
            "incomplete",
            "So the thing about that bug is that it only happens when the cache expires overnight.",
            0.45,
        ),
    ]
    with tempfile.TemporaryDirectory(prefix="rook-smart-turn-tts-") as tmp_dir:
        rendered = _synthesize_phonon_wavs([(lbl, txt) for lbl, txt, _ in utterances], Path(tmp_dir))
        if rendered is None:
            print("Qualitative check: skipped (Phonon TTS environment not found).")
            return
        det = SmartTurnDetector(path, intra_op_num_threads=DEFAULT_INTRA_OP_THREADS)
        assert det.load()
        print("Qualitative check (offline Phonon TTS; incomplete clips sliced mid-clause for continuation prosody):")
        for (expected, text, wav_path), (_, _, cut_frac) in zip(rendered, utterances):
            audio, sr = _read_wav_float32(wav_path)
            voiced = trim_trailing_silence(audio, sample_rate=sr, max_tail_s=0.0, rms_threshold=0.01)
            if cut_frac is not None:
                voiced = voiced[: int(len(voiced) * cut_frac)]
            clip_020 = np.concatenate([voiced, np.zeros(int(round(0.20 * sr)), dtype=np.float32)])
            clip_045 = np.concatenate([voiced, np.zeros(int(round(0.45 * sr)), dtype=np.float32)])
            res_020 = det.predict(clip_020, sample_rate=sr)
            res_045 = det.predict(clip_045, sample_rate=sr)
            label_text = text if cut_frac is None else f"{text[:42]}... [cut@{int(cut_frac * 100)}%]"
            print(
                f"  [{expected:10s}] tail=0.20s: p={res_020.probability:.4f} complete={str(res_020.complete):5s} | "
                f"tail=0.45s: p={res_045.probability:.4f} complete={str(res_045.complete):5s} | {label_text!r}"
            )
        det.unload()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipecat Smart Turn v3.2 CPU/ONNX end-of-turn detector.")
    parser.add_argument("--check", action="store_true", help="Run offline self-checks in scratch XDG folders.")
    parser.add_argument("--download", action="store_true", help="Download and verify the Smart Turn v3.2 ONNX model.")
    parser.add_argument("--benchmark", action="store_true", help="Run ONNX CPU/RAM/latency + qualitative benchmark.")
    parser.add_argument("--model", help="Path to smart-turn-v3.2-cpu.onnx (overrides env/default).")
    parser.add_argument("--runs", type=int, default=20, help="Number of warm inference iterations for --benchmark.")
    parser.add_argument("--skip-qualitative", action="store_true", help="Skip Phonon TTS qualitative check.")
    args = parser.parse_args(argv)

    if args.check:
        with tempfile.TemporaryDirectory(prefix="rook-turn-check-") as scratch:
            prev_env = {k: os.environ.get(k) for k in (
                "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
                "XDG_RUNTIME_DIR", MODEL_ENV_VAR,
            )}
            try:
                os.environ.update({
                    "XDG_DATA_HOME": f"{scratch}/data",
                    "XDG_STATE_HOME": f"{scratch}/state",
                    "XDG_CONFIG_HOME": f"{scratch}/config",
                    "XDG_CACHE_HOME": f"{scratch}/cache",
                    "XDG_RUNTIME_DIR": scratch,
                })
                os.environ.pop(MODEL_ENV_VAR, None)
                run_check()
            finally:
                for key, val in prev_env.items():
                    if val is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = val
        return 0

    if args.download:
        model_path = default_model_path(args.model)
        expected_sha256 = MODEL_SHA256 if model_path.name == MODEL_FILENAME else None
        path = ensure_model(model_path, expected_sha256=expected_sha256)
        print(f"Model ready: {path} ({path.stat().st_size} bytes)")
        return 0

    if args.benchmark:
        model_path = default_model_path(args.model)
        run_benchmark(model_path, runs=args.runs, skip_qualitative=args.skip_qualitative)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
