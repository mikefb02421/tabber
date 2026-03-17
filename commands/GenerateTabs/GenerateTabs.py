import adsk.core
import adsk.fusion
import traceback

from ...lib import geometry
from ...lib import layout as layout_mod
from ...lib import sketch_builder
from ...lib import cut_builder

# Command identifiers
CMD_ID = 'tabberGenerateTabs'
CMD_NAME = 'Generate Tabs'
CMD_TOOLTIP = 'Add finger-joint tabs to a face'
PANEL_ID = 'SolidScriptsAddinsPanel'

# Keep handler references alive
_handlers = []


def register(ui):
    """Register the command button in the Fusion UI."""
    cmd_defs = ui.commandDefinitions
    existing = cmd_defs.itemById(CMD_ID)
    if existing:
        existing.deleteMe()

    cmd_def = cmd_defs.addButtonDefinition(CMD_ID, CMD_NAME, CMD_TOOLTIP)

    on_created = TabberCommandCreatedHandler()
    cmd_def.commandCreated.add(on_created)
    _handlers.append(on_created)

    panel = ui.allToolbarPanels.itemById(PANEL_ID)
    if panel:
        existing_ctrl = panel.controls.itemById(CMD_ID)
        if existing_ctrl:
            existing_ctrl.deleteMe()
        panel.controls.addCommand(cmd_def)

    return cmd_def


def unregister(ui):
    """Remove the command button from the Fusion UI."""
    panel = ui.allToolbarPanels.itemById(PANEL_ID)
    if panel:
        ctrl = panel.controls.itemById(CMD_ID)
        if ctrl:
            ctrl.deleteMe()

    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()

    _handlers.clear()


class TabberCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Registers all sub-handlers and builds dialog inputs."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = adsk.core.Command.cast(args.command)
            inputs = cmd.commandInputs

            # Placement dropdown
            placement_input = inputs.addDropDownCommandInput(
                'placementInput', 'Placement',
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            placement_input.listItems.add('Dual Edge', True)
            placement_input.listItems.add('Single Edge', False)

            # Primary face selection
            face_input = inputs.addSelectionInput(
                'faceSelectInput', 'Face', 'Select a planar face',
            )
            face_input.addSelectionFilter('PlanarFaces')
            face_input.setSelectionLimits(1, 1)

            # Secondary face selection (for dual mode)
            secondary_input = inputs.addSelectionInput(
                'secondaryFaceInput', 'Secondary Face',
                'Select the opposite face (auto-detected if possible)',
            )
            secondary_input.addSelectionFilter('PlanarFaces')
            secondary_input.setSelectionLimits(0, 1)
            secondary_input.isVisible = True  # Dual is default

            # Tab count
            inputs.addIntegerSpinnerCommandInput(
                'tabCountInput', 'Number of Tabs', 1, 50, 1, 3,
            )

            # Width mode dropdown
            width_mode_input = inputs.addDropDownCommandInput(
                'widthModeInput', 'Width Mode',
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            width_mode_input.listItems.add('Automatic', True)
            width_mode_input.listItems.add('Manual', False)

            # Manual tab width (mm displayed, stored internally as cm)
            tab_width_input = inputs.addFloatSpinnerCommandInput(
                'tabWidthInput', 'Tab Width',
                'mm', 0.1, 1000.0, 0.5, 8.0,
            )
            tab_width_input.isVisible = False  # Hidden when Automatic

            # Warning message (hidden by default)
            warning_input = inputs.addTextBoxCommandInput(
                'warningMsgInput', '', '', 2, True,
            )
            warning_input.isVisible = False

            # Register event handlers
            on_execute = TabberExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)

            on_input_changed = TabberInputChangedHandler()
            cmd.inputChanged.add(on_input_changed)
            _handlers.append(on_input_changed)

            on_selection = TabberSelectionHandler()
            cmd.selectionEvent.add(on_selection)
            _handlers.append(on_selection)

            on_validate = TabberValidateHandler()
            cmd.validateInputs.add(on_validate)
            _handlers.append(on_validate)

        except Exception:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(traceback.format_exc())


class TabberExecuteHandler(adsk.core.CommandEventHandler):
    """Reads inputs and calls lib/ modules to create geometry."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            app = adsk.core.Application.get()
            design = adsk.fusion.Design.cast(app.activeProduct)

            cmd = args.command
            inputs = cmd.commandInputs

            # Read inputs
            face_input = inputs.itemById('faceSelectInput')
            face = face_input.selection(0).entity

            # Derive component from the face's body so sketch and extrude
            # operate in the correct component context
            component = face.body.parentComponent

            tab_count_input = inputs.itemById('tabCountInput')
            tab_count = tab_count_input.value

            width_mode_input = inputs.itemById('widthModeInput')
            width_mode_name = width_mode_input.selectedItem.name

            placement_input = inputs.itemById('placementInput')
            placement_name = placement_input.selectedItem.name

            tab_width_input = inputs.itemById('tabWidthInput')
            # Fusion stores float spinner values in internal units (cm)
            manual_width_cm = tab_width_input.value

            # Get face dimensions
            dims = geometry.get_face_dimensions(face)

            # Calculate layout
            width_mode = 'auto' if width_mode_name == 'Automatic' else 'manual'
            tab_layout = layout_mod.calculate_layout(
                face_length_cm=dims["length_cm"],
                tab_count=tab_count,
                width_mode=width_mode,
                manual_tab_width_cm=manual_width_cm if width_mode == 'manual' else None,
            )

            # Force-reload lib modules to pick up code changes
            import importlib, sys
            # Clear cached modules so reload reads from disk
            for mod_name in list(sys.modules.keys()):
                if 'Tabber' in mod_name and 'lib' in mod_name:
                    del sys.modules[mod_name]
            from ...lib import geometry as _geo, sketch_builder as _sb, cut_builder as _cb

            # Build sketch and cuts on primary face
            sketch = _sb.build_tab_sketch(
                component, face, tab_layout, dims["height_cm"],
            )
            _cb.build_cuts(component, face, sketch, dims["height_cm"])

            # If dual mode, build mirror cuts on opposite face
            if placement_name == 'Dual Edge':
                secondary_input = inputs.itemById('secondaryFaceInput')
                if secondary_input.selectionCount > 0:
                    opposite = secondary_input.selection(0).entity
                    opp_component = opposite.body.parentComponent

                    # Get primary sketch bounds from its line endpoints
                    # (primary face entity is invalid after cuts)
                    pri_min_x, pri_max_x = float('inf'), float('-inf')
                    pri_min_y, pri_max_y = float('inf'), float('-inf')
                    pri_lines = sketch.sketchCurves.sketchLines
                    for li in range(pri_lines.count):
                        ln = pri_lines.item(li)
                        for pt in [ln.startSketchPoint.geometry, ln.endSketchPoint.geometry]:
                            pri_min_x = min(pri_min_x, pt.x)
                            pri_max_x = max(pri_max_x, pt.x)
                            pri_min_y = min(pri_min_y, pt.y)
                            pri_max_y = max(pri_max_y, pt.y)

                    pri_w = pri_max_x - pri_min_x
                    pri_h = pri_max_y - pri_min_y
                    pri_length_is_x = (pri_w >= pri_h)

                    # Create sketch on opposite face
                    try:
                        opp_sketch = opp_component.sketches.addWithoutEdges(opposite)
                    except AttributeError:
                        opp_sketch = opp_component.sketches.add(opposite)
                    opp_sketch.name = "Tabber mirror cuts"

                    # For each primary TAB (= mirror notch/cut),
                    # map corners through model space to opposite sketch space
                    for seg in tab_layout["segments"]:
                        if seg["type"] != "notch":
                            continue
                        if pri_length_is_x:
                            sx1, sy1 = pri_min_x + seg["start_cm"], pri_min_y
                            sx2, sy2 = pri_min_x + seg["end_cm"], pri_max_y
                        else:
                            sx1, sy1 = pri_min_x, pri_min_y + seg["start_cm"]
                            sx2, sy2 = pri_max_x, pri_min_y + seg["end_cm"]

                        m1 = sketch.sketchToModelSpace(adsk.core.Point3D.create(sx1, sy1, 0))
                        m2 = sketch.sketchToModelSpace(adsk.core.Point3D.create(sx2, sy2, 0))
                        o1 = opp_sketch.modelToSketchSpace(m1)
                        o2 = opp_sketch.modelToSketchSpace(m2)

                        opp_sketch.sketchCurves.sketchLines.addTwoPointRectangle(
                            adsk.core.Point3D.create(min(o1.x, o2.x), min(o1.y, o2.y), 0),
                            adsk.core.Point3D.create(max(o1.x, o2.x), max(o1.y, o2.y), 0),
                        )

                    # Cut the opposite face
                    _cb.build_cuts(opp_component, opposite, opp_sketch, dims["height_cm"])

        except layout_mod.LayoutError as e:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(str(e), 'Tabber Layout Error')
        except Exception:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(traceback.format_exc())


class TabberInputChangedHandler(adsk.core.InputChangedEventHandler):
    """Shows/hides inputs and triggers opposite face auto-detection."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            changed_input = args.input
            inputs = changed_input.parentCommand.commandInputs

            width_mode_input = inputs.itemById('widthModeInput')
            tab_width_input = inputs.itemById('tabWidthInput')
            placement_input = inputs.itemById('placementInput')
            secondary_input = inputs.itemById('secondaryFaceInput')
            face_input = inputs.itemById('faceSelectInput')
            warning_input = inputs.itemById('warningMsgInput')

            # Toggle manual tab width visibility
            is_manual = width_mode_input.selectedItem.name == 'Manual'
            tab_width_input.isVisible = is_manual

            # Toggle secondary face visibility
            is_dual = placement_input.selectedItem.name == 'Dual Edge'
            secondary_input.isVisible = is_dual

            # Auto-detect opposite face when primary face changes in dual mode
            if changed_input.id == 'faceSelectInput' and is_dual:
                warning_input.isVisible = False

                if face_input.selectionCount > 0:
                    face = face_input.selection(0).entity
                    app = adsk.core.Application.get()
                    design = adsk.fusion.Design.cast(app.activeProduct)
                    component = design.activeComponent

                    opposite = geometry.find_opposite_face(face, component)
                    if opposite:
                        secondary_input.clearSelection()
                        secondary_input.addSelection(opposite)
                    else:
                        warning_input.formattedText = (
                            'No opposite face detected. '
                            'Switch to Single Edge or select manually.'
                        )
                        warning_input.isVisible = True

            # Hide warning when switching to single mode
            if changed_input.id == 'placementInput' and not is_dual:
                warning_input.isVisible = False

        except Exception:
            pass  # Don't crash on input change events


class TabberSelectionHandler(adsk.core.SelectionEventHandler):
    """Filters selection to planar faces only."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            selection_args = adsk.core.SelectionEventArgs.cast(args)
            entity = selection_args.selection.entity

            if hasattr(entity, 'geometry'):
                if entity.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
                    selection_args.isSelectable = True
                    return

            selection_args.isSelectable = False
        except Exception:
            selection_args.isSelectable = False


class TabberValidateHandler(adsk.core.ValidateInputsEventHandler):
    """Ensures at least one face is selected before enabling OK."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            validate_args = adsk.core.ValidateInputsEventArgs.cast(args)
            inputs = args.inputs

            face_input = inputs.itemById('faceSelectInput')
            if face_input.selectionCount < 1:
                validate_args.areInputsValid = False
                return

            validate_args.areInputsValid = True
        except Exception:
            validate_args.areInputsValid = False
