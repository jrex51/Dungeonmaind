from app.base_models.timeline_models import TimelineSourceSegment
from app.functions.timeline.timeline_generator import _group_segments


def test_related_segments_are_combined_into_one_group():
    segments = [
        TimelineSourceSegment(
            text="You discover a locked chest.",
            speaker="DM",
            start_time=10.0,
            end_time=13.0,
        ),
        TimelineSourceSegment(
            text="I walk over to it.",
            speaker="Player",
            start_time=14.0,
            end_time=16.0,
        ),
        TimelineSourceSegment(
            text="I open the chest.",
            speaker="Player",
            start_time=17.0,
            end_time=19.0,
        ),
    ]

    groups = _group_segments(segments)

    assert len(groups) == 1
    assert len(groups[0]) == 3
    assert groups[0][0].text == "You discover a locked chest."
    assert groups[0][2].text == "I open the chest."


def test_large_gap_still_splits_groups():
    segments = [
        TimelineSourceSegment(
            text="You discover a locked chest.",
            speaker="DM",
            start_time=10.0,
            end_time=13.0,
        ),
        TimelineSourceSegment(
            text="I open the chest.",
            speaker="Player",
            start_time=50.0,
            end_time=53.0,
        ),
    ]

    groups = _group_segments(segments)

    assert len(groups) == 2

def test_llm_detector_includes_transcript_context(monkeypatch):
    import app.functions.timeline.timeline_generator as timeline_generator

    captured_prompt = {}

    class FakeResponse:
        def json(self):
            return {
                "message": {
                    "content": "1: EVENT"
                }
            }

    def fake_post(url, **kwargs):
        captured_prompt["prompt"] = (
            kwargs["json"]["messages"][0]["content"]
        )
        return FakeResponse()

    monkeypatch.setattr(
        "httpx.post",
        fake_post,
    )

    result = timeline_generator._llm_detect_events(
        ["I open it."],
        contexts=[
            (
                "You discover an ancient chest.",
                "I open it.",
                "Inside is a legendary sword.",
            )
        ],
    )

    assert result == [True]

    prompt = captured_prompt["prompt"]

    assert "You discover an ancient chest." in prompt
    assert "I open it." in prompt
    assert "Inside is a legendary sword." in prompt

    assert "PREVIOUS:" in prompt
    assert "CURRENT:" in prompt
    assert "FOLLOWING:" in prompt