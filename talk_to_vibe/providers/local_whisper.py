import ctypes
import glob
import os
import threading

import numpy as np

from talk_to_vibe.providers.base import BaseSTTProvider

_CUDA_PRELOADED = False
_CUDA_PRELOAD_LOCK = threading.Lock()


def _preload_bundled_cuda_libs() -> tuple[bool, str]:
    """Load CUDA libs from the nvidia-* pip wheels into the process.

    CTranslate2 dlopen()s libcublas / libcudnn by short name. Without this,
    those calls only succeed if the system has matching libs in the linker
    path. By preloading the wheel-provided .so files with RTLD_GLOBAL, later
    short-name lookups resolve to them in-memory.

    Returns (preloaded, message). preloaded=False simply means the wheels
    aren't installed — not an error; CPU mode still works.
    """
    global _CUDA_PRELOADED
    with _CUDA_PRELOAD_LOCK:
        if _CUDA_PRELOADED:
            return True, "already preloaded"
        try:
            import nvidia.cublas.lib as cublas_pkg
            import nvidia.cudnn.lib as cudnn_pkg
        except ImportError:
            return False, "nvidia cublas/cudnn wheels not installed"

        candidates: list[str] = []
        for pkg in (cublas_pkg, cudnn_pkg):
            pkg_dirs: list[str] = []
            pkg_file = getattr(pkg, "__file__", None)
            if pkg_file:
                pkg_dirs.append(os.path.dirname(pkg_file))
            else:
                pkg_dirs.extend(list(getattr(pkg, "__path__", []) or []))
            for pkg_dir in pkg_dirs:
                candidates.extend(sorted(glob.glob(os.path.join(pkg_dir, "*.so*"))))

        loaded: list[str] = []
        pending = list(candidates)
        last_errors: dict[str, str] = {}
        # Inter-library dependencies (e.g. libcublas needs libcublasLt) mean
        # alphabetical load order can fail on the first pass. Retry until no
        # additional libs load successfully.
        while pending:
            progressed = False
            still_pending: list[str] = []
            for so in pending:
                try:
                    ctypes.CDLL(so, mode=ctypes.RTLD_GLOBAL)
                    loaded.append(os.path.basename(so))
                    last_errors.pop(so, None)
                    progressed = True
                except OSError as exc:
                    last_errors[so] = str(exc)
                    still_pending.append(so)
            pending = still_pending
            if not progressed:
                break
        errors = [f"{os.path.basename(so)}: {msg}" for so, msg in last_errors.items()]
        _CUDA_PRELOADED = bool(loaded)
        if errors:
            return _CUDA_PRELOADED, f"loaded {len(loaded)} libs; errors: {errors[:2]}"
        return _CUDA_PRELOADED, f"loaded {len(loaded)} libs"


def _resolve_device_and_compute(device: str, compute_type: str) -> tuple[str, str]:
    """Translate 'auto' into concrete values based on what's available."""
    chosen_device = device
    if chosen_device == "auto":
        preloaded, _ = _preload_bundled_cuda_libs()
        chosen_device = "cuda" if preloaded else "cpu"
    elif chosen_device == "cuda":
        _preload_bundled_cuda_libs()

    chosen_compute = compute_type
    if chosen_compute == "auto":
        chosen_compute = "float16" if chosen_device == "cuda" else "int8"
    return chosen_device, chosen_compute


class LocalWhisperProvider(BaseSTTProvider):
    provider_name = "Local Whisper (faster-whisper)"

    def __init__(
        self,
        model_size: str,
        device: str = "auto",
        compute_type: str = "auto",
        language: str = "en",
        model_dir: str = "",
        cpu_threads: int = 0,
        beam_size: int = 5,
        vad_filter: bool = True,
    ):
        from faster_whisper import WhisperModel

        self.model_name = model_size
        self.model = model_size
        self.language = language or None
        self.beam_size = beam_size
        self.vad_filter = vad_filter

        resolved_device, resolved_compute = _resolve_device_and_compute(device, compute_type)
        self.device = resolved_device
        self.compute_type = resolved_compute

        kwargs = {
            "device": resolved_device,
            "compute_type": resolved_compute,
        }
        if model_dir:
            kwargs["download_root"] = os.path.expanduser(model_dir)
        if cpu_threads and resolved_device == "cpu":
            kwargs["cpu_threads"] = cpu_threads

        self._whisper = WhisperModel(model_size, **kwargs)

    def transcribe(self, audio_data: np.ndarray) -> str:
        if audio_data is None or len(audio_data) == 0:
            return ""

        if audio_data.dtype == np.int16:
            samples = audio_data.astype(np.float32) / 32768.0
        elif audio_data.dtype == np.float32:
            samples = audio_data
        else:
            samples = audio_data.astype(np.float32)

        if samples.ndim > 1:
            samples = samples.mean(axis=1).astype(np.float32)

        segments, _info = self._whisper.transcribe(
            samples,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
        )
        parts = []
        for seg in segments:
            text = (seg.text or "").strip()
            if text:
                parts.append(text)
        return " ".join(parts)


__all__ = [
    "LocalWhisperProvider",
    "_preload_bundled_cuda_libs",
    "_resolve_device_and_compute",
]
