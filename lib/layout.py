class LayoutError(Exception):
    """Raised when tab dimensions don't fit the face."""
    pass


def calculate_layout(face_length_cm, tab_count, width_mode, manual_tab_width_cm=None):
    """
    Calculate tab and notch positions along the face length.

    Pattern: notch, tab, notch, tab, ..., notch
    Always starts and ends with a notch.
    Tab count = N -> notch count = N + 1.
    The entire pattern is centered on the face.

    Width modes:
    - 'auto':   tab_width = notch_width = face_length / (2N + 1)
    - 'manual': tab_width = manual_tab_width_cm (user supplied)
                notch_width = (face_length - N * tab_width) / (N + 1)

    Returns dict with tab_width_cm, notch_width_cm, and segments list.
    All positions measured from the left edge of the face (x=0).
    """
    N = tab_count
    M = N + 1  # number of notches
    L = face_length_cm

    if width_mode == 'auto':
        segment_width = L / (2 * N + 1)
        tab_w = segment_width
        notch_w = segment_width
    elif width_mode == 'manual':
        tab_w = manual_tab_width_cm
        notch_w = (L - N * tab_w) / M
        if notch_w <= 0:
            raise LayoutError(
                f"Tab width {tab_w * 10:.1f}mm is too large for face length "
                f"{L * 10:.1f}mm with {N} tabs. "
                f"Notch width would be {notch_w * 10:.1f}mm."
            )
    else:
        raise ValueError(f"Unknown width_mode: {width_mode!r}")

    total_w = M * notch_w + N * tab_w
    offset = (L - total_w) / 2

    segments = []
    x = offset
    for i in range(M + N):
        if i % 2 == 0:
            segments.append({"type": "notch", "start_cm": x, "end_cm": x + notch_w})
            x += notch_w
        else:
            segments.append({"type": "tab", "start_cm": x, "end_cm": x + tab_w})
            x += tab_w

    return {
        "tab_width_cm": tab_w,
        "notch_width_cm": notch_w,
        "segments": segments,
    }
