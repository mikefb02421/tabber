import adsk.core
import adsk.fusion


def build_tab_sketch(component, face, layout, depth_cm, label="Tabber cuts"):
    """
    Create a sketch on `face` containing rectangles for each notch position
    in `layout`. Each rectangle represents one notch cut.

    Args:
        component: The Fusion component.
        face: The BRepFace to sketch on.
        layout: Dict from calculate_layout() with segments list.
        depth_cm: Height of the face (board thickness) in cm.
        label: Name for the sketch in the browser tree.

    Returns:
        The created Sketch object.
    """
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)

    # Register user parameters for tab and notch widths
    register_parameter(design, "tabber_tab_width", layout["tab_width_cm"])
    register_parameter(design, "tabber_notch_width", layout["notch_width_cm"])

    # Use addWithoutEdges to avoid auto-projecting face edges,
    # which would create extra profiles between our rectangles.
    try:
        sketch = component.sketches.addWithoutEdges(face)
    except AttributeError:
        sketch = component.sketches.add(face)
    sketch.name = label

    # Get face vertex positions in SKETCH space (not model space).
    # addTwoPointRectangle expects sketch-space coordinates.
    min_x = float('inf')
    min_y = float('inf')
    max_x = float('-inf')
    max_y = float('-inf')

    for vi in range(face.vertices.count):
        world_pt = face.vertices.item(vi).geometry
        sketch_pt = sketch.modelToSketchSpace(world_pt)
        min_x = min(min_x, sketch_pt.x)
        min_y = min(min_y, sketch_pt.y)
        max_x = max(max_x, sketch_pt.x)
        max_y = max(max_y, sketch_pt.y)

    sketch_width = max_x - min_x
    sketch_height = max_y - min_y

    # Length axis = the longer sketch dimension (tabs run along it).
    # Height axis = shorter dimension (board thickness).
    if sketch_width >= sketch_height:
        # X = length axis, Y = height axis
        for seg in layout["segments"]:
            if seg["type"] == "notch":
                x1 = min_x + seg["start_cm"]
                x2 = min_x + seg["end_cm"]
                y1 = min_y
                y2 = max_y
                sketch.sketchCurves.sketchLines.addTwoPointRectangle(
                    adsk.core.Point3D.create(x1, y1, 0),
                    adsk.core.Point3D.create(x2, y2, 0),
                )
    else:
        # Y = length axis, X = height axis
        for seg in layout["segments"]:
            if seg["type"] == "notch":
                y1 = min_y + seg["start_cm"]
                y2 = min_y + seg["end_cm"]
                x1 = min_x
                x2 = max_x
                sketch.sketchCurves.sketchLines.addTwoPointRectangle(
                    adsk.core.Point3D.create(x1, y1, 0),
                    adsk.core.Point3D.create(x2, y2, 0),
                )

    return sketch


def register_parameter(design, name, value_cm, units="cm"):
    """
    Register (or update) a user parameter in the design.
    If a parameter with `name` already exists, update its value.
    Returns the parameter.
    """
    params = design.userParameters
    existing = params.itemByName(name)
    if existing:
        existing.expression = f"{value_cm} cm"
        return existing
    else:
        param = params.add(
            name,
            adsk.core.ValueInput.createByReal(value_cm),
            units,
            f"Tabber: {name.replace('tabber_', '')}",
        )
        return param
