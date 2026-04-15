import argparse
import sys

from talk_to_vibe import __version__
from talk_to_vibe.config.loader import load_config
from talk_to_vibe.config.wizard import run_wizard
from talk_to_vibe.config.constants import SUPPORTED_PROVIDERS
from talk_to_vibe.providers.factory import create_provider


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
        help="Run as macOS menu bar app (default on macOS)",
    )
    parser.add_argument(
        "--terminal",
        action="store_true",
        help="Run in terminal mode instead of menu bar",
    )
    args = parser.parse_args()

    if args.setup:
        config = run_wizard(force=True)
    else:
        config = load_config()

    if args.provider:
        config.provider = args.provider

    errors = config.validate()
    if errors:
        for err in errors:
            print(f"❌ {err}")
        print("Run: ./run_ttv.sh --setup")
        sys.exit(1)

    stt = create_provider(config)

    ptt_key = args.key or config.ptt_key
    auto_enter = config.auto_enter

    use_menubar = not args.terminal
    if sys.platform != "darwin":
        use_menubar = False

    if use_menubar:
        from talk_to_vibe.menubar import TalkToVibeMenuBar
        app = TalkToVibeMenuBar(stt=stt, ptt_key_name=ptt_key, auto_enter=auto_enter, prompt_file=config.prompt_file)
    else:
        from talk_to_vibe.app import TalkToVibe
        app = TalkToVibe(stt=stt, ptt_key_name=ptt_key, auto_enter=auto_enter)

    app.run()


if __name__ == "__main__":
    main()
