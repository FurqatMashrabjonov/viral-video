"""Per-request cost logging: Scribe minutes + CPU seconds -> running $/UZS estimate."""
import json
import time
from pathlib import Path

CPU_COST_PER_HOUR_USD = 0.05  # ponytail: rough CPU cloud VM estimate, replace with real infra pricing
USD_TO_UZS = 12700  # ponytail: static placeholder FX rate, refresh if precision matters
LOG_PATH = Path("logs/cost_log.jsonl")


def log_cost(job_id: str, scribe_minutes: float, scribe_cost_usd: float, cpu_seconds: float) -> dict:
    cpu_cost_usd = cpu_seconds / 3600 * CPU_COST_PER_HOUR_USD
    total_usd = scribe_cost_usd + cpu_cost_usd
    entry = {
        "job_id": job_id,
        "timestamp": time.time(),
        "scribe_minutes": round(scribe_minutes, 3),
        "scribe_cost_usd": round(scribe_cost_usd, 4),
        "cpu_seconds": round(cpu_seconds, 2),
        "cpu_cost_usd": round(cpu_cost_usd, 4),
        "total_cost_usd": round(total_usd, 4),
        "total_cost_uzs": round(total_usd * USD_TO_UZS, 0),
    }
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
