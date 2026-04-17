# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for MasterWeb – Linux amd64 single-file build
# Usage:  pyinstaller build.spec
# Output: dist/MasterDnsWeb

from pathlib import Path

block_cipher = None
backend_dir = Path("backend")
static_dir = backend_dir / "static"

datas = []
if static_dir.exists():
    datas.append((str(static_dir), "static"))

a = Analysis(
    [str(backend_dir / "main.py")],
    pathex=[str(backend_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "jose",
        "jose.jwt",
        "dotenv",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MasterDnsWeb",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=True,
    target_arch="x86_64",
)
