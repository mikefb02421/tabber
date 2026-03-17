import adsk.core
import adsk.fusion

from . import sketch_builder


def build_cuts(component, face, sketch, depth_cm):
    """
    For each closed profile in `sketch`, create an extrude-cut feature
    that cuts into the body to `depth_cm`.

    Returns list of created ExtrudeFeature objects.
    """
    features = []
    extrudes = component.features.extrudeFeatures

    body = face.body

    profile_count = sketch.profiles.count
    if profile_count == 0:
        raise RuntimeError(
            f"Tabber: sketch '{sketch.name}' has no profiles. "
            f"Cannot create cuts."
        )

    for pi in range(profile_count):
        profile = sketch.profiles.item(pi)

        ext_input = extrudes.createInput(
            profile,
            adsk.fusion.FeatureOperations.CutFeatureOperation,
        )
        # Face normal points outward; negative depth cuts into the body.
        distance = adsk.core.ValueInput.createByReal(-depth_cm)
        ext_input.setDistanceExtent(False, distance)
        feature = extrudes.add(ext_input)
        features.append(feature)

    return features


def build_mirror_cuts(component, primary_face, opposite_face, primary_layout, depth_cm,
                      primary_sketch=None):
    """
    Build the interlocking mirror cuts on the opposite face.

    Maps positions through model space so axis flips between the two
    faces' sketch coordinate systems are handled automatically.
    """
    mirror_component = opposite_face.body.parentComponent

    # Use the existing primary sketch (the face may be invalid after cuts)
    pri_sketch = primary_sketch

    # Get primary sketch bounds from its own geometry
    # (the face entity may be invalid after cuts modified the body)
    pri_min_x, pri_max_x = float('inf'), float('-inf')
    pri_min_y, pri_max_y = float('inf'), float('-inf')
    lines = pri_sketch.sketchCurves.sketchLines
    for i in range(lines.count):
        line = lines.item(i)
        for pt in [line.startSketchPoint.geometry, line.endSketchPoint.geometry]:
            pri_min_x = min(pri_min_x, pt.x)
            pri_max_x = max(pri_max_x, pt.x)
            pri_min_y = min(pri_min_y, pt.y)
            pri_max_y = max(pri_max_y, pt.y)

    pri_width = pri_max_x - pri_min_x
    pri_height = pri_max_y - pri_min_y
    pri_length_is_x = (pri_width >= pri_height)

    # Create sketch on opposite face
    try:
        opp_sketch = mirror_component.sketches.addWithoutEdges(opposite_face)
    except AttributeError:
        opp_sketch = mirror_component.sketches.add(opposite_face)
    opp_sketch.name = "Tabber mirror cuts"

    # For each primary TAB segment (becomes a notch/cut on opposite face),
    # map its corners: primary sketch space → model space → opposite sketch space
    for seg in primary_layout["segments"]:
        if seg["type"] != "tab":
            continue

        if pri_length_is_x:
            sx1, sy1 = pri_min_x + seg["start_cm"], pri_min_y
            sx2, sy2 = pri_min_x + seg["end_cm"], pri_max_y
        else:
            sx1, sy1 = pri_min_x, pri_min_y + seg["start_cm"]
            sx2, sy2 = pri_max_x, pri_min_y + seg["end_cm"]

        # Primary sketch → model → opposite sketch
        m1 = pri_sketch.sketchToModelSpace(adsk.core.Point3D.create(sx1, sy1, 0))
        m2 = pri_sketch.sketchToModelSpace(adsk.core.Point3D.create(sx2, sy2, 0))
        o1 = opp_sketch.modelToSketchSpace(m1)
        o2 = opp_sketch.modelToSketchSpace(m2)

        # Use min/max to handle any axis flips
        opp_sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(min(o1.x, o2.x), min(o1.y, o2.y), 0),
            adsk.core.Point3D.create(max(o1.x, o2.x), max(o1.y, o2.y), 0),
        )

    return build_cuts(mirror_component, opposite_face, opp_sketch, depth_cm)
