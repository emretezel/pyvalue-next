"""A progress bar on one line, for a command that runs for a while.

The bar is redrawn in place: each update returns to the start of the line
and writes over what was there, so a long run never scrolls the screen. The
counts a command prints at its end start on a line of their own.

Nothing is drawn when the output is not a terminal. A bar that is redrawn
into a file or a log is thousands of lines of noise. Plain ``conda run``
holds a command's output back until it ends, so the bar shows only with
``conda run --no-capture-output``, or in an activated environment.

Author: Emre Tezel
"""

import time
from collections.abc import Callable
from typing import TextIO

# How many characters the bar itself has, between its brackets.
_WIDTH: int = 30

_SECONDS_IN_A_MINUTE: int = 60


def _time_left(seconds: float) -> str:
    """Say how long the rest takes, in words a person reads at a glance."""
    if seconds < _SECONDS_IN_A_MINUTE:
        return "under a minute left"
    return f"about {round(seconds / _SECONDS_IN_A_MINUTE):,} min left"


def progress_line(done: int, total: int, elapsed: float) -> str:
    """Return the text of the bar for one moment of a run.

    Args:
        done: How many steps are done.
        total: How many there are in all; more than none.
        elapsed: The seconds since the run began.

    Returns:
        The bar, the two counts, the percentage and, while the run is under
        way, an estimate of the time left. The estimate assumes the rest goes
        at the pace so far.
    """
    filled = _WIDTH * done // total
    line = (
        f"[{'#' * filled}{'.' * (_WIDTH - filled)}] {done:,} of {total:,}  {100 * done // total}%"
    )
    if 0 < done < total and elapsed > 0:
        line += f"  {_time_left(elapsed * (total - done) / done)}"
    return line


class ProgressBar:
    """One line that shows how far a run is, redrawn in place.

    A command creates the bar just before the work starts, hands ``update``
    to the component as its progress function, and calls ``finish`` when the
    work is over, whatever the outcome.
    """

    def __init__(self, stream: TextIO, clock: Callable[[], float] = time.monotonic) -> None:
        """Prepare a bar on one stream.

        Args:
            stream: Where to draw. Nothing is drawn unless it is a terminal.
            clock: What returns the seconds that have passed. Tests pass
                their own.
        """
        self._stream = stream
        self._clock = clock
        self._shown = stream.isatty()
        self._started = clock()
        # The length of the line that is on the screen, so that a shorter
        # one can cover it completely.
        self._drawn = 0

    def update(self, done: int, total: int) -> None:
        """Redraw the bar.

        Args:
            done: How many steps are done.
            total: How many there are in all.
        """
        if not self._shown or total <= 0:
            return
        line = progress_line(done, total, self._clock() - self._started)
        # The carriage return goes back to the start of the line without
        # starting a new one. The padding wipes what a longer line left.
        self._stream.write(f"\r{line.ljust(self._drawn)}")
        self._stream.flush()
        self._drawn = len(line)

    def finish(self) -> None:
        """End the bar's line, so that what is printed next starts on a new one."""
        if self._drawn:
            self._stream.write("\n")
            self._stream.flush()
            self._drawn = 0
