import os
import shutil
import threading
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from user import get_current_username

system_stats_router = APIRouter(
	prefix="/system-stats",
	tags=["system-stats"],
	dependencies=[Depends(get_current_username)],
)

class UsageStats(BaseModel):
	total_bytes: int
	used_bytes: int
	free_bytes: int
	usage_percent: float

class SystemStatsResponse(BaseModel):
	cpu_usage_percent: float
	memory: UsageStats
	disk: UsageStats
	collected_at: datetime

class SystemStatsService:
	_cpu_lock = threading.Lock()
	_last_total = 0
	_last_idle = 0

	@staticmethod
	def _read_cpu_times() -> tuple[int, int]:
		with open("/proc/stat", "r", encoding="utf-8") as stat_file:
			cpu_parts = stat_file.readline().split()

		values = [int(value) for value in cpu_parts[1:]]
		idle = values[3] + values[4]
		total = sum(values)
		return total, idle

	@classmethod
	def get_cpu_usage_percent(cls) -> float:
		with cls._cpu_lock:
			current_total, current_idle = cls._read_cpu_times()

			if cls._last_total == 0:
				cls._last_total = current_total
				cls._last_idle = current_idle
				return 0.0

			total_delta = current_total - cls._last_total
			idle_delta = current_idle - cls._last_idle

			cls._last_total = current_total
			cls._last_idle = current_idle

		if total_delta <= 0:
			return 0.0

		usage_percent = (total_delta - idle_delta) / total_delta * 100
		return round(max(0.0, min(usage_percent, 100.0)), 2)

	@staticmethod
	def get_memory_usage() -> UsageStats:
		memory_info: dict[str, int] = {}

		with open("/proc/meminfo", "r", encoding="utf-8") as meminfo_file:
			for line in meminfo_file:
				key, value = line.split(":", maxsplit=1)
				memory_info[key] = int(value.strip().split()[0]) * 1024

		total_bytes = memory_info["MemTotal"]
		free_bytes = memory_info["MemAvailable"]
		used_bytes = total_bytes - free_bytes
		usage_percent = used_bytes / total_bytes * 100 if total_bytes else 0.0

		return UsageStats(
			total_bytes=total_bytes,
			used_bytes=used_bytes,
			free_bytes=free_bytes,
			usage_percent=round(usage_percent, 2),
		)

	@staticmethod
	def get_disk_usage(path: str = "/") -> UsageStats:
		usage = shutil.disk_usage(path)
		usage_percent = usage.used / usage.total * 100 if usage.total else 0.0

		return UsageStats(
			total_bytes=usage.total,
			used_bytes=usage.used,
			free_bytes=usage.free,
			usage_percent=round(usage_percent, 2),
		)

	@classmethod
	def collect(cls) -> SystemStatsResponse:
		return SystemStatsResponse(
			cpu_usage_percent=cls.get_cpu_usage_percent(),
			memory=cls.get_memory_usage(),
			disk=cls.get_disk_usage(),
			collected_at=datetime.now(timezone.utc),
		)

SystemStatsService._last_total, SystemStatsService._last_idle = SystemStatsService._read_cpu_times()

@system_stats_router.get("", response_model=SystemStatsResponse)
def get_system_stats():
	return SystemStatsService.collect()
