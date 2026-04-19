import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _app_dir() -> Path:
    """Return the app directory: binary's folder in production, project root in dev."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

try:
	from dotenv import load_dotenv
except ModuleNotFoundError:
	def load_dotenv(*args, **kwargs):
		return False

from fastapi import APIRouter, Depends, HTTPException, Query, status

from user import get_current_username

load_dotenv(dotenv_path=_app_dir() / ".env", override=False)

service_router = APIRouter(
	prefix="/service",
	tags=["service"],
	dependencies=[Depends(get_current_username)],
)

NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class ServiceController:
	@staticmethod
	def validate_name(name: str) -> str:
		cleaned = name.strip()
		if not cleaned or not NAME_PATTERN.fullmatch(cleaned):
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Invalid profile name",
			)
		return cleaned

	@staticmethod
	def systemd_dir() -> Path:
		return Path(os.getenv("MASTERVPN_SYSTEMD_DIR", "/etc/systemd/system"))

	@staticmethod
	def service_name_prefix() -> str:
		return os.getenv("MASTERVPN_SERVICE_NAME_PREFIX", "masterdnsvpn")

	@staticmethod
	def service_description() -> str:
		return os.getenv("MASTERVPN_SERVICE_DESCRIPTION", "MasterDnsVPN Client")

	@staticmethod
	def exec_start() -> str:
		return os.getenv("MASTERVPN_SERVICE_EXEC_START", "MasterDnsVPN")

	@classmethod
	def resolve_runtime_binary_source(cls) -> Path:
		raw_exec_start = cls.exec_start().strip()
		if not raw_exec_start:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail="MASTERVPN_SERVICE_EXEC_START is empty",
			)

		app_dir = _app_dir()
		backend_dir = Path(__file__).resolve().parent
		configured_path = Path(raw_exec_start).expanduser()
		candidates: list[Path] = []

		# 1. Next to the running binary (release layout: MasterDnsWeb/ folder)
		if configured_path.name:
			candidates.append(app_dir / configured_path.name)

		# 2. Absolute path as configured
		if configured_path.is_absolute():
			candidates.append(configured_path)
		else:
			candidates.append((backend_dir / configured_path).resolve())

		# 3. Dev fallback: backend/bin/
		if configured_path.name:
			candidates.append(backend_dir / "bin" / configured_path.name)

		for candidate in candidates:
			if candidate.exists() and candidate.is_file():
				return candidate

		candidate_text = ", ".join(str(path) for path in candidates)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=(
				"MasterDnsVPN binary was not found. Checked: "
				f"{candidate_text}. Place MasterDnsVPN next to MasterDnsWeb, or set MASTERVPN_SERVICE_EXEC_START."
			),
		)

	@staticmethod
	def service_user() -> str:
		return os.getenv("MASTERVPN_SERVICE_USER", "root")

	@staticmethod
	def restart_policy() -> str:
		return os.getenv("MASTERVPN_SERVICE_RESTART", "always")

	@staticmethod
	def restart_sec() -> str:
		return os.getenv("MASTERVPN_SERVICE_RESTART_SEC", "5")

	@staticmethod
	def _needs_sudo() -> bool:
		"""True when the process is not already running as root."""
		return hasattr(os, "geteuid") and os.geteuid() != 0

	@staticmethod
	def unit_name(name: str) -> str:
		validated_name = ServiceController.validate_name(name)
		return f"{ServiceController.service_name_prefix()}-{validated_name}.service"

	@classmethod
	def unit_file_path(cls, name: str) -> Path:
		return cls.systemd_dir() / cls.unit_name(name)

	@staticmethod
	def profile_path(name: str) -> Path:
		return _app_dir() / "data" / f"{name}.json"

	@staticmethod
	def _escape_env_value(value: str) -> str:
		return value.replace("\\", "\\\\").replace('"', '\\"')

	@classmethod
	def profile_listen_port(cls, name: str) -> int:
		profile_file = cls.profile_path(name)
		default_port = int(os.getenv("PORT", "8000"))

		try:
			payload = json.loads(profile_file.read_text(encoding="utf-8"))
			configure = payload.get("configure", {})
			raw_port = configure.get("LISTEN_PORT", default_port)
			port = int(raw_port)
		except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail=f"Invalid profile port in '{profile_file.name}': {exc}",
			) from exc

		if not 1 <= port <= 65535:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail=f"LISTEN_PORT for profile '{name}' must be between 1 and 65535",
			)

		return port

	@classmethod
	def runtime_dir_for_profile(cls, name: str) -> Path:
		"""Each profile gets its own runtime directory with config + resolvers."""
		base = _app_dir() / "runtime" / name
		base.mkdir(parents=True, exist_ok=True)
		return base

	@classmethod
	def generate_runtime_files(cls, name: str) -> Path:
		"""Read profile JSON -> write client_config.toml + client_resolvers.txt
		into a per-profile runtime directory. Returns the directory path."""
		validated_name = cls.validate_name(name)
		profile_file = cls.profile_path(validated_name)

		try:
			payload = json.loads(profile_file.read_text(encoding="utf-8"))
		except (OSError, json.JSONDecodeError) as exc:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail=f"Cannot read profile '{validated_name}': {exc}",
			) from exc

		configure: dict[str, Any] = payload.get("configure", {})
		resolvers: list[str] = payload.get("resolver", [])

		runtime_dir = cls.runtime_dir_for_profile(validated_name)

		# --- client_config.toml ---
		toml_lines: list[str] = []
		for key, value in configure.items():
			if isinstance(value, list):
				items = ", ".join(f'"{v}"' for v in value)
				toml_lines.append(f"{key} = [{items}]")
			elif isinstance(value, bool):
				toml_lines.append(f"{key} = {str(value).lower()}")
			elif isinstance(value, int):
				toml_lines.append(f"{key} = {value}")
			elif isinstance(value, float):
				toml_lines.append(f"{key} = {value}")
			elif isinstance(value, str):
				toml_lines.append(f'{key} = "{value}"')
			else:
				toml_lines.append(f'{key} = "{value}"')

		config_path = runtime_dir / "client_config.toml"
		config_path.write_text("\n".join(toml_lines) + "\n", encoding="utf-8")

		resolvers_path = runtime_dir / "client_resolvers.txt"
		resolvers_path.write_text("\n".join(resolvers) + "\n", encoding="utf-8")

		binary_source = cls.resolve_runtime_binary_source()
		binary_dest = runtime_dir / binary_source.name
		if binary_dest.exists() or binary_dest.is_symlink():
			binary_dest.unlink()
		try:
			shutil.copy2(binary_source, binary_dest)
			binary_dest.chmod(0o755)
		except OSError as exc:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail=f"Failed to prepare runtime binary for profile '{validated_name}': {exc}",
			) from exc

		return runtime_dir

	@classmethod
	def build_unit_content(cls, name: str) -> str:
		validated_name = cls.validate_name(name)
		profile_path = cls.profile_path(validated_name)
		# resolve binary first so we fail early with a clear message
		binary_source = cls.resolve_runtime_binary_source()
		runtime_dir = cls.generate_runtime_files(validated_name)
		description = cls.service_description()
		binary_name = binary_source.name
		exec_start_in_runtime = str(runtime_dir / binary_name)
		service_user = cls.service_user().strip()
		restart_policy = cls.restart_policy().strip()
		restart_sec = cls.restart_sec().strip()

		if not service_user:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail="MASTERVPN_SERVICE_USER is empty",
			)

		profile_name_value = cls._escape_env_value(validated_name)
		profile_path_value = cls._escape_env_value(str(profile_path))

		return "\n".join(
			[
				"[Unit]",
				f"Description={description} ({validated_name})",
				"After=network.target",
				"",
				"[Service]",
				"Type=simple",
				f"WorkingDirectory={runtime_dir}",
				f"Environment=\"MASTERVPN_PROFILE_NAME={profile_name_value}\"",
				f"Environment=\"MASTERVPN_PROFILE_PATH={profile_path_value}\"",
				f"ExecStart={exec_start_in_runtime}",
				f"Restart={restart_policy}",
				f"RestartSec={restart_sec}",
				f"User={service_user}",
				"",
				"[Install]",
				"WantedBy=multi-user.target",
				"",
			]
		)

	@staticmethod
	def _ensure_systemctl_available() -> None:
		if shutil.which("systemctl") is None:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail="systemctl is not available on this host",
			)

	@classmethod
	def _build_privileged_command(cls, args: list[str]) -> list[str]:
		if not cls._needs_sudo():
			return args

		if shutil.which("sudo") is None:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail="sudo is not available. Run MasterDnsWeb as root.",
			)

		return ["sudo", "-n", *args]

	@classmethod
	def _ensure_sudo_session(cls) -> None:
		if not cls.use_sudo():
			return

		password = cls.sudo_password()
		if password is None:
			return

		process = subprocess.run(
			["sudo", "-S", "-k", "-p", "", "-v"],
			capture_output=True,
			text=True,
			input=f"{password}\n",
			check=False,
		)

		if process.returncode != 0:
			message = process.stderr.strip() or process.stdout.strip() or "sudo authentication failed"
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail=(
					"Sudo authentication failed. Use the sudo password of the user running the API process "
					f"(not necessarily root password). Details: {message}"
				),
			)

	@classmethod
	def _command_error_detail(cls, process: subprocess.CompletedProcess[str], fallback: str) -> str:
		output = process.stderr.strip() or process.stdout.strip() or fallback
		if "sudo" in output.lower() and (
			"password is required" in output.lower()
			or "a terminal is required" in output.lower()
			or "no tty present" in output.lower()
		):
			return (
				"Privileged access is required. Run MasterDnsWeb as root (sudo ./MasterDnsWeb) "
				"or configure passwordless sudo for the current user."
			)
		return output

	@classmethod
	def _run_command(
		cls,
		args: list[str],
		*,
		check: bool = True,
	) -> subprocess.CompletedProcess[str]:
		command = cls._build_privileged_command(args)
		process = subprocess.run(
			command,
			capture_output=True,
			text=True,
			check=False,
		)

		if check and process.returncode != 0:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail=cls._command_error_detail(process, "Command execution failed"),
			)

		return process

	@classmethod
	def _run_systemctl(
		cls,
		args: list[str],
		*,
		check: bool = True,
	) -> subprocess.CompletedProcess[str]:
		cls._ensure_systemctl_available()
		return cls._run_command(["systemctl", *args], check=check)

	@staticmethod
	def _can_write_to_directory(path: Path) -> bool:
		return path.exists() and os.access(path, os.W_OK)

	@classmethod
	def ensure_unit_exists(cls, name: str) -> Path:
		unit_path = cls.unit_file_path(name)
		if not unit_path.exists():
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail=f"Service unit '{cls.unit_name(name)}' not found",
			)
		return unit_path

	@classmethod
	def write_unit_file(cls, name: str) -> Path:
		unit_path = cls.unit_file_path(name)
		unit_content = cls.build_unit_content(name)
		try:
			if cls._can_write_to_directory(unit_path.parent):
				unit_path.parent.mkdir(parents=True, exist_ok=True)
				unit_path.write_text(unit_content, encoding="utf-8")
			else:
				with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as temp_file:
					temp_file.write(unit_content)
					temp_path = Path(temp_file.name)

				try:
					cls._run_command(["mkdir", "-p", str(unit_path.parent)])
					cls._run_command(["install", "-m", "644", str(temp_path), str(unit_path)])
				finally:
					temp_path.unlink(missing_ok=True)
		except OSError as exc:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail=f"Error writing service unit file: {exc}",
			) from exc
		return unit_path

	@classmethod
	def remove_unit_file(cls, name: str) -> None:
		unit_path = cls.unit_file_path(name)
		if not unit_path.exists():
			return
		try:
			if cls._can_write_to_directory(unit_path.parent):
				unit_path.unlink()
			else:
				cls._run_command(["rm", "-f", str(unit_path)])
		except OSError as exc:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail=f"Error removing service unit file: {exc}",
			) from exc

	@classmethod
	def daemon_reload(cls) -> None:
		cls._run_systemctl(["daemon-reload"])

	@classmethod
	def enable(cls, name: str) -> None:
		cls.ensure_unit_exists(name)
		cls._run_systemctl(["enable", cls.unit_name(name)])

	@classmethod
	def disable(cls, name: str) -> None:
		cls._run_systemctl(["disable", cls.unit_name(name)], check=False)

	@classmethod
	def start(cls, name: str) -> dict[str, Any]:
		cls.ensure_unit_exists(name)
		cls._run_systemctl(["start", cls.unit_name(name)])
		return {
			"status": "success",
			"message": f"Service '{cls.unit_name(name)}' started successfully",
			"unit": cls.unit_name(name),
		}

	@classmethod
	def stop(cls, name: str) -> dict[str, Any]:
		cls.ensure_unit_exists(name)
		cls._run_systemctl(["stop", cls.unit_name(name)])
		return {
			"status": "success",
			"message": f"Service '{cls.unit_name(name)}' stopped successfully",
			"unit": cls.unit_name(name),
		}

	@classmethod
	def restart(cls, name: str) -> dict[str, Any]:
		cls.ensure_unit_exists(name)
		cls._run_systemctl(["restart", cls.unit_name(name)])
		return {
			"status": "success",
			"message": f"Service '{cls.unit_name(name)}' restarted successfully",
			"unit": cls.unit_name(name),
		}

	@classmethod
	def status(cls, name: str) -> dict[str, Any]:
		cls.ensure_unit_exists(name)
		unit_name = cls.unit_name(name)
		status_result = cls._run_systemctl(["status", unit_name, "--no-pager", "--full"], check=False)
		enabled_result = cls._run_systemctl(["is-enabled", unit_name], check=False)

		return {
			"status": "success",
			"unit": unit_name,
			"unit_file": str(cls.unit_file_path(name)),
			"enabled": enabled_result.stdout.strip() or enabled_result.stderr.strip() or "unknown",
			"return_code": status_result.returncode,
			"output": status_result.stdout.strip() or status_result.stderr.strip(),
		}

	@classmethod
	def logs(cls, name: str, lines: int = 100) -> dict[str, Any]:
		cls.ensure_unit_exists(name)
		unit_name = cls.unit_name(name)
		safe_lines = max(1, min(lines, 2000))
		logs_result = cls._run_command(
			[
				"journalctl",
				"-u",
				unit_name,
				"-n",
				str(safe_lines),
				"--no-pager",
			],
			check=False,
		)

		return {
			"status": "success",
			"unit": unit_name,
			"requested_lines": safe_lines,
			"return_code": logs_result.returncode,
			"output": logs_result.stdout.strip() or logs_result.stderr.strip(),
		}

	@classmethod
	def provision_for_profile(cls, name: str) -> dict[str, Any]:
		validated_name = cls.validate_name(name)
		unit_path = cls.write_unit_file(validated_name)
		cls.daemon_reload()
		cls.enable(validated_name)

		return {
			"status": "success",
			"message": f"Service '{cls.unit_name(validated_name)}' initialized successfully",
			"unit": cls.unit_name(validated_name),
			"unit_file": str(unit_path),
		}

	@classmethod
	def sync_after_update(cls, name: str) -> dict[str, Any]:
		validated_name = cls.validate_name(name)
		unit_path = cls.write_unit_file(validated_name)
		cls.daemon_reload()
		cls._run_systemctl(["stop", cls.unit_name(validated_name)], check=False)

		# Attempt to restart the service.  If the service fails to start (e.g.
		# the binary rejects the configuration), we do NOT propagate the error
		# back as an HTTP 500 — the config has already been saved successfully.
		# The caller can inspect instance status / logs to diagnose startup issues.
		start_warning: str | None = None
		try:
			cls._run_systemctl(["start", cls.unit_name(validated_name)])
		except HTTPException as exc:
			start_warning = exc.detail

		result: dict[str, Any] = {
			"status": "success",
			"message": f"Service '{cls.unit_name(validated_name)}' refreshed successfully",
			"unit": cls.unit_name(validated_name),
			"unit_file": str(unit_path),
		}
		if start_warning:
			result["start_warning"] = start_warning
		return result

	@classmethod
	def remove_for_profile(cls, name: str) -> dict[str, Any]:
		validated_name = cls.validate_name(name)
		unit_name = cls.unit_name(validated_name)
		cls._run_systemctl(["stop", unit_name], check=False)
		cls._run_systemctl(["disable", unit_name], check=False)
		cls.remove_unit_file(validated_name)
		cls.daemon_reload()

		runtime_dir = cls.runtime_dir_for_profile(validated_name)
		if runtime_dir.exists():
			shutil.rmtree(runtime_dir, ignore_errors=True)

		return {
			"status": "success",
			"message": f"Service '{unit_name}' removed successfully",
			"unit": unit_name,
		}


@service_router.post("/{name}/start")
def start_service(name: str):
	return ServiceController.start(name)


@service_router.post("/{name}/stop")
def stop_service(name: str):
	return ServiceController.stop(name)


@service_router.post("/{name}/restart")
def restart_service(name: str):
	return ServiceController.restart(name)


@service_router.get("/{name}/status")
def get_service_status(name: str):
	return ServiceController.status(name)


@service_router.get("/{name}/logs")
def get_service_logs(name: str, lines: int = Query(default=100, ge=1, le=2000)):
	return ServiceController.logs(name, lines)


@service_router.get("/binary-version")
def get_binary_version():
	"""Return the MasterDnsVPN binary version string."""
	try:
		binary = ServiceController.resolve_runtime_binary_source()
	except HTTPException:
		return {"version": None, "error": "Binary not found"}

	try:
		result = subprocess.run(
			[str(binary), "--version"],
			capture_output=True,
			text=True,
			timeout=5,
			check=False,
		)
		output = (result.stdout.strip() or result.stderr.strip()) or "unknown"
	except subprocess.TimeoutExpired:
		return {"version": None, "error": "Binary timed out"}

	return {"version": output}
