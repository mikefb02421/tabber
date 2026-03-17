import adsk.core
import adsk.fusion
import traceback

from ...lib import layout as layout_mod

# Command identifiers
CMD_ID = 'tabberGenerateTabs'
CMD_NAME = 'Tabber'
CMD_TOOLTIP = 'Add finger-joint tabs to a face'
PANEL_ID = 'SolidModifyPanel'

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

            # Face selection
            face_input = inputs.addSelectionInput(
                'faceSelectInput', 'Face', 'Select a planar face',
            )
            face_input.addSelectionFilter('PlanarFaces')
            face_input.setSelectionLimits(1, 1)

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

            tab_width_input = inputs.itemById('tabWidthInput')
            # Fusion stores float spinner values in internal units (cm)
            manual_width_cm = tab_width_input.value

            # Get face dimensions
            from ...lib import geometry
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

            # Record timeline position before creating geometry
            timeline = design.timeline
            start_index = timeline.count

            # Build parametric sketch and cuts on primary face
            sketch, suffix = _sb.build_tab_sketch(
                component, face, tab_layout, dims["height_cm"],
                width_mode=width_mode,
                tab_count=tab_count,
                manual_tab_width_cm=manual_width_cm if width_mode == 'manual' else None,
            )
            _cb.build_cuts(component, face, sketch, dims["height_cm"],
                           param_suffix=suffix)

            # Group all new timeline items with descriptive name
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

            width_mode_input = inputs.itemById('widthModeInput')
            tab_width_input = inputs.itemById('tabWidthInput')

            # Toggle manual tab width visibility
            is_manual = width_mode_input.selectedItem.name == 'Manual'
            tab_width_input.isVisible = is_manual

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
