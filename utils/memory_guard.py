import os
import sys
import time
import subprocess
import gc
import threading
import datetime
from typing import Dict, List, Optional, Union
from utils.config import (
    MEMORY_GUARD_ENABLED,
    MEMORY_WARNING_PERCENT,
    MEMORY_CRITICAL_PERCENT,
    MEMORY_RECOVERY_PERCENT,
    MEMORY_RECOVERY_CYCLES,
    MEMORY_WARNING_RSS_MB,
    MEMORY_CRITICAL_RSS_MB,
    MEMORY_RECOVERY_RSS_MB,
    MEMORY_SAMPLE_INTERVAL
)
from utils.logger import setup_logger

logger = setup_logger("MemoryGuard")

# Diagnostic tracing flag
_tracemalloc_enabled = False

class MemoryProvider:
    def get_process_rss(self) -> float:
        """Returns resident memory of the current process in MB."""
        raise NotImplementedError()
        
    def get_system_available(self) -> float:
        """Returns system available memory in MB."""
        raise NotImplementedError()

class MacOSProvider(MemoryProvider):
    def get_process_rss(self) -> float:
        try:
            pid = os.getpid()
            out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)])
            kb = float(out.strip())
            return kb / 1024.0
        except Exception:
            import resource
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0 / 1024.0

    def get_system_available(self) -> float:
        try:
            out = subprocess.check_output(["vm_stat"])
            lines = out.decode("utf-8").split("\n")
            page_size = 4096
            pages_free = 0
            pages_inactive = 0
            for line in lines:
                if "page size of" in line:
                    parts = line.split()
                    page_size = int(parts[2])
                elif "Pages free:" in line:
                    pages_free = int(line.split()[2].replace(".", ""))
                elif "Pages inactive:" in line:
                    pages_inactive = int(line.split()[2].replace(".", ""))
            available_bytes = (pages_free + pages_inactive) * page_size
            return available_bytes / 1024.0 / 1024.0
        except Exception:
            return 1024.0

class LinuxProvider(MemoryProvider):
    def get_process_rss(self) -> float:
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        kb = float(parts[1])
                        return kb / 1024.0
        except Exception:
            pass
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

    def get_system_available(self) -> float:
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        parts = line.split()
                        kb = float(parts[1])
                        return kb / 1024.0
        except Exception:
            return 1024.0

class FallbackProvider(MemoryProvider):
    def get_process_rss(self) -> float:
        import resource
        maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return maxrss / 1024.0 / 1024.0
        return maxrss / 1024.0
        
    def get_system_available(self) -> float:
        return 1024.0

def get_memory_provider() -> MemoryProvider:
    try:
        import psutil
        class PsutilProvider(MemoryProvider):
            def get_process_rss(self) -> float:
                return psutil.Process(os.getpid()).memory_info().rss / 1024.0 / 1024.0
            def get_system_available(self) -> float:
                return psutil.virtual_memory().available / 1024.0 / 1024.0
        return PsutilProvider()
    except ImportError:
        if sys.platform == "darwin":
            return MacOSProvider()
        elif sys.platform.startswith("linux"):
            return LinuxProvider()
        return FallbackProvider()

class MemoryGuard:
    _lock = threading.Lock()
    provider: MemoryProvider = get_memory_provider()
    current_state: str = "NORMAL"
    
    # State tracking
    _rss_history: List[float] = []
    _registered_caches: List[Union[dict, any]] = []
    _concurrency_reduction_factor: float = 1.0
    _recovery_cycle_counter: int = 0
    
    # Dynamic thresholds based on APP_MODE
    warning_rss_limit: float = MEMORY_WARNING_RSS_MB
    critical_rss_limit: float = MEMORY_CRITICAL_RSS_MB
    emergency_rss_limit: float = MEMORY_CRITICAL_RSS_MB * 1.2
    warning_sys_limit: float = MEMORY_WARNING_PERCENT
    critical_sys_limit: float = MEMORY_CRITICAL_PERCENT
    emergency_sys_limit: float = MEMORY_CRITICAL_PERCENT * 1.05
    recovery_rss_limit: float = MEMORY_RECOVERY_RSS_MB
    recovery_sys_limit: float = MEMORY_RECOVERY_PERCENT

    # Peak stats
    peak_rss_mb: float = 0.0
    baseline_rss_mb: float = 0.0
    total_system_memory_mb: float = 0.0
    
    @classmethod
    def initialize(cls):
        with cls._lock:
            cls.baseline_rss_mb = cls.provider.get_process_rss()
            cls.peak_rss_mb = cls.baseline_rss_mb
            cls.current_state = "NORMAL"
            cls._rss_history.clear()
            cls._recovery_cycle_counter = 0
            cls._concurrency_reduction_factor = 1.0
            
            # Apply Profile Separation (Local vs Production)
            import utils.config
            if utils.config.APP_MODE == "production":
                cls.warning_rss_limit = 4000.0
                cls.critical_rss_limit = 8000.0
                cls.emergency_rss_limit = 12000.0
                cls.warning_sys_limit = 85.0
                cls.critical_sys_limit = 93.0
                cls.emergency_sys_limit = 97.0
                cls.recovery_rss_limit = 3500.0
                cls.recovery_sys_limit = 80.0
            else:
                cls.warning_rss_limit = MEMORY_WARNING_RSS_MB
                cls.critical_rss_limit = MEMORY_CRITICAL_RSS_MB
                cls.emergency_rss_limit = MEMORY_CRITICAL_RSS_MB * 1.2
                cls.warning_sys_limit = MEMORY_WARNING_PERCENT
                cls.critical_sys_limit = MEMORY_CRITICAL_PERCENT
                cls.emergency_sys_limit = MEMORY_CRITICAL_PERCENT * 1.05
                cls.recovery_rss_limit = MEMORY_RECOVERY_RSS_MB
                cls.recovery_sys_limit = MEMORY_RECOVERY_PERCENT

            # Estimate total system memory in MB
            if sys.platform == "darwin":
                try:
                    # Sandboxed/managed macOS sessions may deny sysctl.  This
                    # is an expected optional probe, not a runtime error.
                    out = subprocess.check_output(
                        ["sysctl", "-n", "hw.memsize"], stderr=subprocess.DEVNULL
                    )
                    cls.total_system_memory_mb = float(out.strip()) / 1024.0 / 1024.0
                except Exception:
                    cls.total_system_memory_mb = 8192.0 # 8GB default fallback
            elif sys.platform.startswith("linux"):
                try:
                    with open("/proc/meminfo", "r") as f:
                        for line in f:
                            if line.startswith("MemTotal:"):
                                parts = line.split()
                                cls.total_system_memory_mb = float(parts[1]) / 1024.0
                                break
                except Exception:
                    cls.total_system_memory_mb = 8192.0
            else:
                cls.total_system_memory_mb = 8192.0
                
            logger.info(f"MemoryGuard initialized. Baseline RSS: {cls.baseline_rss_mb:.2f}MB | System Total: {cls.total_system_memory_mb:.2f}MB")

    @classmethod
    def register_cache(cls, cache_obj):
        with cls._lock:
            if cache_obj not in cls._registered_caches:
                cls._registered_caches.append(cache_obj)

    @classmethod
    def get_concurrency_reduction_factor(cls) -> float:
        with cls._lock:
            return cls._concurrency_reduction_factor

    @classmethod
    def check_and_cleanup(cls) -> Dict:
        """
        Samples memory metrics, updates state machine, and triggers cleanup if pressured.
        """
        if not MEMORY_GUARD_ENABLED:
            return {"status": "DISABLED"}
            
        with cls._lock:
            try:
                rss = cls.provider.get_process_rss()
                sys_avail = cls.provider.get_system_available()
            except Exception as e:
                logger.error(f"Memory sensing failed: {e}. Reverting toFallback.")
                cls.current_state = "MEMORY_STATUS_UNKNOWN"
                return {"status": "MEMORY_STATUS_UNKNOWN", "error": str(e)}

            if rss > cls.peak_rss_mb:
                cls.peak_rss_mb = rss
                
            sys_used_pct = 0.0
            if cls.total_system_memory_mb > 0:
                sys_used_pct = (cls.total_system_memory_mb - sys_avail) / cls.total_system_memory_mb * 100.0

            # State transition logic with hysteresis
            old_state = cls.current_state
            cls._update_state_machine(rss, sys_used_pct)
            
            # Telemetry dict
            import utils.config
            telemetry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "mode": utils.config.APP_MODE.upper(),
                "process_rss_mb": round(rss, 2),
                "peak_rss_mb": round(cls.peak_rss_mb, 2),
                "system_available_mb": round(sys_avail, 2),
                "memory_state": cls.current_state,
                "active_tasks": 1 if cls.current_state == "NORMAL" else 0,
                "blocked_tasks": cls._get_blocked_tasks_list(),
                "recovery_cycles": cls._recovery_cycle_counter
            }
            
            if _tracemalloc_enabled:
                import tracemalloc
                curr_traced, peak_traced = tracemalloc.get_traced_memory()
                telemetry["traced_current_mb"] = round(curr_traced / 1024.0 / 1024.0, 2)
                telemetry["traced_peak_mb"] = round(peak_traced / 1024.0 / 1024.0, 2)

            # Log transition events
            if cls.current_state != old_state:
                logger.warning(
                    f"[MEMORY_EVENT] state={cls.current_state} old_state={old_state} "
                    f"rss={rss:.2f}MB sys_used={sys_used_pct:.1f}%"
                )

            # Leak detection
            cls._rss_history.append(rss)
            if len(cls._rss_history) > 10:
                cls._rss_history.pop(0)
            if len(cls._rss_history) >= 5:
                is_increasing = all(cls._rss_history[i] < cls._rss_history[i+1] for i in range(len(cls._rss_history)-1))
                delta = cls._rss_history[-1] - cls._rss_history[0]
                if is_increasing and delta > 30.0:
                    logger.warning(f"[MEMORY_EVENT] state=MEMORY_GROWTH_SUSPECTED rss={rss:.2f}MB delta={delta:.2f}MB")
                    telemetry["leak_suspected"] = True

            # Cleanup triggered under warning/critical
            if cls.current_state in ["WARNING", "CRITICAL", "EMERGENCY"]:
                cls._run_cleanup_pipeline(rss)
                
            return telemetry

    @classmethod
    def _update_state_machine(cls, rss: float, sys_used_pct: float):
        # EMERGENCY check (highest severity)
        if rss > cls.emergency_rss_limit or sys_used_pct > cls.emergency_sys_limit:
            cls.current_state = "EMERGENCY"
            cls._concurrency_reduction_factor = 0.0
            cls._recovery_cycle_counter = 0
            return

        # CRITICAL check
        if rss > cls.critical_rss_limit or sys_used_pct > cls.critical_sys_limit:
            cls.current_state = "CRITICAL"
            cls._concurrency_reduction_factor = 0.2
            cls._recovery_cycle_counter = 0
            return
            
        # WARNING check
        if rss > cls.warning_rss_limit or sys_used_pct > cls.warning_sys_limit:
            cls.current_state = "WARNING"
            cls._concurrency_reduction_factor = 0.5
            cls._recovery_cycle_counter = 0
            return

        # Check recovery stability
        if rss < cls.recovery_rss_limit and sys_used_pct < cls.recovery_sys_limit:
            if cls.current_state in ["WARNING", "CRITICAL", "EMERGENCY"]:
                cls.current_state = "RECOVERY"
                cls._recovery_cycle_counter = 0
                
            if cls.current_state == "RECOVERY":
                cls._recovery_cycle_counter += 1
                if cls._recovery_cycle_counter >= MEMORY_RECOVERY_CYCLES:
                    cls.current_state = "NORMAL"
                    cls._concurrency_reduction_factor = 1.0
                    cls._recovery_cycle_counter = 0
        else:
            # Thrashing prevention: if memory stays warning-adjacent during recovery, cancel recovery cycle
            if cls.current_state == "RECOVERY":
                cls.current_state = "WARNING"
                cls._recovery_cycle_counter = 0

    @classmethod
    def _run_cleanup_pipeline(cls, before_rss: float):
        logger.info(f"[MEMORY_CLEANUP] Cleaning {len(cls._registered_caches)} registered caches...")
        for cache in cls._registered_caches:
            try:
                if isinstance(cache, dict):
                    cache.clear()
                elif hasattr(cache, "clear"):
                    cache.clear()
            except Exception as e:
                logger.error(f"Cache cleanup exception: {e}")
                
        # Invoke garbage collection
        gc.collect()
        after_rss = cls.provider.get_process_rss()
        logger.info(f"[MEMORY_CLEANUP] Cleanup complete. Process RSS: {before_rss:.2f}MB -> {after_rss:.2f}MB")

    @classmethod
    def _get_blocked_tasks_list(cls) -> List[str]:
        blocked = []
        if cls.current_state == "EMERGENCY":
            blocked = ["llm", "rag", "embedding", "pdf_ingestion", "large_batch", "new_ticker", "optional_provider"]
        elif cls.current_state == "CRITICAL":
            blocked = ["llm", "rag", "embedding", "pdf_ingestion", "large_batch"]
        return blocked

    @classmethod
    def allow(cls, task_name: str) -> bool:
        """
        Admissions Controller Gate.
        Gates heavy tasks based on memory pressure level.
        """
        if not MEMORY_GUARD_ENABLED:
            return True
            
        with cls._lock:
            state = cls.current_state
            
        if state == "EMERGENCY":
            # Block all new workloads, save core alpha process
            if task_name in ["llm", "rag", "embedding", "pdf_ingestion", "large_batch", "new_ticker", "optional_provider"]:
                logger.warning(f"[MEMORY_GUARD] Admission BLOCKED for heavy task '{task_name}' under EMERGENCY.")
                return False
                
        if state == "CRITICAL":
            # Gated admissions
            if task_name in ["llm", "rag", "embedding", "pdf_ingestion", "large_batch"]:
                logger.warning(f"[MEMORY_GUARD] Admission BLOCKED for heavy task '{task_name}' under CRITICAL pressure.")
                return False
                
        return True

def enable_diagnostics():
    global _tracemalloc_enabled
    import tracemalloc
    tracemalloc.start()
    _tracemalloc_enabled = True
    logger.info("Tracemalloc diagnostics enabled.")

def get_diagnostics() -> Dict:
    if not _tracemalloc_enabled:
        return {}
    import tracemalloc
    current, peak = tracemalloc.get_traced_memory()
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')
    top_allocations = [str(s) for s in top_stats[:5]]
    return {
        "current_traced_mb": current / 1024.0 / 1024.0,
        "peak_traced_mb": peak / 1024.0 / 1024.0,
        "top_allocations": top_allocations
    }
