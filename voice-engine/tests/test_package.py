import importlib

# The "never imports the backend" boundary is enforced statically by import-linter (pyproject.toml).


def test_voice_engine_package_imports() -> None:
    module = importlib.import_module("ielts_voice")
    assert module.__version__ == "0.1.0"


def test_voice_engine_can_use_ai_engine_interfaces() -> None:
    from ielts_ai.providers import STTProvider, TTSProvider

    assert STTProvider.__name__ == "STTProvider"
    assert TTSProvider.__name__ == "TTSProvider"
