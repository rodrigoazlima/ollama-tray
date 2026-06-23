import json
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import psutil


class OllamaStats:
    cpu_pct:   float       = 0.0
    mem_rss:   int         = 0
    mem_vms:   int         = 0
    threads:   int         = 0
    handles:   int         = 0
    num_procs: int         = 0
    uptime:    str         = "—"
    procs:     list        = []
    models:    list        = []   # from /api/ps
    vram_nvml: tuple | None = None  # (used_bytes, total_bytes) or None

    def is_empty(self) -> bool:
        return self.num_procs == 0


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_uptime(create_time: float) -> str:
    delta = timedelta(seconds=int(time.time() - create_time))
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s   = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


def fmt_expires(ts: str) -> str:
    """Convert RFC3339 expiry timestamp to human-readable remaining time."""
    if not ts:
        return ""
    try:
        exp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        delta = exp - datetime.now(timezone.utc)
        secs = int(delta.total_seconds())
        if secs < 0:
            return "expired"
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}h {m:02d}m"
        if m:
            return f"{m}m {s:02d}s"
        return f"{s}s"
    except Exception:
        return ""


# ── /api/ps poller ────────────────────────────────────────────────────────────

_ps_models:  list           = []
_ps_lock:    threading.Lock = threading.Lock()
_ps_url:     str            = ""
_ps_started: bool           = False


def _fetch_ps() -> list:
    if not _ps_url:
        return []
    try:
        req = urllib.request.Request(
            _ps_url.rstrip("/") + "/api/ps",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return json.loads(resp.read()).get("models") or []
    except Exception:
        return []


def _ps_poller() -> None:
    global _ps_models
    while True:
        models = _fetch_ps()
        with _ps_lock:
            _ps_models = models
        time.sleep(2)


def start_ps_poller(base_url: str) -> None:
    global _ps_started, _ps_url
    _ps_url = base_url
    if _ps_started:
        return
    _ps_started = True
    threading.Thread(target=_ps_poller, daemon=True).start()


# ── NVML VRAM (NVIDIA, optional) ─────────────────────────────────────────────

_pynvml_missing: bool = False


def _try_vram_nvml() -> tuple[int, int] | None:
    """Returns (used_bytes, total_bytes) across all NVIDIA GPUs, or None."""
    global _pynvml_missing
    if _pynvml_missing:
        return None
    try:
        import pynvml  # type: ignore
    except ImportError:
        _pynvml_missing = True
        return None
    try:
        pynvml.nvmlInit()
        n = pynvml.nvmlDeviceGetCount()
        used = total = 0
        for i in range(n):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            m = pynvml.nvmlDeviceGetMemoryInfo(h)
            used  += m.used
            total += m.total
        return (used, total)
    except Exception:
        return None


# ── process stats ─────────────────────────────────────────────────────────────

_stats_lock    = threading.Lock()
_current_stats = OllamaStats()
_proc_handles: dict[int, psutil.Process] = {}


def refresh_stats() -> OllamaStats:
    global _proc_handles, _current_stats

    live = [
        p for p in psutil.process_iter(["name", "pid"])
        if "ollama" in (p.info.get("name") or "").lower()
    ]
    live_pids = {p.pid for p in live}
    _proc_handles = {pid: h for pid, h in _proc_handles.items() if pid in live_pids}

    for p in live:
        if p.pid not in _proc_handles:
            try:
                p.cpu_percent(interval=None)
                _proc_handles[p.pid] = p
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    s = OllamaStats()
    s.procs = []
    earliest = None

    for pid, p in list(_proc_handles.items()):
        try:
            with p.oneshot():
                cpu  = p.cpu_percent(interval=None)
                mi   = p.memory_info()
                thr  = p.num_threads()
                hdl  = p.num_handles() if hasattr(p, "num_handles") else 0
                ct   = p.create_time()
                name = p.name()
            s.cpu_pct  += cpu
            s.mem_rss  += mi.rss
            s.mem_vms  += mi.vms
            s.threads  += thr
            s.handles  += hdl
            s.num_procs += 1
            if earliest is None or ct < earliest:
                earliest = ct
            s.procs.append({"name": name, "pid": pid, "cpu": cpu,
                             "rss": mi.rss, "vms": mi.vms, "thr": thr})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            _proc_handles.pop(pid, None)

    if earliest:
        s.uptime = _fmt_uptime(earliest)

    with _ps_lock:
        s.models = list(_ps_models)

    s.vram_nvml = _try_vram_nvml()

    with _stats_lock:
        _current_stats = s
    return s


def current_stats() -> OllamaStats:
    with _stats_lock:
        return _current_stats
