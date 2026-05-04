# 🎤 Talk to Vibe

**Push-to-talk transcription for coding.**

TalkToVibe runs as a macOS menu bar app or Linux tray app. Tap your configured push-to-talk chord once to start recording, tap it again to stop, and the transcript is inserted into the focused app.

## Highlights

- macOS menu bar app and Linux tray app, with terminal mode for dev/debug work
- Cloud Whisper providers, GPT-compatible multimodal audio endpoints, or on-device `faster-whisper`
- Direct text insertion into the active app; Linux also keeps the clipboard populated when possible
- Reconfigure from the app menu, launch at login, and toggle Auto-Enter without editing config files
- Microphone preference ordering for USB/KVM/hot-plug setups
- Custom transcription prompts for multimodal chat-completions models

## Quick Start

### macOS Installed App

```bash
git clone https://github.com/mitchAtRFarm/talk-to-vibe-multi-platform.git
cd talk-to-vibe
./setup_macos.sh
```

This builds and installs `TalkToVibe.app` into `~/Applications`, installs the reconfigure helper, optionally enables launch at login, and opens the relevant macOS privacy panes.

Launch `~/Applications/TalkToVibe.app` when setup finishes. It runs as a menu bar app and does not need Terminal to stay open.

### Linux Installed App (X11)

```bash
git clone https://github.com/mitchAtRFarm/talk-to-vibe-multi-platform.git
cd talk-to-vibe
./setup_linux.sh
```

This installs system packages, builds the repo venv, writes a launcher and desktop entry, optionally enables autostart, and launches TalkToVibe as a tray app.

Tested on Ubuntu 24.04 + Cinnamon 6 (X11). The tray icon exposes `Provider Info`, `Auto-Enter`, `Reconfigure...`, `About`, and `Quit`, and swaps between idle, recording, and transcribing states.

> Wayland is not supported. Global hotkey capture uses X11.

### Generic Repo Setup

```bash
git clone https://github.com/mitchAtRFarm/talk-to-vibe-multi-platform.git
cd talk-to-vibe
bash setup.sh
./run_ttv.sh
```

On macOS and Linux, `./run_ttv.sh` defaults to the menu bar / tray app. Use `./run_ttv.sh --terminal` if you want the terminal UI instead.

First run asks you to choose a provider, enter credentials if that provider needs them, pick a push-to-talk chord, and optionally set microphone preferences, Auto-Enter, and a custom prompt file.

## Providers

TalkToVibe supports purpose-built transcription APIs, configurable multimodal audio endpoints, and local on-device transcription:

| Provider | Type | Default Model | Where It Runs | Notes |
|----------|------|---------------|---------------|-------|
| **Groq** | Whisper transcription | `whisper-large-v3-turbo` | Cloud | Fast `/audio/transcriptions` provider |
| **OpenAI** | Whisper transcription | `whisper-1` | Cloud | OpenAI `/audio/transcriptions` |
| **OpenAI-Compatible** | Whisper transcription | `whisper-1` | Your endpoint | Self-hosted or compatible OpenAI-style API |
| **OpenRouter** | Multimodal chat + audio | `google/gemini-3.1-flash-lite-preview` | Cloud by default | Uses a configurable `/chat/completions` endpoint with `input_audio`; OpenRouter is just the default wiring |
| **Local Whisper** | `faster-whisper` | `large-v3-turbo` | Local machine | No API key; on-device transcription |

### Whisper Transcription vs Multimodal Audio

**Whisper-style providers** (`groq`, `openai`, `openai_compatible`) upload a WAV file to `/audio/transcriptions` and return a transcript directly. They are the simplest choice for pure dictation.

**The `openrouter` provider path** sends base64-encoded audio to a chat-completions endpoint using a text prompt plus `input_audio`. The default config points at OpenRouter, but the `base_url` is configurable, so you can adapt it to another compatible endpoint if it accepts the same payload shape.

That means you are not locked to OpenRouter branding. If you have another provider or gateway that exposes a compatible chat-completions API for audio-capable models, you can point TalkToVibe at it by changing the model and `base_url` in config.

**Local Whisper** runs `faster-whisper` in-process with no network call. It is useful when you want local transcription or do not want to depend on an API key.

### Local Whisper Setup

If you want the built-in `local_whisper` provider:

```bash
./linux_install_and_set_whisper.sh
```

That helper installs `faster-whisper`, downloads the selected model, runs a smoke test, and rewrites `~/.talktovibe/config.yaml` to use `local_whisper`.

If you prefer to install it manually, install `requirements-local-whisper.txt` into the repo venv and then select `local_whisper` in `./run_ttv.sh --setup`.

### Multimodal Endpoint Examples

The default multimodal config looks like this:

```yaml
provider: openrouter
providers:
  openrouter:
    api_key: sk-or-...
    model: google/gemini-3.1-flash-lite-preview
    base_url: https://openrouter.ai/api/v1/chat/completions
```

If you have your own compatible gateway, keep `provider: openrouter` and change the nested `model`, `api_key`, and `base_url` values.

### Switch Provider

```bash
./run_ttv.sh --setup
./run_ttv.sh --provider openrouter
./run_ttv.sh --provider local_whisper
```

On macOS and Linux, the installed app also includes a `Reconfigure...` menu item.

## Usage

1. Launch `TalkToVibe.app` on macOS, run the Linux tray app, or start `./run_ttv.sh` in terminal mode.
2. Focus the target app: your IDE, terminal, browser, chat app, or anything else that accepts typed text.
3. Press your configured push-to-talk chord once to start recording.
4. Press the chord again to stop recording and transcribe.
5. TalkToVibe inserts the transcript into the focused app and optionally sends Enter if Auto-Enter is enabled.

On macOS and Linux, the background app shows state with the menu bar or tray icon while recording/transcribing.

### Change PTT Key

The PTT chord is configured during setup and saved to `~/.talktovibe/config.yaml`. You can also override it per run:

```bash
./run_ttv.sh --key ctrl+9
./run_ttv.sh --key ctrl+1
./run_ttv.sh --key ctrl+2
./run_ttv.sh --key f18
./run_ttv.sh --setup
```

Available keys on macOS include `ctrl+9` (default), `ctrl+1`-`ctrl+5`, `ctrl+8`, number keys `0-9`, `f18`, `f19`, `f20`, `f9`-`f12`, plus modifier-based keys such as `alt_r`, `cmd_r`, `ctrl_r`, and generic modifiers like `ctrl`, `alt`, `cmd`, and `shift`.

Available keys on Linux/X11 include `ctrl+9` (default), number keys `0-9`, `f1`-`f20`, and generic or side-specific modifiers such as `ctrl`, `ctrl_l`, `ctrl_r`, `alt`, `alt_l`, `alt_r`, `shift`, `shift_l`, `shift_r`, `super`, `super_l`, and `super_r`.

On macOS, avoid modifier-only bindings when possible. Chords like `ctrl+9` are more reliable than modifier-only shortcuts on global event taps.

On Linux, check for desktop-environment shortcut collisions before picking a chord.

### Custom Transcription Prompt

`prompt_file` is used by the multimodal chat-completions provider path. It lets you override the bundled coding-oriented transcription prompt with your own `.md` file:

```yaml
# ~/.talktovibe/config.yaml
prompt_file: ~/my_prompts/transcription.md
```

Set `prompt_file` to an empty string, or omit it, to use the bundled prompt. Whisper-style providers and `local_whisper` do not use this setting.

## macOS Permissions

On first launch of `TalkToVibe.app`, allow these in **System Settings -> Privacy & Security**:

- **Microphone**
- **Accessibility**
- **Input Monitoring** on systems that require it for global key listening

Without the macOS accessibility/input permissions, global hotkey capture and synthetic typing may not work.

## Linux Notes

TalkToVibe's Linux tray app is built for X11 desktops.

- X11 session required: Wayland does not support the current global hotkey path
- Clipboard helper: `xclip` is installed by `setup_linux.sh`; `xsel` and `wl-copy` are also supported if present
- Text injection: `xdotool` is preferred on Linux, with `pynput` as fallback
- Audio stack: PulseAudio or PipeWire must be working
- Tray host: AppIndicator / StatusNotifierItem support is required in the desktop panel
- Notifications use `notify-send`

On stock GNOME, you may also need the AppIndicator extension enabled for the tray icon to appear.

## Linux Install And Uninstall

Install:

```bash
./setup_linux.sh
```

Useful flags:

```bash
./setup_linux.sh --yes
./setup_linux.sh --skip-apt
./setup_linux.sh --skip-autostart
./setup_linux.sh --enable-autostart
./setup_linux.sh --reuse-config
./setup_linux.sh --no-launch
```

The installer apt-installs `libportaudio2`, `xclip`, `xdotool`, `libayatana-appindicator3-1`, `gir1.2-ayatanaappindicator3-0.1`, `python3-gi`, `python3-gi-cairo`, `libcanberra-gtk3-module`, `libnotify-bin`, and `python3-venv`, creates a `--system-site-packages` venv in the repo, runs the configuration wizard, writes a launcher at `~/.local/bin/talktovibe`, a desktop entry at `~/.local/share/applications/TalkToVibe.desktop`, and optionally an autostart entry at `~/.config/autostart/TalkToVibe.desktop`.

If the selected provider is `local_whisper` and `faster-whisper` is missing, `setup_linux.sh` automatically hands off to `./linux_install_and_set_whisper.sh`.

Uninstall:

```bash
./uninstall_linux.sh
```

Useful flags:

```bash
./uninstall_linux.sh --keep-config
./uninstall_linux.sh --remove-venv
./uninstall_linux.sh --yes
```

`uninstall_linux.sh` removes the launcher, desktop entry, autostart entry, logs, and config by default. It does not apt-uninstall system packages.

## macOS Install And Uninstall

Install or repair the packaged app:

```bash
./setup_macos.sh
```

Useful installer flags:

```bash
./setup_macos.sh --yes
./setup_macos.sh --skip-login-item
./setup_macos.sh --no-launch
./setup_macos.sh --rebuild
./setup_macos.sh --reuse-config
./setup_macos.sh --skip-signing
```

Uninstall the packaged app and its installed support files outside the repo:

```bash
./uninstall_macos.sh
```

Useful uninstall flags:

```bash
./uninstall_macos.sh --keep-config
./uninstall_macos.sh --remove-brew-deps
./uninstall_macos.sh --yes
```

`uninstall_macos.sh` removes the installed app, helper, LaunchAgent, logs, and config by default. It does not remove anything inside the cloned repository.

## How It Works

```text
PTT chord -> microphone -> transcription provider -> transcript -> focused app
```

- Audio is recorded as 16 kHz mono PCM and sent to the selected provider
- Microphone selection is re-evaluated at recording time, so preferred USB/KVM mics can recover when they come back
- macOS inserts text by typing it into the active app
- Linux inserts text with `xdotool` when available, falls back to `pynput`, and also updates the clipboard when a clipboard tool is available
- Installed app logs live at `~/.talktovibe/logs/app.log`

## Architecture

```text
talk_to_vibe/
  config/      - YAML config models, loader, wizard
  audio/       - microphone recording, WAV helpers
  providers/   - STT backends (groq, openai, openai_compatible, openrouter, local_whisper)
  providers/prompts/ - bundled transcription prompts and loader
  platforms/   - OS-specific behavior (macOS + Linux active, Windows stub)
  app.py       - terminal-mode app loop
  menubar.py   - macOS menu bar app
  tray.py      - Linux tray app
  cli.py       - CLI entry point and mode selection
  errors.py    - custom exceptions
tests/         - unit tests
```

## Config

Config is stored at `~/.talktovibe/config.yaml` with mode `600`.

```yaml
provider: openrouter
ptt_key: ctrl+9
auto_enter: false
prompt_file: ""
mic_preferences:
  - "TONOR TC30"
  - "NexiGo"

providers:
  groq:
    api_key: gsk_...
    model: whisper-large-v3-turbo
  openai:
    api_key: sk-...
    model: whisper-1
  openai_compatible:
    base_url: http://localhost:8000/v1
    api_key: ""
    model: whisper-1
  openrouter:
    api_key: sk-or-...
    model: google/gemini-3.1-flash-lite-preview
    base_url: https://openrouter.ai/api/v1/chat/completions
  local_whisper:
    model_size: large-v3-turbo
    device: auto
    compute_type: auto
    language: en
    cpu_threads: 0
    beam_size: 5
    vad_filter: true
```

Notes:

- `prompt_file` only affects the multimodal chat-completions provider path
- The provider named `openrouter` is really a configurable chat-completions + `input_audio` integration; OpenRouter is the default endpoint, not a hard requirement
- `mic_preferences` is a priority-ordered list of device-name substrings; the first available match wins
- `local_whisper.device` supports `auto`, `cuda`, and `cpu`
- `local_whisper.compute_type` supports `auto`, `float16`, `float32`, `int8`, `int8_float16`, `int8_float32`, and `int16`

## Running Tests

```bash
./run_ttv.sh --test
```

## License

MIT
