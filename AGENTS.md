# AGENTS.md — Talk to Vibe

## Project Overview

Push-to-talk speech-to-text tool. Hold a key, speak, release — text is auto-pasted into the active app.

## Architecture

```
talk_to_vibe/
  config/      — YAML config models, loader, wizard
  audio/       — microphone recording, WAV helpers
  providers/   — STT backends (groq, openai, openai_compatible, openrouter)
  providers/prompts/ — Bundled .md prompt files and loader (transcription.md)
  platforms/   — OS-specific behavior (macOS active, Linux/Windows stubs)
  app.py       — main app loop (terminal mode)
  menubar.py   — rumps menu bar app (macOS default)
  cli.py       — argument parsing and entry point wiring
  errors.py    — custom exceptions
```

## Provider Types

There are two distinct provider types in this codebase. They use different API shapes and must not be conflated.

### Whisper Transcription Providers

- **Providers**: `groq`, `openai`, `openai_compatible`
- **API**: OpenAI `/audio/transcriptions` endpoint
- **Input**: WAV file upload
- **Output**: Structured transcription response with `.text`
- **SDK**: Uses the `openai` or `groq` Python SDK's `client.audio.transcriptions.create()` method
- **When to use**: Pure speech-to-text dictation. Simplest, most reliable for transcription.

### Multimodal Chat Providers

- **Providers**: `openrouter`
- **API**: OpenAI `/chat/completions` endpoint with `input_audio` content type
- **Input**: Base64-encoded WAV in a chat message
- **Output**: Chat completion response — transcript extracted from `choices[0].message.content`
- **Transport**: Direct `httpx` POST (not the OpenAI SDK transcription client)
- **When to use**: When you want to use a multimodal model (Gemini, GPT-4o, etc.) that accepts audio natively. More flexible but requires a transcription prompt and response parsing.

### Adding a New Provider

1. Determine which type it is — Whisper or Multimodal.
2. Create a new file in `providers/` following the pattern of the matching type.
3. Implement `transcribe(audio_data: numpy.ndarray) -> str`.
4. Set `provider_name` and `model` on the class.
5. Register it in `providers/factory.py`.
6. Add config fields in `config/models.py`.
7. Add wizard support in `config/wizard.py`.
8. Write unit tests for request payload building and response parsing.

## Testing Mandate

- **Every** bug fix, refactor, or new feature must include unit tests.
- No provider code ships without request/response parsing tests.
- Run `./run_ttv.sh --test` before considering any change complete.
- Mock all I/O boundaries: network, microphone, clipboard, OS commands.
- Document any intentionally untested hardware or OS boundaries in code comments.

## Running Tests

```bash
./run_ttv.sh --test
```

## Code Style

- Python 3.10+
- No comments unless asked
- Small functions, clear names
- Keep OS-specific logic behind platform adapters in `platforms/`
- All provider config (models, base URLs, API keys) belongs in `~/.talktovibe/config.yaml` — never hardcode in Python

## Key Conventions

- Config file: `~/.talktovibe/config.yaml` — YAML only, no JSON
- All providers implement `transcribe(audio_data: numpy.ndarray) -> str`
- All providers set `provider_name: str` and `model: str` attributes
- Platform adapters implement `paste_text`, `play_success_sound`, `get_key_map`, `parse_ptt_chord`, `get_chord_display_name`, `is_modifier_only`
- Launch the app with `./run_ttv.sh` (menu bar mode on macOS, terminal mode with `--terminal`)
- Transcription prompts live in `providers/prompts/` as `.md` files — `load_prompt(name)` loads a bundled prompt, `load_custom_prompt(path)` loads a user-supplied one
- `prompt_file` config field overrides the bundled transcription prompt with a custom `.md` file path; empty string means use the bundled prompt
