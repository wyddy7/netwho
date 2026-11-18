"""Voice messages go to Gemini on OpenRouter as the downloaded .ogg, no conversion."""
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
        raise RuntimeError("stt down")

    monkeypatch.setattr(ai_service, "transcribe_audio", boom)

    assert asyncio.run(onboarding.process_voice_input(_Message())) == ""
    assert seen and not os.path.exists(seen[0])


def _mock_llm(monkeypatch, replies):
    """Point the shared OpenAI client at a mock transport; replies are popped per request."""
    from openai import AsyncOpenAI
    requests = []

    def handler(request):
        requests.append(request)
        status, content = replies.pop(0)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "boom"}})
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
        })

    client = AsyncOpenAI(api_key="test-key", base_url="https://openrouter.test/api/v1", max_retries=0,
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(ai_service, "llm_client", client)
    return requests


def test_transcribe_audio_sends_ogg_as_input_audio(monkeypatch, tmp_path):
    """The .ogg goes base64 in an input_audio part, format ogg, to STT_MODEL."""
    import base64
    import json
    ogg = tmp_path / "voice_42_7.ogg"
    ogg.write_bytes(OGG_BYTES)
    requests = _mock_llm(monkeypatch, [(200, " привет ")])

    assert asyncio.run(ai_service.transcribe_audio(str(ogg))) == "привет"

    assert len(requests) == 1
    assert requests[0].url.path.endswith("/chat/completions")
    body = json.loads(requests[0].content)
    assert body["model"] == settings.STT_MODEL
    audio = [p for p in body["messages"][0]["content"] if p["type"] == "input_audio"][0]["input_audio"]
    assert audio["format"] == "ogg"
    assert base64.b64decode(audio["data"]) == OGG_BYTES


def test_transcribe_audio_falls_back_on_error_and_on_empty(monkeypatch, tmp_path):
    import json
    ogg = tmp_path / "v.ogg"
    ogg.write_bytes(OGG_BYTES)

    requests = _mock_llm(monkeypatch, [(500, None), (200, "запасная")])
    assert asyncio.run(ai_service.transcribe_audio(str(ogg))) == "запасная"
    assert [json.loads(r.content)["model"] for r in requests] == [settings.STT_MODEL, settings.STT_FALLBACK_MODEL]

    _mock_llm(monkeypatch, [(200, ""), (200, "  ")])
    assert asyncio.run(ai_service.transcribe_audio(str(ogg))) == ""


def test_transcribe_audio_missing_file_returns_empty(tmp_path):
    assert asyncio.run(ai_service.transcribe_audio(str(tmp_path / "nope.ogg"))) == ""
