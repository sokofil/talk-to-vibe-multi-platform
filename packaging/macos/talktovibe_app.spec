# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_all

project_root = Path.cwd()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from talk_to_vibe import __version__

import importlib.util

prompt_datas = collect_data_files("talk_to_vibe.providers.prompts", includes=["*.md"])
whisper_datas = collect_data_files("faster_whisper.assets")

mlx_datas, mlx_binaries_auto, mlx_hidden = collect_all("mlx")
mlx_whisper_datas, mlx_whisper_binaries, mlx_whisper_hidden = collect_all("mlx_whisper")

# Explicitly include dylibs that PyInstaller can't resolve via @rpath
_mlx_spec = importlib.util.find_spec("mlx")
_mlx_pkg = Path(list(_mlx_spec.submodule_search_locations)[0])
mlx_lib = str(_mlx_pkg / "lib")
mlx_binaries_explicit = [
    (str(Path(mlx_lib) / "libmlx.dylib"), "mlx/lib"),
    (str(Path(mlx_lib) / "libjaccl.dylib"), "mlx/lib"),
]

a = Analysis(
    [str(project_root / "talk_to_vibe" / "__main__.py")],
    pathex=[str(project_root)],
    binaries=mlx_binaries_explicit + mlx_binaries_auto + mlx_whisper_binaries,
    datas=prompt_datas + whisper_datas + mlx_datas + mlx_whisper_datas,
    hiddenimports=[
        "rumps",
        "faster_whisper",
        "faster_whisper.assets",
        "ctranslate2",
        "tiktoken",
        "tiktoken_ext",
        "tiktoken_ext.openai_public",
    ] + mlx_hidden + mlx_whisper_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "torchvision", "torchaudio", "tensorflow", "jax"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TalkToVibe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TalkToVibe",
)

app = BUNDLE(
    coll,
    name="TalkToVibe.app",
    icon=None,
    bundle_identifier="com.talktovibe.app",
    version=__version__,
    info_plist={
        "CFBundleName": "TalkToVibe",
        "CFBundleDisplayName": "TalkToVibe",
        "LSUIElement": True,
        "NSPrincipalClass": "NSApplication",
        "NSAccessibilityUsageDescription": "TalkToVibe needs Accessibility access to monitor your push-to-talk shortcut and type transcribed text.",
        "NSMicrophoneUsageDescription": "TalkToVibe needs microphone access to record speech for transcription.",
    },
)
