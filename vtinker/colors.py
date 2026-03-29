"""ANSI color helpers for terminal output."""
from __future__ import annotations

import os
import sys

# Respect NO_COLOR (https://no-color.org/) and dumb terminals
_NO_COLOR = (
    os.environ.get("NO_COLOR", "") != ""
    or os.environ.get("TERM", "") == "dumb"
    or not hasattr(sys.stderr, "isatty")
    or not sys.stderr.isatty()
)


def _esc(code: str) -> str:
    return "" if _NO_COLOR else f"\033[{code}m"


# Reset
RESET = _esc("0")

# Styles
BOLD = _esc("1")
DIM = _esc("2")
ITALIC = _esc("3")

# Foreground colors
BLACK = _esc("30")
RED = _esc("31")
GREEN = _esc("32")
YELLOW = _esc("33")
BLUE = _esc("34")
MAGENTA = _esc("35")
CYAN = _esc("36")
WHITE = _esc("37")

# Bright foreground
BR_BLACK = _esc("90")    # gray
BR_RED = _esc("91")
BR_GREEN = _esc("92")
BR_YELLOW = _esc("93")
BR_BLUE = _esc("94")
BR_MAGENTA = _esc("95")
BR_CYAN = _esc("96")
BR_WHITE = _esc("97")


# Semantic aliases
PHASE = BOLD + BR_CYAN
TOOL_CALL = YELLOW
TOOL_RESULT = DIM + GREEN
TOOL_PATH = BR_WHITE
THINKING = DIM + MAGENTA
TEXT = RESET
STEP_LINE = DIM + BR_BLACK
TOKEN_INFO = DIM + BR_BLACK
ERROR = BOLD + RED
SUCCESS = BOLD + GREEN
WARN = YELLOW
DEBUG = DIM + BR_BLACK
TIMESTAMP = DIM + BR_BLACK
