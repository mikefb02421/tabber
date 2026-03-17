import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib.layout import calculate_layout, LayoutError


def test_auto_mode_equal_widths():
    result = calculate_layout(30.0, 3, 'auto')
    assert result["tab_width_cm"] == result["notch_width_cm"]
    assert len([s for s in result["segments"] if s["type"] == "notch"]) == 4
    assert len([s for s in result["segments"] if s["type"] == "tab"]) == 3


def test_auto_mode_segment_width():
    result = calculate_layout(30.0, 3, 'auto')
    expected_width = 30.0 / 7  # 2*3+1 = 7 segments
    assert abs(result["tab_width_cm"] - expected_width) < 0.001


def test_manual_mode_notch_fills_remainder():
    result = calculate_layout(30.0, 3, 'manual', manual_tab_width_cm=2.0)
    total = sum(s["end_cm"] - s["start_cm"] for s in result["segments"])
    assert abs(total - 30.0) < 0.001


def test_manual_mode_tab_too_wide_raises():
    with pytest.raises(LayoutError):
        calculate_layout(10.0, 3, 'manual', manual_tab_width_cm=5.0)


def test_segments_are_contiguous():
    result = calculate_layout(20.0, 2, 'auto')
    segs = result["segments"]
    for i in range(len(segs) - 1):
        assert abs(segs[i]["end_cm"] - segs[i + 1]["start_cm"]) < 0.001


def test_always_starts_and_ends_with_notch():
    result = calculate_layout(20.0, 2, 'auto')
    assert result["segments"][0]["type"] == "notch"
    assert result["segments"][-1]["type"] == "notch"


def test_single_tab():
    result = calculate_layout(15.0, 1, 'auto')
    assert len(result["segments"]) == 3  # notch, tab, notch
    assert result["segments"][0]["type"] == "notch"
    assert result["segments"][1]["type"] == "tab"
    assert result["segments"][2]["type"] == "notch"


def test_segments_cover_full_length():
    result = calculate_layout(20.0, 2, 'auto')
    segs = result["segments"]
    assert abs(segs[0]["start_cm"]) < 0.001
    assert abs(segs[-1]["end_cm"] - 20.0) < 0.001


def test_manual_mode_correct_notch_width():
    result = calculate_layout(30.0, 3, 'manual', manual_tab_width_cm=3.0)
    # notch_width = (30 - 3*3) / 4 = 21/4 = 5.25
    assert abs(result["notch_width_cm"] - 5.25) < 0.001


def test_manual_mode_segments_centered():
    result = calculate_layout(30.0, 3, 'manual', manual_tab_width_cm=3.0)
    total = 4 * 5.25 + 3 * 3.0  # 21 + 9 = 30
    assert abs(total - 30.0) < 0.001
    segs = result["segments"]
    assert abs(segs[0]["start_cm"]) < 0.001
    assert abs(segs[-1]["end_cm"] - 30.0) < 0.001
