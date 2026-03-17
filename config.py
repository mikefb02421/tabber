import logging


class Config:
    # Logging
    LOG_FILE = 'tabber.log'
    LOG_LEVEL = logging.NOTSET

    # Defaults shown in dialog
    DEFAULT_TAB_COUNT = 3
    DEFAULT_WIDTH_MODE = 'auto'
    DEFAULT_MANUAL_WIDTH = 8.0  # mm
    DEFAULT_PLACEMENT = 'dual'

    def __init__(self, app):
        self.app = app
        self.ui = app.userInterface
        self.design = app.activeProduct
