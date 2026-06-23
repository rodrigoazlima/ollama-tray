import threading
import time
from datetime import timedelta

import psutil


class OllamaStats:
    cpu_pct:   float = 0.0
    mem_rss:   int   = 0
    mem_vms:   int   = 0
    threads:   int   = 0
    handles:   int   = 0
    num_procs: int   = 0
    uptime:    str   = "—"
    procs:     list  = []

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

    with _stats_lock:
        _current_stats = s
    return s


def current_stats() -> OllamaStats:
    with _stats_lock:
        return _current_stats
