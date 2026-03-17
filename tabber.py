import adsk.core
import adsk.fusion
import importlib
import traceback

from .lib import geometry
from .lib import layout
from .lib import sketch_builder
from .lib import cut_builder
from .commands.GenerateTabs import GenerateTabs


def run(context):
    try:
        # Force-reload all modules so code changes take effect
        # without restarting Fusion
        importlib.reload(geometry)
        importlib.reload(layout)
        importlib.reload(sketch_builder)
        importlib.reload(cut_builder)
        importlib.reload(GenerateTabs)

        app = adsk.core.Application.get()
        ui = app.userInterface
        GenerateTabs.register(ui)
    except Exception:
        app = adsk.core.Application.get()
        app.userInterface.messageBox(
            f'Tabber failed to start:\n{traceback.format_exc()}'
        )


def stop(context):
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        GenerateTabs.unregister(ui)
    except Exception:
        app = adsk.core.Application.get()
        app.userInterface.messageBox(
            f'Tabber failed to stop:\n{traceback.format_exc()}'
        )
