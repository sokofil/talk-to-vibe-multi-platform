from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_setup_script_exists_and_mentions_talktovibe_app():
    path = REPO_ROOT / "setup_macos.sh"
    content = path.read_text()
    assert "TalkToVibe.app" in content
    assert "pyinstaller" in content.lower()
    assert "LaunchAgents" in content


def test_setup_script_supports_skip_signing_flag():
    path = REPO_ROOT / "setup_macos.sh"
    content = path.read_text()
    assert "--skip-signing" in content
    assert 'Skipping local codesigning' in content


def test_setup_script_uses_python_for_secret_generation():
    path = REPO_ROOT / "setup_macos.sh"
    content = path.read_text()
    assert "import secrets" in content
    assert "secrets.choice" in content


def test_uninstall_script_defaults_to_removing_config_unless_keep_flag():
    path = REPO_ROOT / "uninstall_macos.sh"
    content = path.read_text()
    assert "--keep-config" in content
    assert "rm -f \"$CONFIG_PATH\"" in content


def test_pyinstaller_specs_exist():
    app_spec = REPO_ROOT / "packaging" / "macos" / "talktovibe_app.spec"
    helper_spec = REPO_ROOT / "packaging" / "macos" / "talktovibe_configure.spec"
    assert app_spec.exists()
    assert helper_spec.exists()
