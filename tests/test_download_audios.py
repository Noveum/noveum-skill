import logging
import os
from pathlib import Path

from conftest import RecordingServer, load_script

downloader = load_script(
    "claude-skills/noveum-dataset/scripts/download_audios.py", "download_audios"
)
common = load_script("claude-skills/noveum-dataset/scripts/_common.py", "_common")

WAV_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 64
METADATA = b'{"id": "clip-1", "mimeType": "audio/wav", "url": "https://example.test/x"}'
LOG = logging.getLogger("test")


def serve(body: bytes, content_type: str):
    return RecordingServer(lambda path: (200, {"Content-Type": content_type}, body))


def download(server, uuid: str, out_dir: Path, overwrite: bool = False):
    downloader.BASE_URL = server.url
    return downloader.download_one(uuid, out_dir, common.auth_kwargs("secret-key"), LOG, overwrite)


def test_audio_bytes_are_saved_with_the_extension_their_header_shows(tmp_path):
    server = serve(WAV_BYTES, "audio/wav")
    try:
        assert download(server, "clip-1", tmp_path) == ("clip-1", None)
    finally:
        server.close()

    saved = tmp_path / "clip-1.wav"
    assert saved.read_bytes() == WAV_BYTES
    assert server.requests[0]["path"] == "/api/v1/audio/clip-1/serve"
    assert [p.name for p in tmp_path.iterdir()] == ["clip-1.wav"]


def test_a_metadata_reply_is_never_cached_as_a_wav_file(tmp_path):
    server = serve(METADATA, "application/json")
    try:
        uuid, error = download(server, "clip-1", tmp_path)
    finally:
        server.close()

    assert uuid == "clip-1"
    assert error is not None and "not audio" in error
    assert list(tmp_path.iterdir()) == []


def test_a_stale_metadata_file_is_not_treated_as_cached_audio(tmp_path):
    (tmp_path / "clip-1.wav").write_bytes(METADATA)
    server = serve(WAV_BYTES, "audio/wav")
    try:
        assert download(server, "clip-1", tmp_path) == ("clip-1", None)
    finally:
        server.close()

    assert len(server.requests) == 1
    assert (tmp_path / "clip-1.wav").read_bytes() == WAV_BYTES


def test_real_cached_audio_is_reused_without_a_request(tmp_path):
    (tmp_path / "clip-1.wav").write_bytes(WAV_BYTES)
    server = serve(WAV_BYTES, "audio/wav")
    try:
        assert download(server, "clip-1", tmp_path) == ("clip-1", None)
    finally:
        server.close()

    assert server.requests == []


def test_audio_ids_cannot_escape_the_output_folder(tmp_path):
    out_dir = tmp_path / "audio"
    server = serve(WAV_BYTES, "audio/wav")
    try:
        for uuid in ["../outside", "..", "a/b", "/etc/passwd", ".hidden", ""]:
            returned, error = download(server, uuid, out_dir)
            assert returned == uuid
            assert error is not None and "invalid audio id" in error
    finally:
        server.close()

    assert server.requests == []
    assert not (tmp_path / "outside.wav").exists()


def test_a_symlinked_target_is_refused_instead_of_written_through(tmp_path):
    out_dir = tmp_path / "audio"
    out_dir.mkdir()
    elsewhere = tmp_path / "elsewhere.wav"
    elsewhere.write_bytes(b"keep me")
    os.symlink(elsewhere, out_dir / "clip-1.wav")
    server = serve(WAV_BYTES, "audio/wav")
    try:
        uuid, error = download(server, "clip-1", out_dir, overwrite=True)
    finally:
        server.close()

    assert error is not None and "symlink" in error
    assert elsewhere.read_bytes() == b"keep me"
    assert server.requests == []
