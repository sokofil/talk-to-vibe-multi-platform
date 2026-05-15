# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files

project_root = Path.cwd()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from talk_to_vibe import __version__

prompt_datas = collect_data_files("talk_to_vibe.providers.prompts", includes=["*.md"])
whisper_datas = collect_data_files("faster_whisper.assets")

a = Analysis(
    [str(project_root / "talk_to_vibe" / "__main__.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=prompt_datas + whisper_datas,
    hiddenimports=["rumps", "faster_whisper", "faster_whisper.assets", "ctranslate2"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
