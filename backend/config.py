import json, re
from ipaddress import IPv4Address
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from service_controller import ServiceController
from user import get_current_username

config_router = APIRouter(
    prefix="/config",
    tags=["config"],
    dependencies=[Depends(get_current_username)],
)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data_files"
DATA_DIR.mkdir(exist_ok=True)

NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class ClientConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    DOMAINS: list[str]
    DATA_ENCRYPTION_METHOD: int
    ENCRYPTION_KEY: str
    PROTOCOL_TYPE: str
    LISTEN_IP: IPv4Address
    LISTEN_PORT: int
    SOCKS5_AUTH: bool
    RESOLVER_BALANCING_STRATEGY: int
    PACKET_DUPLICATION_COUNT: int
    SETUP_PACKET_DUPLICATION_COUNT: int
    MIN_UPLOAD_MTU: int
    MIN_DOWNLOAD_MTU: int
    MAX_UPLOAD_MTU: int
    MAX_DOWNLOAD_MTU: int
    RX_TX_WORKERS: int
    TUNNEL_PROCESS_WORKERS: int
    SESSION_INIT_RACING_COUNT: int
    MAX_PACKETS_PER_BATCH: int
    ARQ_WINDOW_SIZE: int
    ARQ_INITIAL_RTO_SECONDS: float
    ARQ_MAX_RTO_SECONDS: float
    LOG_LEVEL: str

    @field_validator("DOMAINS")
    @classmethod
    def validate_domains(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("DOMAINS must contain at least one domain")
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Each domain must be a non-empty string")
        return value

    @field_validator("ENCRYPTION_KEY", "PROTOCOL_TYPE", "LOG_LEVEL")
    @classmethod
    def validate_non_empty_strings(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty")
        return cleaned

    @field_validator("LISTEN_PORT")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("LISTEN_PORT must be between 1 and 65535")
        return value

    @field_validator(
        "DATA_ENCRYPTION_METHOD",
        "RESOLVER_BALANCING_STRATEGY",
        "PACKET_DUPLICATION_COUNT",
        "SETUP_PACKET_DUPLICATION_COUNT",
        "RX_TX_WORKERS",
        "TUNNEL_PROCESS_WORKERS",
        "SESSION_INIT_RACING_COUNT",
        "MAX_PACKETS_PER_BATCH",
        "ARQ_WINDOW_SIZE",
    )
    @classmethod
    def validate_non_negative_numbers(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Value cannot be negative")
        return value

    @field_validator(
        "MIN_UPLOAD_MTU",
        "MIN_DOWNLOAD_MTU",
        "MAX_UPLOAD_MTU",
        "MAX_DOWNLOAD_MTU",
    )
    @classmethod
    def validate_positive_mtu(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MTU values must be greater than zero")
        return value

    @field_validator("ARQ_INITIAL_RTO_SECONDS", "ARQ_MAX_RTO_SECONDS")
    @classmethod
    def validate_positive_rto(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("RTO values must be greater than zero")
        return value

    @model_validator(mode="after")
    def validate_ranges(self) -> "ClientConfig":
        if self.MIN_UPLOAD_MTU > self.MAX_UPLOAD_MTU:
            raise ValueError("MIN_UPLOAD_MTU cannot be greater than MAX_UPLOAD_MTU")
        if self.MIN_DOWNLOAD_MTU > self.MAX_DOWNLOAD_MTU:
            raise ValueError("MIN_DOWNLOAD_MTU cannot be greater than MAX_DOWNLOAD_MTU")
        if self.ARQ_INITIAL_RTO_SECONDS > self.ARQ_MAX_RTO_SECONDS:
            raise ValueError("ARQ_INITIAL_RTO_SECONDS cannot be greater than ARQ_MAX_RTO_SECONDS")
        return self


class CreateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    configure: ClientConfig
    resolver: list[IPv4Address]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Name cannot be empty")
        if not NAME_PATTERN.fullmatch(cleaned):
            raise ValueError("Name can only contain letters, numbers, hyphens, and underscores")
        return cleaned

    @field_validator("resolver")
    @classmethod
    def validate_resolver(cls, value: list[IPv4Address]) -> list[IPv4Address]:
        if not value:
            raise ValueError("Resolver must contain at least one IPv4 address")
        return value


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configure: ClientConfig
    resolver: list[IPv4Address]

    @field_validator("resolver")
    @classmethod
    def validate_resolver(cls, value: list[IPv4Address]) -> list[IPv4Address]:
        if not value:
            raise ValueError("Resolver must contain at least one IPv4 address")
        return value


def profile_file_path(name: str) -> Path:
    return DATA_DIR / f"{name}.json"


class ConfigCRUD:
    @staticmethod
    def validate_name(name: str) -> str:
        cleaned = name.strip()
        if not cleaned or not NAME_PATTERN.fullmatch(cleaned):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid profile name"
            )
        return cleaned

    @staticmethod
    def ensure_not_exists(file_path: Path, name: str) -> None:
        if file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Profile '{name}' already exists"
            )

    @staticmethod
    def ensure_exists(file_path: Path, name: str) -> None:
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile '{name}' not found"
            )

    @staticmethod
    def serialize_payload(name: str, configure: ClientConfig, resolver: list[IPv4Address]) -> dict[str, Any]:
        return {
            "name": name,
            "configure": {
                key: str(value) if isinstance(value, IPv4Address) else value
                for key, value in configure.model_dump().items()
            },
            "resolver": [str(ip) for ip in resolver]
        }

    @staticmethod
    def write_profile(file_path: Path, payload: dict[str, Any], action: str) -> None:
        try:
            file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error {action} profile file: {exc}"
            ) from exc

    @staticmethod
    def read_profile(file_path: Path) -> dict[str, Any]:
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error reading profile file: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Profile file is corrupted: {exc}"
            ) from exc

    @classmethod
    def create(cls, request: CreateProfileRequest) -> dict[str, Any]:
        name = cls.validate_name(request.name)
        file_path = profile_file_path(name)
        cls.ensure_not_exists(file_path, name)

        payload = cls.serialize_payload(name, request.configure, request.resolver)
        cls.write_profile(file_path, payload, "creating")

        try:
            service_data = ServiceController.provision_for_profile(name)
        except HTTPException:
            if file_path.exists():
                try:
                    file_path.unlink()
                except OSError:
                    pass
            raise

        return {
            "status": "success",
            "message": f"Profile '{name}' created successfully",
            "file": file_path.name,
            "data": payload,
            "service": service_data,
        }

    @classmethod
    def update(cls, name: str, request: UpdateProfileRequest) -> dict[str, Any]:
        validated_name = cls.validate_name(name)
        file_path = profile_file_path(validated_name)
        cls.ensure_exists(file_path, validated_name)

        payload = cls.serialize_payload(validated_name, request.configure, request.resolver)
        cls.write_profile(file_path, payload, "updating")

        service_data = ServiceController.sync_after_update(validated_name)

        return {
            "status": "success",
            "message": f"Profile '{validated_name}' updated successfully",
            "file": file_path.name,
            "data": payload,
            "service": service_data,
        }

    @classmethod
    def delete(cls, name: str) -> dict[str, Any]:
        validated_name = cls.validate_name(name)
        file_path = profile_file_path(validated_name)
        cls.ensure_exists(file_path, validated_name)
        service_data = ServiceController.remove_for_profile(validated_name)

        try:
            file_path.unlink()
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error deleting profile file: {exc}"
            ) from exc

        return {
            "status": "success",
            "message": f"Profile '{validated_name}' deleted successfully",
            "service": service_data,
        }

    @staticmethod
    def list_all() -> dict[str, Any]:
        files = sorted(path.stem for path in DATA_DIR.glob("*.json"))
        return {
            "status": "success",
            "count": len(files),
            "profiles": files
        }

    @classmethod
    def get(cls, name: str) -> dict[str, Any]:
        validated_name = cls.validate_name(name)
        file_path = profile_file_path(validated_name)
        cls.ensure_exists(file_path, validated_name)

        return {
            "status": "success",
            "data": cls.read_profile(file_path)
        }


@config_router.post("", status_code=status.HTTP_201_CREATED)
def create_profile(request: CreateProfileRequest, _: str = Depends(get_current_username)):
    return ConfigCRUD.create(request)


@config_router.put("/{name}")
def update_profile(name: str, request: UpdateProfileRequest, _: str = Depends(get_current_username)):
    return ConfigCRUD.update(name, request)


@config_router.delete("/{name}")
def delete_profile(name: str):
    return ConfigCRUD.delete(name)


@config_router.get("")
def list_profiles():
    return ConfigCRUD.list_all()


@config_router.get("/{name}")
def get_profile(name: str):
    return ConfigCRUD.get(name)
