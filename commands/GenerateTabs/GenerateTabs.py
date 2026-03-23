import adsk.core
import adsk.fusion
import os
import traceback

from ...lib import layout as layout_mod

# Command identifiers
CMD_ID = 'tabberGenerateTabs'
CMD_NAME = 'Tabber'
CMD_TOOLTIP = 'Add finger-joint tabs to a face'
PANEL_ID = 'SolidCreatePanel'
RESOURCES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'resources', 'Tabber')

# Keep handler references alive
_handlers = []


def register(ui):
    """Register the command button in the Fusion UI."""
    cmd_defs = ui.commandDefinitions
    existing = cmd_defs.itemById(CMD_ID)
    if existing:
        existing.deleteMe()

    cmd_def = cmd_defs.addButtonDefinition(CMD_ID, CMD_NAME, CMD_TOOLTIP, RESOURCES_DIR)

    on_created = TabberCommandCreatedHandler()
    cmd_def.commandCreated.add(on_created)
    _handlers.append(on_created)

    panel = ui.allToolbarPanels.itemById(PANEL_ID)
    if panel:
        existing_ctrl = panel.controls.itemById(CMD_ID)
        if existing_ctrl:
            existing_ctrl.deleteMe()
        ctrl = panel.controls.addCommand(cmd_def)
        ctrl.isPromotedByDefault = True
        ctrl.isPromoted = True

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

            # Selection mode dropdown
            sel_mode_input = inputs.addDropDownCommandInput(
                'selectionModeInput', 'Selection Mode',
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            sel_mode_input.listItems.add('Edge', True)
            sel_mode_input.listItems.add('Face+Edge', False)

            # Face selection (Edge mode)
            face_input = inputs.addSelectionInput(
                'faceSelectInput', 'Face', 'Select a planar face',
            )
            face_input.addSelectionFilter('PlanarFaces')
            face_input.setSelectionLimits(1, 1)

            # Top Face selection (Face+Edge mode)
            top_face_input = inputs.addSelectionInput(
                'topFaceInput', 'Top Face', 'Select the top face of the board',
            )
            top_face_input.addSelectionFilter('PlanarFaces')
            top_face_input.setSelectionLimits(1, 1)
            top_face_input.isVisible = False

            # Edge selection (Face+Edge mode)
            edge_input = inputs.addSelectionInput(
                'edgeSelectInput', 'Edge', 'Select an edge on the top face',
            )
            edge_input.addSelectionFilter('LinearEdges')
            edge_input.setSelectionLimits(1, 1)
            edge_input.isVisible = False

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

            # Hole diameter (Face+Edge mode, inches)
            hole_dia_input = inputs.addFloatSpinnerCommandInput(
                'holeDiameterInput', 'Hole Diameter',
                'in', 0.01, 2.0, 0.0625, 0.125,
            )
            hole_dia_input.isVisible = False

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

            # Force-reload lib modules to pick up code changes
            import importlib, sys
            for mod_name in list(sys.modules.keys()):
                if 'Tabber' in mod_name and 'lib' in mod_name:
                    del sys.modules[mod_name]
            from ...lib import geometry as _geo, sketch_builder as _sb, cut_builder as _cb

            # Read common inputs
            sel_mode_input = inputs.itemById('selectionModeInput')
            selection_mode = sel_mode_input.selectedItem.name  # 'Edge' or 'Face+Edge'

            tab_count_input = inputs.itemById('tabCountInput')
            tab_count = tab_count_input.value

            width_mode_input = inputs.itemById('widthModeInput')
            width_mode_name = width_mode_input.selectedItem.name

            tab_width_input = inputs.itemById('tabWidthInput')
            manual_width_cm = tab_width_input.value

            width_mode = 'auto' if width_mode_name == 'Automatic' else 'manual'

            timeline = design.timeline
            start_index = timeline.count

            if selection_mode == 'Edge':
                # --- Edge mode (original flow) ---
                face_input = inputs.itemById('faceSelectInput')
                face = face_input.selection(0).entity
                component = face.body.parentComponent

                dims = _geo.get_face_dimensions(face)

                tab_layout = layout_mod.calculate_layout(
                    face_length_cm=dims["length_cm"],
                    tab_count=tab_count,
                    width_mode=width_mode,
                    manual_tab_width_cm=manual_width_cm if width_mode == 'manual' else None,
                )

                sketch, suffix = _sb.build_tab_sketch(
                    component, face, tab_layout, dims["height_cm"],
                    width_mode=width_mode,
                    tab_count=tab_count,
                    manual_tab_width_cm=manual_width_cm if width_mode == 'manual' else None,
                )
                _cb.build_cuts(component, face, sketch, dims["height_cm"],
                               param_suffix=suffix)

            else:
                # --- Face+Edge mode ---
                top_face_input = inputs.itemById('topFaceInput')
                top_face = top_face_input.selection(0).entity

                edge_input = inputs.itemById('edgeSelectInput')
                selected_edge = edge_input.selection(0).entity

                hole_dia_input = inputs.itemById('holeDiameterInput')
                hole_diameter_cm = hole_dia_input.value  # Fusion stores in cm

                # Find the edge face (perpendicular face adjacent to the edge)
                edge_face = _geo.find_edge_face(selected_edge, top_face)
                if edge_face is None:
                    raise RuntimeError(
                        "Tabber: could not find the edge face adjacent to "
                        "the selected edge. Ensure the edge borders two faces."
                    )

                component = top_face.body.parentComponent

                # Edge face dimensions: length from edge, height = board thickness
                edge_length_cm = _geo.get_edge_length(selected_edge)
                edge_dims = _geo.get_face_dimensions(edge_face)
                board_thickness_cm = edge_dims["height_cm"]

                tab_layout = layout_mod.calculate_layout(
                    face_length_cm=edge_length_cm,
                    tab_count=tab_count,
                    width_mode=width_mode,
                    manual_tab_width_cm=manual_width_cm if width_mode == 'manual' else None,
                )

                # Build tab sketch and cuts on the edge face
                sketch, suffix = _sb.build_tab_sketch(
                    component, edge_face, tab_layout, board_thickness_cm,
                    width_mode=width_mode,
                    tab_count=tab_count,
                    manual_tab_width_cm=manual_width_cm if width_mode == 'manual' else None,
                )
                _cb.build_cuts(component, edge_face, sketch, board_thickness_cm,
                               param_suffix=suffix)

                # Build pilot hole sketch and cuts on the top face
                hole_sketch = _sb.build_pilot_hole_sketch(
                    component, top_face, selected_edge, tab_layout,
                    board_thickness_cm, hole_diameter_cm,
                    suffix=suffix,
                )
                _cb.build_hole_cuts(component, top_face, hole_sketch)

            # Group all new timeline items
            end_index = timeline.count - 1
            if end_index > start_index:
                group = timeline.timelineGroups.add(start_index, end_index)
                group_num = suffix.replace("_", "") if suffix else "1"
                group.name = f"Tabs {group_num}"

        except layout_mod.LayoutError as e:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(str(e), 'Tabber Layout Error')
        except Exception:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(traceback.format_exc())


class TabberInputChangedHandler(adsk.core.InputChangedEventHandler):
    """Shows/hides tab width input based on width mode."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            changed_input = args.input
            inputs = changed_input.parentCommand.commandInputs

            sel_mode_input = inputs.itemById('selectionModeInput')
            is_face_edge = sel_mode_input.selectedItem.name == 'Face+Edge'

            # Toggle inputs by selection mode
            inputs.itemById('faceSelectInput').isVisible = not is_face_edge
            inputs.itemById('topFaceInput').isVisible = is_face_edge
            inputs.itemById('edgeSelectInput').isVisible = is_face_edge
            inputs.itemById('holeDiameterInput').isVisible = is_face_edge

            # Toggle manual tab width visibility
            width_mode_input = inputs.itemById('widthModeInput')
            is_manual = width_mode_input.selectedItem.name == 'Manual'
            inputs.itemById('tabWidthInput').isVisible = is_manual

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
            active_input = selection_args.activeInput

            # Edge input accepts linear edges
            if active_input.id == 'edgeSelectInput':
                if hasattr(entity, 'geometry'):
                    geo = entity.geometry
                    if hasattr(geo, 'curveType'):
                        if geo.curveType == adsk.core.Curve3DTypes.Line3DCurveType:
                            selection_args.isSelectable = True
                            return
                selection_args.isSelectable = False
                return

            # Face inputs accept planar faces
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

            sel_mode_input = inputs.itemById('selectionModeInput')
            is_face_edge = sel_mode_input.selectedItem.name == 'Face+Edge'

            if is_face_edge:
                top_face_input = inputs.itemById('topFaceInput')
                edge_input = inputs.itemById('edgeSelectInput')
                if top_face_input.selectionCount < 1 or edge_input.selectionCount < 1:
                    validate_args.areInputsValid = False
                    return
            else:
                face_input = inputs.itemById('faceSelectInput')
                if face_input.selectionCount < 1:
                    validate_args.areInputsValid = False
                    return

            validate_args.areInputsValid = True
        except Exception:
            validate_args.areInputsValid = False
