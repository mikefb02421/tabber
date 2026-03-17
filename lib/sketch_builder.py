import adsk.core
import adsk.fusion


def build_tab_sketch(component, face, layout, depth_cm, label="Tabber cuts",
                     width_mode='auto', tab_count=3, manual_tab_width_cm=None):
    """
    Create a fully parametric sketch on `face` with notch rectangles tied to
    projected face edges via constraints and parameter expressions.

    Returns:
        (sketch, suffix) — the Sketch object and the parameter suffix string
        used for this run's parameters.
    """
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)

    suffix = _get_param_suffix(design)

    # --- Create sketch without auto-projected edges ---
    try:
        sketch = component.sketches.addWithoutEdges(face)
    except AttributeError:
        sketch = component.sketches.add(face)
    sketch.name = label

    # --- Project face edges as construction lines ---
    projected_lines = []
    for i in range(face.edges.count):
        edge = face.edges.item(i)
        projected = sketch.project(edge)
        for j in range(projected.count):
            item = projected.item(j)
            item.isConstruction = True
            if hasattr(item, 'startSketchPoint'):
                projected_lines.append(item)

    # --- Identify projected edge roles (left/right/top/bottom) ---
    proj = _identify_projected_edges(projected_lines)

    # --- Determine face orientation in sketch space ---
    sketch_width = proj['right_x'] - proj['left_x']
    sketch_height = proj['top_y'] - proj['bottom_y']
    length_is_x = (sketch_width >= sketch_height)

    if length_is_x:
        length_dim_val = sketch_width
        height_dim_val = sketch_height
    else:
        length_dim_val = sketch_height
        height_dim_val = sketch_width

    dims = sketch.sketchDimensions

    # --- Try to add driven dimensions for parametric face-length tracking ---
    length_dim_param = None
    height_dim_param = None
    try:
        if length_is_x:
            length_dim = dims.addDistanceDimension(
                proj['bottom_left_pt'], proj['bottom_right_pt'],
                adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation,
                _midpoint_3d(proj['bottom_left_pt'].geometry, proj['bottom_right_pt'].geometry, dy=-1.0),
                False,
            )
            height_dim = dims.addDistanceDimension(
                proj['bottom_left_pt'], proj['top_left_pt'],
                adsk.fusion.DimensionOrientations.VerticalDimensionOrientation,
                _midpoint_3d(proj['bottom_left_pt'].geometry, proj['top_left_pt'].geometry, dx=-1.0),
                False,
            )
        else:
            length_dim = dims.addDistanceDimension(
                proj['bottom_left_pt'], proj['top_left_pt'],
                adsk.fusion.DimensionOrientations.VerticalDimensionOrientation,
                _midpoint_3d(proj['bottom_left_pt'].geometry, proj['top_left_pt'].geometry, dx=-1.0),
                False,
            )
            height_dim = dims.addDistanceDimension(
                proj['bottom_left_pt'], proj['bottom_right_pt'],
                adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation,
                _midpoint_3d(proj['bottom_left_pt'].geometry, proj['bottom_right_pt'].geometry, dy=-1.0),
                False,
            )
        length_dim_param = length_dim.parameter.name
        height_dim_param = height_dim.parameter.name
    except Exception:
        pass

    # --- Register user parameters ---
    N = tab_count
    fl_name = f"tabber_face_length{suffix}"
    cd_name = f"tabber_cut_depth{suffix}"
    tc_name = f"tabber_tab_count{suffix}"
    nw_name = f"tabber_notch_width{suffix}"
    tw_name = f"tabber_tab_width{suffix}"

    # Link to driven dimension if available, otherwise use measured value
    register_parameter(design, fl_name, length_dim_val,
                       expression=length_dim_param)
    register_parameter(design, cd_name, height_dim_val,
                       expression=height_dim_param)

    # tabber_tab_count = integer (stored as unitless real)
    register_parameter(design, tc_name, float(N), units="",
                       comment="Tabber: tab count")

    # tabber_tab_width and tabber_notch_width with mode-dependent expressions
    if width_mode == 'auto':
        # notch_width = face_length / (2 * tab_count + 1)
        nw_expr = f"{fl_name} / (2 * {tc_name} + 1)"
        register_parameter(design, nw_name, layout["notch_width_cm"],
                           expression=nw_expr)
        # tab_width = notch_width (equal in auto mode)
        register_parameter(design, tw_name, layout["tab_width_cm"],
                           expression=nw_name)
    else:
        # manual: tab_width is the user-specified value
        register_parameter(design, tw_name, manual_tab_width_cm or layout["tab_width_cm"])
        # notch_width = (face_length - tab_count * tab_width) / (tab_count + 1)
        nw_expr = f"({fl_name} - {tc_name} * {tw_name}) / ({tc_name} + 1)"
        register_parameter(design, nw_name, layout["notch_width_cm"],
                           expression=nw_expr)

    # --- Create notch rectangles at initial positions ---
    notch_segments = [s for s in layout["segments"] if s["type"] == "notch"]
    lines_coll = sketch.sketchCurves.sketchLines
    constraints = sketch.geometricConstraints

    # Face bounds in sketch space
    min_x = proj['left_x']
    min_y = proj['bottom_y']
    max_x = proj['right_x']
    max_y = proj['top_y']

    rect_infos = []
    for seg in notch_segments:
        if length_is_x:
            x1 = min_x + seg["start_cm"]
            x2 = min_x + seg["end_cm"]
            y1 = min_y
            y2 = max_y
        else:
            x1 = min_x
            x2 = max_x
            y1 = min_y + seg["start_cm"]
            y2 = min_y + seg["end_cm"]

        rect_lines = lines_coll.addTwoPointRectangle(
            adsk.core.Point3D.create(x1, y1, 0),
            adsk.core.Point3D.create(x2, y2, 0),
        )
        info = _identify_rect_edges(rect_lines, length_is_x)
        rect_infos.append(info)

    # --- Apply geometric constraints ---
    for i, info in enumerate(rect_infos):
        # Perpendicular: lock rectangle corners to right angles
        try:
            constraints.addPerpendicular(info['left_line'], info['bottom_line'])
        except Exception:
            pass
        try:
            constraints.addPerpendicular(info['right_line'], info['top_line'])
        except Exception:
            pass

        # Collinear: rectangle top line with projected top edge
        try:
            constraints.addCollinear(info['top_line'], proj['top_line'])
        except Exception:
            pass

        # Collinear: rectangle bottom line with projected bottom edge
        try:
            constraints.addCollinear(info['bottom_line'], proj['bottom_line'])
        except Exception:
            pass

    # Anchor first rectangle's leading edge to projected leading edge
    if rect_infos:
        leading_line = rect_infos[0]['left_line'] if length_is_x else rect_infos[0]['bottom_line']
        proj_leading = proj['left_line'] if length_is_x else proj['bottom_line']
        try:
            constraints.addCollinear(leading_line, proj_leading)
        except Exception:
            pass

    # --- Apply dimensional constraints with parameter expressions ---
    if length_is_x:
        dim_orient = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
    else:
        dim_orient = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation

    for i, info in enumerate(rect_infos):
        # Width dimension for each notch rectangle
        if length_is_x:
            p1 = info['left_line'].startSketchPoint
            p2 = info['right_line'].startSketchPoint
            text_pos = _midpoint_3d(p1.geometry, p2.geometry, dy=0.5)
        else:
            p1 = info['bottom_line'].startSketchPoint
            p2 = info['top_line'].startSketchPoint
            text_pos = _midpoint_3d(p1.geometry, p2.geometry, dx=0.5)

        try:
            width_dim = dims.addDistanceDimension(p1, p2, dim_orient, text_pos)
            width_dim.parameter.expression = nw_name
        except Exception:
            pass

        # Gap dimension between this rectangle and the next (= tab width)
        if i < len(rect_infos) - 1:
            next_info = rect_infos[i + 1]
            if length_is_x:
                gap_p1 = info['right_line'].startSketchPoint
                gap_p2 = next_info['left_line'].startSketchPoint
                text_pos = _midpoint_3d(gap_p1.geometry, gap_p2.geometry, dy=-0.5)
            else:
                gap_p1 = info['top_line'].startSketchPoint
                gap_p2 = next_info['bottom_line'].startSketchPoint
                text_pos = _midpoint_3d(gap_p1.geometry, gap_p2.geometry, dx=-0.5)

            try:
                gap_dim = dims.addDistanceDimension(gap_p1, gap_p2, dim_orient, text_pos)
                gap_dim.parameter.expression = tw_name
            except Exception:
                pass

    return sketch, suffix


def register_parameter(design, name, value_cm, units="cm", expression=None,
                       comment=None):
    """
    Register (or update) a user parameter in the design.
    If `expression` is provided, set the parameter's expression to it.
    Returns the parameter.
    """
    params = design.userParameters
    existing = params.itemByName(name)

    if existing:
        if expression:
            existing.expression = expression
        else:
            existing.expression = f"{value_cm} {units}" if units else str(value_cm)
        return existing
    else:
        param = params.add(
            name,
            adsk.core.ValueInput.createByReal(value_cm),
            units,
            comment or f"Tabber: {name.replace('tabber_', '')}",
        )
        if expression:
            param.expression = expression
        return param


def _get_param_suffix(design):
    """
    Determine the next available suffix for tabber parameters.
    First run uses "", second uses "_2", third "_3", etc.
    """
    params = design.userParameters
    # Check for existing tabber_face_length parameters
    if not params.itemByName("tabber_face_length"):
        return ""

    n = 2
    while True:
        if not params.itemByName(f"tabber_face_length_{n}"):
            return f"_{n}"
        n += 1


def _identify_projected_edges(projected_lines):
    """
    Sort projected construction lines into left/right/top/bottom based on
    sketch-space position. Returns dict with edge lines and corner points.
    """
    if not projected_lines:
        raise RuntimeError("Tabber: no projected lines found on face.")

    # Collect all endpoints to find bounding box
    all_pts = []
    for line in projected_lines:
        all_pts.append(line.startSketchPoint.geometry)
        all_pts.append(line.endSketchPoint.geometry)

    xs = [p.x for p in all_pts]
    ys = [p.y for p in all_pts]
    left_x = min(xs)
    right_x = max(xs)
    bottom_y = min(ys)
    top_y = max(ys)
    mid_x = (left_x + right_x) / 2
    mid_y = (bottom_y + top_y) / 2

    tol = 0.001  # tolerance for edge classification

    # Classify each line
    left_line = None
    right_line = None
    top_line = None
    bottom_line = None

    for line in projected_lines:
        sp = line.startSketchPoint.geometry
        ep = line.endSketchPoint.geometry
        mx = (sp.x + ep.x) / 2
        my = (sp.y + ep.y) / 2

        # Check if line is roughly vertical (small x-spread, large y-spread)
        dx = abs(sp.x - ep.x)
        dy = abs(sp.y - ep.y)

        if dx < dy:
            # Vertical line — left or right
            if mx < mid_x:
                left_line = line
            else:
                right_line = line
        else:
            # Horizontal line — top or bottom
            if my < mid_y:
                bottom_line = line
            else:
                top_line = line

    if not all([left_line, right_line, top_line, bottom_line]):
        raise RuntimeError(
            "Tabber: could not identify all four projected edges. "
            f"Found: left={left_line is not None}, right={right_line is not None}, "
            f"top={top_line is not None}, bottom={bottom_line is not None}"
        )

    # Find corner SketchPoints
    bottom_left_pt = _get_corner_point(bottom_line, left_line)
    bottom_right_pt = _get_corner_point(bottom_line, right_line)
    top_left_pt = _get_corner_point(top_line, left_line)
    top_right_pt = _get_corner_point(top_line, right_line)

    return {
        'left_line': left_line,
        'right_line': right_line,
        'top_line': top_line,
        'bottom_line': bottom_line,
        'left_x': left_x,
        'right_x': right_x,
        'top_y': top_y,
        'bottom_y': bottom_y,
        'bottom_left_pt': bottom_left_pt,
        'bottom_right_pt': bottom_right_pt,
        'top_left_pt': top_left_pt,
        'top_right_pt': top_right_pt,
    }


def _get_corner_point(line1, line2):
    """
    Find the SketchPoint shared (or closest) between two connected sketch lines.
    """
    pts1 = [line1.startSketchPoint, line1.endSketchPoint]
    pts2 = [line2.startSketchPoint, line2.endSketchPoint]

    # Try exact match first (same SketchPoint object)
    for p1 in pts1:
        for p2 in pts2:
            if p1 == p2:
                return p1

    # Fall back to closest point by distance
    best = None
    best_dist = float('inf')
    for p1 in pts1:
        for p2 in pts2:
            d = p1.geometry.distanceTo(p2.geometry)
            if d < best_dist:
                best_dist = d
                best = p1
    return best


def _identify_rect_edges(rect_lines, length_is_x):
    """
    Given the 4 SketchLines from addTwoPointRectangle, identify which is
    top, bottom, left, and right.

    Returns dict with top_line, bottom_line, left_line, right_line.
    """
    lines = []
    for i in range(rect_lines.count):
        lines.append(rect_lines.item(i))

    # Classify by midpoint position
    horizontal = []
    vertical = []
    for line in lines:
        sp = line.startSketchPoint.geometry
        ep = line.endSketchPoint.geometry
        dx = abs(sp.x - ep.x)
        dy = abs(sp.y - ep.y)
        if dx >= dy:
            horizontal.append(line)
        else:
            vertical.append(line)

    # Sort horizontal lines by Y midpoint
    horizontal.sort(key=lambda l: (l.startSketchPoint.geometry.y + l.endSketchPoint.geometry.y) / 2)
    # Sort vertical lines by X midpoint
    vertical.sort(key=lambda l: (l.startSketchPoint.geometry.x + l.endSketchPoint.geometry.x) / 2)

    if len(horizontal) >= 2 and len(vertical) >= 2:
        bottom_line = horizontal[0]
        top_line = horizontal[1]
        left_line = vertical[0]
        right_line = vertical[1]
    else:
        # Fallback: treat first two as one pair, second two as the other
        bottom_line = lines[0]
        right_line = lines[1]
        top_line = lines[2]
        left_line = lines[3]

    return {
        'top_line': top_line,
        'bottom_line': bottom_line,
        'left_line': left_line,
        'right_line': right_line,
    }


def _midpoint_3d(p1, p2, dx=0.0, dy=0.0):
    """Return a Point3D at the midpoint of p1 and p2, offset by dx/dy."""
    return adsk.core.Point3D.create(
        (p1.x + p2.x) / 2 + dx,
        (p1.y + p2.y) / 2 + dy,
        0,
    )
