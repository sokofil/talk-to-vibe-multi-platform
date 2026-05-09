from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_setup_script_exists_and_mentions_talktovibe_app():
    content = (REPO_ROOT / "setup_macos.sh").read_text()
    assert "TalkToVibe.app" in content
    assert "pyinstaller" in content.lower()
    assert "LaunchAgents" in content


def test_setup_script_supports_skip_signing_flag():
    path = REPO_ROOT / "setup_macos.sh"
    content = path.read_text()
    assert "--skip-signing" in content
    assert 'Skipping local codesigning' in content


def test_setup_script_wizard_does_not_launch_app_loop():
    path = REPO_ROOT / "setup_macos.sh"
    content = path.read_text()
    assert '"$PYTHON_BIN" -m talk_to_vibe --setup' not in content
    assert "from talk_to_vibe.config.wizard import run_wizard" in content


def test_setup_script_strips_existing_signatures_before_resigning():
    path = REPO_ROOT / "setup_macos.sh"
    content = path.read_text()
    assert "codesign --remove-signature" in content
    assert "Freshly codesigning installed app" in content


def test_setup_script_uses_python_for_secret_generation():
    path = REPO_ROOT / "setup_macos.sh"
    content = path.read_text()
    assert "import secrets" in content
    assert "secrets.choice" in content


def test_uninstall_script_defaults_to_removing_config_unless_keep_flag():
    content = (REPO_ROOT / "uninstall_macos.sh").read_text()
    assert "--keep-config" in content
    assert "rm -f \"$CONFIG_PATH\"" in content


def test_pyinstaller_specs_exist():
    app_spec = REPO_ROOT / "packaging" / "macos" / "talktovibe_app.spec"
    helper_spec = REPO_ROOT / "packaging" / "macos" / "talktovibe_configure.spec"
    assert app_spec.exists()
    assert helper_spec.exists()
