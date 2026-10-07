import pytest
import yt_dlp
from conftest import sign_in

from app import extensions
from app.models.schemas import DownloadRequest
from app.services import downloader
from app.services.media_formats import select_video_format, video_options


def fmt(identity, **values):
    return {
        "format_id": identity,
        "url": "https://example.com/" + identity,
        "ext": "mp4",
        "protocol": "https",
        "vcodec": "avc1",
        "acodec": "none",
        "height": 1080,
        **values,
    }


def test_format_metadata_excludes_audio_drm_and_private_urls():
    result = video_options(
        {
            "duration": 10,
            "formats": [
                fmt("a", vcodec="none", acodec="aac"),
                fmt("drm", has_drm=True),
                fmt("images", vcodec="images"),
                fmt("v", fps=60, filesize=123456),
                fmt("v", fps=60),
                fmt("est", height=720, filesize_approx=98765),
                fmt("rate", height=480, tbr=1000),
                fmt("unknown", height=None),
            ],
        }
    )
    assert [r["format_id"] for r in result] == ["v", "est", "rate", "unknown"]
    assert result[0]["source_bytes"] == 123456
    assert result[0]["size_estimated"] is False
    assert result[1]["size_estimated"] is True
    assert result[2]["source_bytes"] == 1250000
    assert result[3]["source_bytes"] is None
    assert all("url" not in row for row in result)


def test_live_sizes_are_not_extrapolated_from_duration():
    assert (
        video_options({"is_live": True, "duration": 100, "formats": [fmt("v", tbr=1000)]})[0][
            "source_bytes"
        ]
        is None
    )


def test_selection_keeps_exact_fps_variant_and_adds_compatible_audio():
    low = fmt("30", fps=30)
    high = fmt("60", fps=60)
    aac = fmt("aac", height=None, ext="m4a", vcodec="none", acodec="aac")
    opus = fmt("opus", height=None, ext="webm", vcodec="none", acodec="opus")
    selected = list(select_video_format("30")({"formats": [aac, opus, low, high]}))[0]
    assert selected["requested_formats"] == [low, aac]
    assert selected["fps"] == 30
    assert selected["ext"] == "mp4"


def test_combined_source_does_not_add_duplicate_audio():
    muxed = fmt("mux", acodec="aac")
    assert list(select_video_format("mux")({"formats": [muxed]})) == [muxed]


def test_cross_container_audio_uses_mkv_intermediate():
    source = fmt("video")
    audio = fmt("audio", ext="webm", vcodec="none", acodec="opus")
    assert list(select_video_format("video")({"formats": [source, audio]}))[0]["ext"] == "mkv"


def test_missing_format_has_no_silent_fallback():
    with pytest.raises(downloader.DownloadError, match="no longer available"):
        list(select_video_format("missing")({"formats": [fmt("other")]}))


def test_id_is_literal_not_a_selector_expression():
    with pytest.raises(downloader.DownloadError):
        list(select_video_format("bestvideo+bestaudio/best")({"formats": [fmt("other")]}))


def test_current_ytdlp_accepts_custom_merged_selector():
    options = {"quiet": True, "format": select_video_format("chosen")}
    with yt_dlp.YoutubeDL(options) as ydl:
        result = ydl.process_ie_result(
            {
                "id": "fixture",
                "title": "Fixture",
                "formats": [
                    fmt("audio", ext="m4a", vcodec="none", acodec="aac", height=None),
                    fmt("chosen", fps=30),
                    fmt("other", fps=60),
                ],
            },
            download=False,
        )
    assert result["requested_formats"][0]["format_id"] == "chosen"
    assert result["requested_formats"][1]["format_id"] == "audio"


@pytest.mark.parametrize(
    "patch",
    [
        {"video_format_id": 123},
        {"video_format_id": "x" * 201},
        {"video_format_id": "137", "playlist_mode": "entire"},
        {"video_format_id": "137", "container": "mp3"},
        {"video_format_id": "137", "audio_only": True},
    ],
)
def test_invalid_format_requests_rejected(app, client, patch):
    headers = sign_in(app, client)
    response = client.post(
        "/api/download", json={"url": "https://example.com/v", **patch}, headers=headers
    )
    assert response.status_code == 400


def test_selected_id_reaches_queue(app, client, monkeypatch):
    headers = sign_in(app, client)
    monkeypatch.setattr(extensions.queue_manager._pending, "put", lambda task: None)
    monkeypatch.setattr(downloader, "ffmpeg_available", lambda: True)
    response = client.post(
        "/api/download",
        json={"url": "https://example.com/v", "video_format_id": "137"},
        headers=headers,
    )
    assert response.status_code == 201
    item = extensions.queue_manager.get(response.json["task_id"])
    assert item["options"]["video_format_id"] == "137"
    assert callable(
        downloader._format_selector(DownloadRequest(url=item["url"], video_format_id="137"))
    )
