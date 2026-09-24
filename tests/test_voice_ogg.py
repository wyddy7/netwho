"""Voice messages go to Groq Whisper as the downloaded .ogg — no conversion."""
import asyncio
import os
from types import SimpleNamespace

import httpx

# The service modules construct Settings at import time. Keep this offline
# test runnable without a developer or production .env file.
os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

from app.handlers import onboarding, voice  # noqa: E402
from app.services import audio_service  # noqa: E402
from app.services.ai_service import ai_service, settings  # noqa: E402
from app.services.user_service import user_service  # noqa: E402

OGG_BYTES = b"OggS\x00fake-opus-payload"


class _StatusMsg:
    async def edit_text(self, *_args, **_kwargs):
        pass

    async def delete(self):
        pass


class _Bot:
    async def get_file(self, file_id):
        return SimpleNamespace(file_path=f"voice/{file_id}.oga")

    async def download_file(self, _file_path, destination):
        with open(destination, "wb") as f:
            f.write(OGG_BYTES)


class _Message:
    def __init__(self):
        self.from_user = SimpleNamespace(id=42)
        self.message_id = 7
        self.voice = SimpleNamespace(file_id="abc", duration=5)
        self.bot = _Bot()
        self.chat = SimpleNamespace(id=42)

    async def answer(self, *_args, **_kwargs):
        return _StatusMsg()


def _capture_transcribe(monkeypatch, sent):
    """Replace transcribe_audio with a fake that records what it was given."""
    async def fake_transcribe(file_path):
        with open(file_path, "rb") as f:
            sent.append((file_path, f.read()))
        return ""  # empty transcript: handlers stop before the LLM

    monkeypatch.setattr(ai_service, "transcribe_audio", fake_transcribe)


def test_ffmpeg_conversion_is_gone():
    assert not hasattr(audio_service.AudioService, "convert_ogg_to_mp3")


def test_voice_handler_sends_downloaded_ogg_and_cleans_up(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    sent = []
    _capture_transcribe(monkeypatch, sent)

    async def is_pro(_user_id):
        return True

    monkeypatch.setattr(user_service, "is_pro", is_pro)

    asyncio.run(voice.handle_voice(_Message()))

    assert len(sent) == 1
    path, data = sent[0]
    assert path.endswith(".ogg")
    assert data == OGG_BYTES
    assert not os.path.exists(path), "temp .ogg must be deleted"


def test_onboarding_voice_sends_downloaded_ogg_and_cleans_up(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    sent = []
    _capture_transcribe(monkeypatch, sent)

    assert asyncio.run(onboarding.process_voice_input(_Message())) == ""

    assert len(sent) == 1
    path, data = sent[0]
    assert path.endswith(".ogg")
    assert data == OGG_BYTES
    assert not os.path.exists(path), "temp .ogg must be deleted"


def test_temp_ogg_cleaned_up_when_transcription_fails(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    seen = []

    async def boom(file_path):
        seen.append(file_path)
        raise RuntimeError("groq down")

    monkeypatch.setattr(ai_service, "transcribe_audio", boom)

    assert asyncio.run(onboarding.process_voice_input(_Message())) == ""
    assert seen and not os.path.exists(seen[0])


def test_transcribe_audio_uploads_ogg_file_to_groq(monkeypatch, tmp_path):
    """The real Groq SDK uploads the .ogg as-is: filename, bytes and model."""
    ogg = tmp_path / "voice_42_7.ogg"
    ogg.write_bytes(OGG_BYTES)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"text": "привет"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ai_service, "http_client", client)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")

    assert asyncio.run(ai_service.transcribe_audio(str(ogg))) == "привет"

    assert len(requests) == 1
    request = requests[0]
    assert request.url.path.endswith("/audio/transcriptions")
    body = request.content
    assert b'filename="voice_42_7.ogg"' in body
    assert OGG_BYTES in body
    assert b"whisper-large-v3" in body
