"""Tests for ``pyvalue.cli.progress``: one progress bar on one line.

The author's rule for a command that runs for a while: a bar that is redrawn
in place, never a new line for each update (ADR 0028).

Author: Emre Tezel
"""

import io

from hypothesis import given
from hypothesis import strategies as st

from pyvalue.cli.progress import ProgressBar, progress_line


class _Screen(io.StringIO):
    """Stands in for a terminal, or for a file when it is not one."""

    def __init__(self, terminal: bool) -> None:
        """Remember whether to answer as a terminal."""
        super().__init__()
        self._terminal = terminal

    def isatty(self) -> bool:
        """Say whether this is a terminal."""
        return self._terminal


class _Clock:
    """A clock a test sets by hand."""

    def __init__(self) -> None:
        """Start at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the time that was set."""
        return self.now


def test_a_run_that_has_not_started_shows_an_empty_bar() -> None:
    """Thirty characters between the brackets, the counts and the percentage."""
    assert progress_line(0, 8309, 0.0) == "[..............................] 0 of 8,309  0%"


def test_a_run_under_way_shows_how_far_it_is_and_how_long_is_left() -> None:
    """Half done after seven and a half minutes: about as long again."""
    assert progress_line(4150, 8300, 450.0) == (
        "[###############...............] 4,150 of 8,300  50%  about 8 min left"
    )


def test_the_last_stretch_is_under_a_minute() -> None:
    """No count of seconds that jumps about."""
    assert progress_line(8200, 8300, 820.0).endswith("98%  under a minute left")


def test_a_finished_run_shows_a_full_bar_and_no_time_left() -> None:
    """There is nothing left to estimate."""
    assert (
        progress_line(8309, 8309, 900.0) == "[##############################] 8,309 of 8,309  100%"
    )


@given(total=st.integers(min_value=1, max_value=10**6), data=st.data())
def test_the_bar_always_has_the_same_width(total: int, data: st.DataObject) -> None:
    """Whatever the counts, the bar itself is thirty characters."""
    done = data.draw(st.integers(min_value=0, max_value=total))

    bar = progress_line(done, total, 12.0).split("]")[0].removeprefix("[")

    assert len(bar) == 30
    assert set(bar) <= {"#", "."}


@given(total=st.integers(min_value=1, max_value=10**6), data=st.data())
def test_the_bar_never_goes_back(total: int, data: st.DataObject) -> None:
    """More done never shows as less filled."""
    done = data.draw(st.integers(min_value=0, max_value=total - 1))

    assert progress_line(done, total, 1.0).count("#") <= progress_line(done + 1, total, 1.0).count(
        "#"
    )


def test_every_update_redraws_the_same_line() -> None:
    """A carriage return and no line feed: nothing scrolls while the run goes on."""
    screen, clock = _Screen(terminal=True), _Clock()
    bar = ProgressBar(screen, clock)

    for done in (1, 2, 3):
        clock.now += 1.0
        bar.update(done, 4)

    drawn = screen.getvalue()
    assert "\n" not in drawn
    assert drawn.count("\r") == 3
    assert drawn.split("\r")[-1].startswith("[######################........] 3 of 4  75%")


def test_a_shorter_line_covers_the_longer_one_it_replaces() -> None:
    """The last update has no time left to show, and must wipe the one before."""
    screen, clock = _Screen(terminal=True), _Clock()
    bar = ProgressBar(screen, clock)
    clock.now = 600.0
    bar.update(1, 2)
    before = len(screen.getvalue().split("\r")[-1])

    bar.update(2, 2)

    last = screen.getvalue().split("\r")[-1]
    assert len(last) == before
    assert last.rstrip() == "[##############################] 2 of 2  100%"


def test_finishing_ends_the_line_once() -> None:
    """What the command prints next starts on a line of its own."""
    screen = _Screen(terminal=True)
    bar = ProgressBar(screen, _Clock())
    bar.update(1, 1)

    bar.finish()
    bar.finish()

    assert screen.getvalue().count("\n") == 1
    assert screen.getvalue().endswith("\n")


def test_a_bar_that_was_never_drawn_leaves_no_empty_line() -> None:
    """A run with nothing to do prints its counts and nothing else."""
    screen = _Screen(terminal=True)

    ProgressBar(screen, _Clock()).finish()

    assert screen.getvalue() == ""


def test_nothing_is_drawn_when_the_output_is_not_a_terminal() -> None:
    """A bar redrawn into a file or a log would be thousands of lines of noise."""
    screen = _Screen(terminal=False)
    bar = ProgressBar(screen, _Clock())

    bar.update(1, 2)
    bar.update(2, 2)
    bar.finish()

    assert screen.getvalue() == ""


def test_a_run_of_nothing_draws_nothing() -> None:
    """There is no percentage of nothing."""
    screen = _Screen(terminal=True)
    bar = ProgressBar(screen, _Clock())

    bar.update(0, 0)

    assert screen.getvalue() == ""
