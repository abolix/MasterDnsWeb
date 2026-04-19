import io, json, re, sys, zipfile
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, field_validator

from service_controller import ServiceController
from user import get_current_username

config_router = APIRouter(
    prefix="/config",
    tags=["config"],
    dependencies=[Depends(get_current_username)],
)

def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _app_dir()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class ClientConfig(BaseModel):
    """Accepts any TOML-derived config keys. Only DOMAINS and ENCRYPTION_KEY are required."""
    model_config = ConfigDict(extra="allow")

    DOMAINS: list[str]
    ENCRYPTION_KEY: str

    @field_validator("DOMAINS")
    @classmethod
    def validate_domains(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("DOMAINS must contain at least one domain")
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Each domain must be a non-empty string")
        return value

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("ENCRYPTION_KEY cannot be empty")
        return cleaned


class CreateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    configure: ClientConfig
    resolver: list[str]

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
    def validate_resolver(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("Resolver must contain at least one address")
        return value


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configure: ClientConfig
    resolver: list[str]

    @field_validator("resolver")
    @classmethod
    def validate_resolver(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("Resolver must contain at least one address")
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
    def serialize_payload(name: str, configure: ClientConfig, resolver: list[str]) -> dict[str, Any]:
        return {
            "name": name,
            "configure": configure.model_dump(),
            "resolver": resolver,
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


@config_router.get("")
def list_profiles():
    return ConfigCRUD.list_all()


@config_router.get("/export/{name}")
def export_profile(name: str, _: str = Depends(get_current_username)):
    """Download a profile as a JSON file."""
    validated_name = ConfigCRUD.validate_name(name)
    file_path = profile_file_path(validated_name)
    ConfigCRUD.ensure_exists(file_path, validated_name)
    data = file_path.read_bytes()
    return Response(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{validated_name}.json"'},
    )


@config_router.post("/import")
async def import_profile(file: UploadFile, _: str = Depends(get_current_username)):
    """Upload a profile JSON file to create a new instance."""
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .json files are accepted")

    raw = await file.read()
    if len(raw) > 1_048_576:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is too large (max 1 MB)")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON: {exc}") from exc

    name = payload.get("name")
    if not name or not NAME_PATTERN.fullmatch(str(name)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or missing 'name' in JSON")

    configure = payload.get("configure")
    resolver = payload.get("resolver")
    if not isinstance(configure, dict) or not isinstance(resolver, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON must contain 'configure' (object) and 'resolver' (array)")

    request = CreateProfileRequest(
        name=name,
        configure=ClientConfig(**configure),
        resolver=resolver,
    )
    return ConfigCRUD.create(request)


@config_router.get("/export-all")
def export_all_profiles(_: str = Depends(get_current_username)):
    """Download all profiles as a zip archive."""
    files = sorted(DATA_DIR.glob("*.json"))
    if not files:
        raise HTTPException(status_code=404, detail="No profiles found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.writestr(f.name, f.read_bytes())
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="masterdns-backup.zip"'},
    )


@config_router.post("/import-all")
async def import_all_profiles(file: UploadFile, _: str = Depends(get_current_username)):
    """Upload a zip of profile JSON files to import."""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")
    raw = await file.read()
    if len(raw) > 10_485_760:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            created = []
            errors = []
            for entry in zf.namelist():
                if not entry.endswith(".json"):
                    continue
                try:
                    payload = json.loads(zf.read(entry))
                    name = payload.get("name")
                    if not name or not NAME_PATTERN.fullmatch(str(name)):
                        errors.append(f"{entry}: invalid name")
                        continue
                    configure = payload.get("configure")
                    resolver = payload.get("resolver")
                    if not isinstance(configure, dict) or not isinstance(resolver, list):
                        errors.append(f"{entry}: invalid structure")
                        continue
                    request = CreateProfileRequest(
                        name=name,
                        configure=ClientConfig(**configure),
                        resolver=resolver,
                    )
                    ConfigCRUD.create(request)
                    created.append(name)
                except HTTPException as exc:
                    errors.append(f"{entry}: {exc.detail}")
                except Exception as exc:
                    errors.append(f"{entry}: {exc}")
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail=f"Invalid zip: {exc}") from exc

    return {"created": created, "errors": errors}


@config_router.put("/{name}")
def update_profile(name: str, request: UpdateProfileRequest, _: str = Depends(get_current_username)):
    return ConfigCRUD.update(name, request)


@config_router.delete("/{name}")
def delete_profile(name: str):
    return ConfigCRUD.delete(name)


@config_router.get("/{name}")
def get_profile(name: str):
    return ConfigCRUD.get(name)
