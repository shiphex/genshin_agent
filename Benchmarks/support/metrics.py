"""Sample worker trees separately from timing; RSS is a sampled lower bound."""
import threading

import psutil


def paired_order(items, round_index):
    """Alternate order, rotating pairs when more than two candidates are supplied."""
    shifted = list(items[round_index // 2 % len(items):]) + list(items[:round_index // 2 % len(items)])
    return shifted if round_index % 2 == 0 else list(reversed(shifted))


class MemorySeries:
    def __init__(self):
        self.baseline, self.last = {}, {}
        self.idle = None
        self.peak, self.samples = 0, 0

    def add(self, processes):
        if not processes:
            return
        total = sum(p["rss"] for p in processes.values())
        if self.idle is None:
            self.idle = total
            self.baseline = {key: p["cpu"] for key, p in processes.items()}
        self.peak = max(self.peak, total)
        self.samples += 1
        for key, item in processes.items():
            self.last[key] = max(self.last.get(key, 0), item["cpu"])

    def result(self):
        return {"samples": self.samples, "idle_rss_bytes": self.idle,
                "sampled_peak_rss_bytes": self.peak if self.samples else None,
                "rss_increase_bytes": max(0, self.peak - self.idle) if self.idle is not None else None,
                "cpu_seconds": sum(max(0, value - self.baseline.get(key, 0)) for key, value in self.last.items())
                if self.samples else None}


class ProcessMeter:
    def __init__(self, pid, interval=0.01, memory=False, tree=True):
        self.pid, self.interval, self.memory = pid, interval, memory
        self.tree = tree
        self.series, self.errors = MemorySeries(), 0
        self.stopped = threading.Event()
        self.thread = None
        self.sample()
        if memory:
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def sample(self):
        try:
            parent = psutil.Process(self.pid)
            processes = [parent] + (parent.children(recursive=True) if self.tree else [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.errors += 1
            return
        snapshot = {}
        for process in processes:
            try:
                cpu = process.cpu_times()
                snapshot[(process.pid, process.create_time())] = {
                    "rss": process.memory_info().rss, "cpu": cpu.user + cpu.system}
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.errors += 1
        self.series.add(snapshot)

    def _run(self):
        while not self.stopped.wait(self.interval):
            self.sample()

    def finish(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=2)
        self.sample()
        return {**self.series.result(), "scope": "process_and_observed_descendants" if self.tree else "process_only",
                "mode": "periodic_memory" if self.memory else "endpoints_only",
                "interval_ms": self.interval * 1000 if self.memory else None,
                "sampling_errors": self.errors,
                "limitations": "short-lived children and between-sample peaks may be missed"}
