# CLAUDE.md — Tabber: Fusion 360 Finger Joint Add-In

## Project overview

A Fusion 360 Python add-in that generates finger-joint (box joint) tabs on
plywood box faces. The user selects a face, configures tab count and width mode,
and the add-in cuts the tab/notch geometry directly into the body using
parametric sketches and extrude-cut features.

---

## Repository layout

```
tabber/
├── CLAUDE.md                        # ← this file
├── tabber.py                        # Add-in entry point
├── tabber.manifest                  # Fusion add-in manifest
├── config.py                        # Constants and defaults
│
├── commands/
│   └── GenerateTabs/
│       ├── GenerateTabs.py          # Command definition, button registration,
│       │                            # and all event handlers
│       └── __init__.py
│
├── lib/
│   ├── geometry.py                  # Face analysis: dimensions, opposite face detection
│   ├── layout.py                    # Tab/notch math: positions, widths, counts
│   ├── sketch_builder.py            # Parametric sketch creation
│   ├── cut_builder.py               # Extrude-cut feature creation
│   └── __init__.py
│
└── tests/
    ├── test_layout.py               # Unit tests for tab math (no Fusion needed)
    └── __init__.py
```

---

## Core concepts

### What a finger joint is

A finger joint on a plywood face looks like this along the face length:

```
[notch][tab][notch][tab][notch]
```

- Notches on both ends, always.
- N tabs → N+1 notches.
- Tabs and notches are centered on the face as a group.
- Tab depth = height of the selected face (= board thickness).

### The two faces

When a user selects a face on a plywood box:

```
         Face Length (L)
    ←──────────────────────→
    ┌──────────────────────┐  ↑
    │                      │  │ Face Height (H) = board thickness = tab depth
    │    Selected Face     │  │
    │                      │  │
    └──────────────────────┘  ↓
```

The tabs run along the LENGTH. Each tab/notch is cut to the full HEIGHT.

### Dual mode — interlocking

In Dual mode the opposite face gets a mirror-image cut — where this face has
notches, the opposite face has tabs, and vice versa. This is what makes the
joints interlock.

---

## Module contracts

### config.py

```python
import logging

class Config:
    # Logging
    LOG_FILE  = 'tabber.log'
    LOG_LEVEL = logging.NOTSET

    # Defaults shown in dialog
    DEFAULT_TAB_COUNT    = 3       # number of tabs (not notches)
    DEFAULT_WIDTH_MODE   = 'auto'  # 'auto' or 'manual'
    DEFAULT_MANUAL_WIDTH = 8.0     # mm, used when width mode = manual
    DEFAULT_PLACEMENT    = 'dual'  # 'single' or 'dual'

    def __init__(self, app):
        self.app    = app
        self.ui     = app.userInterface
        self.design = app.activeProduct
```

### lib/geometry.py

```python
def get_face_dimensions(face) -> dict:
    """
    Return the length and height of a rectangular planar face.

    Returns:
        {
            "length_cm": float,   # longer dimension
            "height_cm": float,   # shorter dimension (= board thickness)
            "length_param": str,  # Fusion parameter name for length (if available)
            "height_param": str,  # Fusion parameter name for height (if available)
        }

    Implementation notes:
    - Use face.boundingBox to get dimensions.
    - Fusion units are cm. Return cm, convert to mm only at display time.
    - length = the axis along which tabs run (longer edge of face).
    - height = the axis perpendicular to the tab cuts (board thickness).
    """

def find_opposite_face(face, component) -> "adsk.fusion.BRepFace | None":
    """
    Find the face that is parallel to `face`, equal in size, and on the
    opposite side of the body.

    Returns None if no such face exists. Never raises — caller handles
    the None case by showing a warning, not an error.

    Implementation notes:
    - Get the face normal via face.evaluator.getNormalAtPoint().
    - The opposite face normal will be antiparallel (dot product ≈ -1.0).
    - Check that bounding box dimensions match within TOLERANCE_CM.
    - If multiple candidates exist, return the one farthest away along
      the normal axis.
    """

TOLERANCE_CM = 0.01   # 0.1mm — faces must match within this to be "equal size"
```

### lib/layout.py

```python
def calculate_layout(
    face_length_cm: float,
    tab_count: int,
    width_mode: str,          # 'auto' or 'manual'
    manual_tab_width_cm: float = None,
) -> dict:
    """
    Calculate tab and notch positions along the face length.

    Pattern: notch, tab, notch, tab, ..., notch
    Always starts and ends with a notch.
    Tab count = N → notch count = N + 1.
    The entire pattern is centered on the face.

    Width modes:
    - 'auto':   tab_width = notch_width = face_length / (2N + 1)
                All tabs and notches are equal width.
    - 'manual': tab_width = manual_tab_width_cm (user supplied)
                notch_width = (face_length - N * tab_width) / (N + 1)
                Notches absorb the remaining space equally.
                If notch_width <= 0, raise LayoutError.

    Returns:
        {
            "tab_width_cm":   float,
            "notch_width_cm": float,
            "segments": [
                {"type": "notch", "start_cm": float, "end_cm": float},
                {"type": "tab",   "start_cm": float, "end_cm": float},
                ...
            ]
        }

    All positions are measured from the left edge of the face (x=0).
    Segments are in order from left to right.
    """

class LayoutError(Exception):
    """Raised when tab dimensions don't fit the face."""
    pass
```

### lib/sketch_builder.py

```python
def build_tab_sketch(
    component,
    face,
    layout: dict,
    depth_cm: float,
    label: str = "Tabber cuts",
) -> "adsk.fusion.Sketch":
    """
    Create a parametric sketch on `face` containing rectangles for each
    notch position in `layout`.

    Each rectangle represents one notch cut. The sketch is used by
    cut_builder.py to extrude-cut into the body.

    Parametric requirements:
    - Project the face edges into the sketch using sketch.project().
      This links the sketch geometry to the face, so if the face changes
      size (e.g. board thickness changes), the sketch updates.
    - Use sketch constraints (horizontal, vertical, equal, symmetric)
      rather than fixed dimensions wherever possible.
    - The depth dimension should be driven by the projected face height,
      not a hardcoded value.
    - The width positions should be driven by parameters registered in
      design.userParameters so the user can see and edit them.

    Implementation notes:
    - Create sketch on face: component.sketches.add(face)
    - Project face boundary: sketch.project(face)
    - Each notch rectangle: sketch.sketchCurves.sketchLines.addTwoPointRectangle()
    - Register tab_width and notch_width as user parameters.
    - Name the sketch with `label` so it's identifiable in the browser.
    - Return the sketch object for use by cut_builder.
    """

def register_parameter(design, name: str, value_cm: float, units: str = "cm") -> "adsk.fusion.UserParameter":
    """
    Register (or update) a user parameter in the design.
    If a parameter with `name` already exists, update its value.
    Returns the parameter.
    """
```

### lib/cut_builder.py

```python
def build_cuts(
    component,
    face,
    sketch,
    depth_cm: float,
) -> list:
    """
    For each closed profile in `sketch`, create an extrude-cut feature
    that cuts into the body to `depth_cm`.

    Returns list of created adsk.fusion.ExtrudeFeature objects.

    Implementation notes:
    - Get profiles from sketch.profiles.
    - For each profile, create an extrude input:
        extrudes = component.features.extrudeFeatures
        input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.CutFeatureOperation)
        input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(depth_cm))
        extrudes.add(input)
    - The cut direction must go INTO the body, not away from it.
      Check the face normal and flip the extent if needed.
    - Do NOT call generateToolpaths or any CAM method.
    """

def build_mirror_cuts(
    component,
    primary_face,
    opposite_face,
    primary_layout: dict,
    depth_cm: float,
) -> list:
    """
    Build the interlocking mirror cuts on the opposite face.

    The mirror layout swaps tabs and notches from the primary layout —
    where primary has a notch, opposite gets a tab (no cut), and where
    primary has a tab, opposite gets a notch (cut).

    Returns list of created ExtrudeFeature objects.

    Implementation:
    - Derive mirror_layout from primary_layout by filtering segments
      to only the 'tab' positions from primary (these become notches
      on the opposite face).
    - Build a new sketch on opposite_face with those positions.
    - Extrude-cut each profile.
    """
```

### commands/GenerateTabs/GenerateTabs.py

This file contains the command definition, button registration, and all event
handlers. Keep all handlers in this one file — the add-in is simple enough
that splitting into separate handler files would add complexity without benefit.

**Button registration:**
- Add to the SOLID workspace (Design workspace), not CAM.
- Panel ID: `'SolidScriptsAddinsPanel'`
- Command ID: `'tabberGenerateTabs'`
- Label: `'Generate Tabs'`
- Tooltip: `'Add finger-joint tabs to a face'`

**Dialog inputs (in order):**

| Input | Type | ID | Default | Visibility |
|---|---|---|---|---|
| Selection Mode | Dropdown | `'selectionModeInput'` | Face+Edge | always |
| Face | Selection (PlanarFaces, 1–1) | `'faceSelectInput'` | — | Edge mode only |
| Top Face | Selection (PlanarFaces, 1–1) | `'topFaceInput'` | — | Face+Edge mode only |
| Edges | Selection (LinearEdges, 1–∞) | `'edgeSelectInput'` | — | Face+Edge mode only |
| Number of Tabs | Integer spinner (1–50) | `'tabCountInput'` | 3 | always |
| Width Mode | Dropdown | `'widthModeInput'` | Automatic | always |
| Tab Width | Float spinner (mm) | `'tabWidthInput'` | 8.0mm | Manual width mode only |
| Pilot Holes | Bool checkbox | `'pilotHolesInput'` | checked | Face+Edge mode only |
| Hole Diameter | Float spinner (in) | `'holeDiameterInput'` | 0.125" | Face+Edge + Pilot Holes on |
| Preview | Bool checkbox | `'previewInput'` | checked | Edge mode only |

**Dialog behavior:**
- `tabWidthInput` is hidden when width mode = Automatic. Show it only when Manual.
- Face+Edge is the default selection mode.
- In Edge mode, the Face selection and Preview checkbox are shown.
- In Face+Edge mode, Top Face, Edges (multi-select), Pilot Holes, and
  Hole Diameter inputs are shown. Preview is disabled (see below).
- `holeDiameterInput` is hidden when Pilot Holes is unchecked.
- When switching selection mode, hidden selection inputs have their limits
  set to (0, 0) so they don't block Fusion's internal validation.
- Auto-advance focus: selecting a top face advances focus to edge input.

**Event handlers:**

```python
class TabberCommandCreatedHandler  # Registers all sub-handlers, builds dialog inputs
class TabberExecutePreviewHandler  # Live preview (Edge mode only, skipped for Face+Edge)
class TabberExecuteHandler         # Final geometry creation + timeline grouping
class TabberInputChangedHandler    # Shows/hides inputs based on mode, auto-advance focus
class TabberSelectionHandler       # Filters selection to planar faces / linear edges
class TabberValidateHandler        # Ensures required selections before enabling OK
```

**Architecture — `_build_geometry(inputs)` helper:**

Both execute and preview call a shared module-level function `_build_geometry(inputs)`
that reads all dialog inputs and builds geometry. Returns `(suffix, start_index)` or
`None` if required selections are missing. The execute handler adds timeline grouping
on top. The preview handler checks selection mode and preview checkbox first.

**Execute flow — Edge mode:**
1. Read face → get dimensions → calculate layout
2. `build_tab_sketch()` → `build_cuts()` (distance extent)

**Execute flow — Face+Edge mode (multi-edge):**
1. Read top face + collect all selected edges
2. For each edge: find edge face → get board thickness → calculate layout → `build_face_edge_sketch()`
3. All sketches built first (BRep stays valid), then all extrudes via `build_hole_cuts()`
4. Group all timeline items into a single named group

**Preview:**
- Edge mode: full real-time preview with extrude cuts (toggle via Preview checkbox)
- Face+Edge mode: preview disabled — extrude cuts invalidate BRep edge entities,
  which prevents multi-edge selection. Geometry created only on OK click.

---

## Parametric design — critical requirements

This is the hardest part of the implementation. Read carefully.

**The goal:** If a user changes the board thickness in their design (which changes
the height of the selected face), the tab depth should update automatically.
If they change the board length (which changes the face length), the tab
positions should recalculate automatically.

**How to achieve this:**

1. **Project face edges into the sketch.** Use `sketch.project(edge)` on each
   edge of the selected face. This creates sketch lines that are linked to the
   face geometry. If the face changes, the projected lines move.

2. **Register tab dimensions as user parameters.** Use `design.userParameters`
   to create named parameters like `tabber_tab_width` and `tabber_notch_width`.
   Drive sketch dimensions from these parameters using
   `adsk.core.ValueInput.createByString("tabber_tab_width")`.

3. **Use sketch constraints, not fixed dimensions.** Apply horizontal/vertical
   constraints to sketch lines. Use the `Equal` constraint to enforce that all
   tabs are the same width. Use `Symmetric` constraint to center the pattern.

4. **Depth driven by projected geometry.** The extrude-cut depth should be
   driven by the projected face height, not a hardcoded number. Create a
   construction line equal to the projected height edge, then reference it.

5. **Never use hardcoded coordinate values** in the sketch if those values
   could change when the model changes. Always derive from projected edges
   or parameters.

---

## Fusion 360 API reference — key patterns

```python
# Get active design and root component
app       = adsk.core.Application.get()
design    = adsk.fusion.Design.cast(app.activeProduct)
component = design.activeComponent   # or design.rootComponent

# Get face normal
ok, normal = face.evaluator.getNormalAtPoint(face.pointOnFace)

# Create sketch on a face
sketch = component.sketches.add(face)

# Project a face edge into the sketch
for edge in face.edges:
    sketch.project(edge)

# Add a rectangle by two corner points (returns 4 SketchLines)
lines = sketch.sketchCurves.sketchLines
rect_lines = lines.addTwoPointRectangle(
    adsk.core.Point3D.create(x1, y1, 0),
    adsk.core.Point3D.create(x2, y2, 0),
)
# rect_lines is a SketchLineList — use .item(i), NOT [i] or [x:y] slices

# Register a user parameter
params = design.userParameters
existing = params.itemByName("tabber_tab_width")
if existing:
    existing.expression = f"{value_cm}"
else:
    params.add("tabber_tab_width",
               adsk.core.ValueInput.createByReal(value_cm),
               "cm", "Tabber: tab width")

# Extrude cut
extrudes  = component.features.extrudeFeatures
ext_input = extrudes.createInput(
    profile,
    adsk.fusion.FeatureOperations.CutFeatureOperation
)
ext_input.setDistanceExtent(
    False,
    adsk.core.ValueInput.createByReal(depth_cm)
)
extrudes.add(ext_input)
```

**CRITICAL — Fusion collection objects:**
- Always use `.item(i)` to index into Fusion collections, never `[i]`
- Never use slice notation `[x:y]` on Fusion collections — use explicit `.item()` calls
- Use `.count` instead of `len()` on Fusion collections
- Some collections support `for x in collection` directly; if that fails, use
  `for i in range(collection.count): x = collection.item(i)`

**Units:**
- ALL Fusion internal distances are in **centimeters**
- Convert mm → cm: divide by 10
- Convert cm → mm: multiply by 10
- Display values to the user in their document units (use `unitsManager`)
- Store and compute everything internally in cm

---

## Tab layout math — reference implementation

This is the core math. Implement this exactly in `lib/layout.py`.

```python
def calculate_layout(face_length_cm, tab_count, width_mode, manual_tab_width_cm=None):
    N = tab_count          # number of tabs
    M = N + 1              # number of notches (always one more than tabs)
    L = face_length_cm

    if width_mode == 'auto':
        # All tabs and notches equal width
        segment_width = L / (2 * N + 1)   # 2N+1 segments total: N tabs + N+1 notches
        tab_w   = segment_width
        notch_w = segment_width

    elif width_mode == 'manual':
        tab_w   = manual_tab_width_cm
        notch_w = (L - N * tab_w) / M
        if notch_w <= 0:
            raise LayoutError(
                f"Tab width {tab_w*10:.1f}mm is too large for face length {L*10:.1f}mm "
                f"with {N} tabs. Notch width would be {notch_w*10:.1f}mm."
            )

    # Total pattern width and centering offset
    total_w = M * notch_w + N * tab_w    # should equal L for auto mode
    offset  = (L - total_w) / 2          # centers the pattern; 0 for auto mode

    # Build segment list left to right
    segments = []
    x = offset
    for i in range(M + N):              # M notches + N tabs interleaved
        if i % 2 == 0:                  # even index = notch
            segments.append({"type": "notch", "start_cm": x, "end_cm": x + notch_w})
            x += notch_w
        else:                           # odd index = tab
            segments.append({"type": "tab", "start_cm": x, "end_cm": x + tab_w})
            x += tab_w

    return {
        "tab_width_cm":   tab_w,
        "notch_width_cm": notch_w,
        "segments":       segments,
    }
```

---

## Build order for Claude Code

Implement in this sequence:

1. **`tabber.manifest`** — static JSON file, no code.

2. **`config.py`** — constants only, no dependencies.

3. **`lib/layout.py`** — pure Python math, no Fusion imports needed.
   Write `tests/test_layout.py` alongside it.
   Run tests with `python -m pytest tests/` to verify before continuing.

4. **`lib/geometry.py`** — Fusion geometry analysis.

5. **`lib/sketch_builder.py`** — parametric sketch creation.
   This is the most complex module. Take it slowly.

6. **`lib/cut_builder.py`** — extrude-cut features.

7. **`commands/GenerateTabs/GenerateTabs.py`** — full command with all handlers.

8. **`tabber.py`** — entry point, wires everything together.

---

## Testing strategy

**Unit tests (no Fusion needed):**

```python
# tests/test_layout.py — mock nothing, pure math
from lib.layout import calculate_layout, LayoutError

def test_auto_mode_equal_widths():
    result = calculate_layout(30.0, 3, 'auto')  # 30cm face, 3 tabs
    assert result["tab_width_cm"] == result["notch_width_cm"]
    assert len([s for s in result["segments"] if s["type"] == "notch"]) == 4  # N+1
    assert len([s for s in result["segments"] if s["type"] == "tab"])  == 3  # N

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
        assert abs(segs[i]["end_cm"] - segs[i+1]["start_cm"]) < 0.001

def test_always_starts_and_ends_with_notch():
    result = calculate_layout(20.0, 2, 'auto')
    assert result["segments"][0]["type"]  == "notch"
    assert result["segments"][-1]["type"] == "notch"
```

**Integration testing (inside Fusion):**
- Install add-in from AddIns folder
- Open a simple box model (two rectangular plywood panels)
- Select an edge face, run Generate Tabs
- Verify: cuts appear, correct count, centered, parametric update works
  when body dimension parameter is changed

---

## Known constraints and gotchas

- **Sketch coordinate system:** When you create a sketch on a face, the sketch
  XY plane is the face plane. The origin is NOT guaranteed to be at the face
  corner — project face edges first to understand the coordinate space.

- **Cut direction:** `setDistanceExtent` cuts in the direction of the face
  normal by default. If the cuts go the wrong way, negate the depth value or
  use `setTwoSidesExtent`.

- **Parametric sketch constraints:** Fusion's constraint API is verbose. If full
  constraint-based parametrics proves too complex for v1, fall back to driving
  dimensions via user parameters and `ValueInput.createByString("param_name")`.
  This is less fully parametric but still updates when parameters change.

- **Multiple bodies:** If the component has multiple bodies, the extrude-cut
  needs to target the correct one. Use `ext_input.participantBodies` to specify.

- **Opposite face detection:** The opposite face is on a different body if the
  box is modeled as separate panels. Handle both cases — same body and
  different body.

- **Do not use slice notation** on any Fusion collection object. Ever.
  Always `.item(i)`. This is the bug that broke TabGen.

---

## Scope boundaries (v1)

- Rectangular faces only — no irregular shapes
- No kerf adjustment — out of scope for v1
- Metric and imperial both supported via unitsManager

## Known constraints and design decisions

- **Preview disabled in Face+Edge mode:** Extrude cuts during preview rebuild the
  BRep, invalidating edge entities that Fusion's selection input tracks. This makes
  it impossible to select additional edges after preview runs. Preview is therefore
  disabled for Face+Edge mode. Edge mode (single face) has full real-time preview.

- **Multi-edge: sketches first, extrudes second:** When multiple edges are selected,
  all sketches are built in a first pass (BRep stays unmodified, all edge/face
  entities remain valid), then all extrudes happen in a second pass. This avoids
  stale entity errors between edges.

- **`build_hole_cuts` accepts `target_body`:** The body reference is captured once
  before extrudes begin and passed directly, since `face.body` goes stale after
  the first extrude cut.

- **Stale entity guards:** Selection access is wrapped in try/except RuntimeError
  throughout `_build_geometry()`, returning None (no-op) if entities are invalid.
  Edge collection uses a break-on-error loop since `selectionCount` can be stale.
