import argparse
import sys

from talk_to_vibe import __version__
from talk_to_vibe.config.loader import load_config
from talk_to_vibe.config.wizard import run_wizard
from talk_to_vibe.config.constants import SUPPORTED_PROVIDERS
from talk_to_vibe.providers.factory import create_provider
from talk_to_vibe.runtime_paths import APP_BUNDLE_NAME


def _setup_hint() -> str:
    if sys.platform == "darwin":
        return f"Re-run the setup helper, or open {APP_BUNDLE_NAME} and choose Reconfigure..."
    if sys.platform.startswith("linux"):
        return "Run: ./setup_linux.sh   (or ./run_ttv.sh --setup to re-run the wizard)"
    return "Run: ./run_ttv.sh --setup"


def main():
    parser = argparse.ArgumentParser(description="Talk to Vibe - Speech to Text for Vibe Coding")
    parser.add_argument(
        "--key",
        default=None,
        help="PTT key or chord (e.g. alt_r, f18, ctrl+alt_r)",
    )
    parser.add_argument("--setup", action="store_true", help="Re-configure STT provider & API key")
    parser.add_argument(
        "--provider",
        choices=SUPPORTED_PROVIDERS,
        help="One-off provider override (does not save to config)",
    )
    parser.add_argument(
        "--menubar",
        action="store_true",
        default=None,
        help="Run as menu bar / tray app (default on macOS and Linux)",
    )
    parser.add_argument(
        "--terminal",
        action="store_true",
        help="Run in terminal mode instead of menu bar / tray",
    )
    args = parser.parse_args()

    if args.setup:
        run_wizard(force=True)
        return
    else:
        config = load_config()

    if args.provider:
        config.provider = args.provider

    errors = config.validate()
    if errors:
        for err in errors:
            print(f"❌ {err}")
        print(_setup_hint())
        sys.exit(1)

    stt = create_provider(config)

    ptt_key = args.key or config.ptt_key
    auto_enter = config.auto_enter

    has_tray = sys.platform == "darwin" or sys.platform.startswith("linux")
    use_tray = has_tray and not args.terminal

    if use_tray and sys.platform == "darwin":
        from talk_to_vibe.menubar import TalkToVibeMenuBar
        app = TalkToVibeMenuBar(
            stt=stt,
            ptt_key_name=ptt_key,
            auto_enter=auto_enter,
            prompt_file=config.prompt_file,
            mic_preferences=config.mic_preferences,
        )
    elif use_tray and sys.platform.startswith("linux"):
        from talk_to_vibe.tray import TalkToVibeTray
        app = TalkToVibeTray(
            stt=stt,
            ptt_key_name=ptt_key,
            auto_enter=auto_enter,
            prompt_file=config.prompt_file,
            mic_preferences=config.mic_preferences,
        )
    else:
        from talk_to_vibe.app import TalkToVibe
        app = TalkToVibe(
            stt=stt,
            ptt_key_name=ptt_key,
            auto_enter=auto_enter,
            mic_preferences=config.mic_preferences,
        )

    app.run()


if __name__ == "__main__":
    main()
