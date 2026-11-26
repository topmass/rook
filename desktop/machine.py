"""Small explicit state machine helper for Rook.

Run `python3 desktop/machine.py` to check the table and log behaviour.
"""
from enum import Enum


class Machine:
    """One explicit state: an Enum value, allowed moves, and a log call for moves the table lacks."""

    strict = False  # Checks set this to fail on untabled moves; live Rook only logs.

    def __init__(self, name, start, moves, log):
        self.name, self.state, self.moves, self.log = name, start, moves, log

    def to(self, new, why=""):
        old, self.state = self.state, new
        if new not in self.moves[old]:
            self.log("illegal_move", machine=self.name, old=old.name, new=new.name, why=why)
            if Machine.strict:
                raise AssertionError(f"{self.name}: {old.name} -> {new.name} ({why})")
        return old


def check():
    """Self-check allowed moves, log-only untabled moves, and strict mode."""

    class Sample(Enum):
        IDLE = 1
        RUNNING = 2
        DONE = 3

    moves = {
        Sample.IDLE: {Sample.RUNNING},
        Sample.RUNNING: {Sample.DONE},
        Sample.DONE: set(),
    }
    rows = []
    m = Machine("sample", Sample.IDLE, moves, lambda event, **fields: rows.append((event, fields)))
    assert m.state is Sample.IDLE
    assert m.to(Sample.RUNNING, "start") is Sample.IDLE and m.state is Sample.RUNNING
    assert m.to(Sample.DONE, "finish") is Sample.RUNNING and m.state is Sample.DONE
    assert rows == []

    saved = Machine.strict
    try:
        Machine.strict = False
        assert m.to(Sample.RUNNING, "late") is Sample.DONE and m.state is Sample.RUNNING
        assert rows == [("illegal_move", {"machine": "sample", "old": "DONE", "new": "RUNNING", "why": "late"})], rows
        rows.clear()
        Machine.strict = True
        try:
            m.to(Sample.IDLE, "bad")
            raise AssertionError("strict mode should raise on an untabled move")
        except AssertionError as exc:
            assert "sample: RUNNING -> IDLE (bad)" in str(exc), exc
        assert rows == [("illegal_move", {"machine": "sample", "old": "RUNNING", "new": "IDLE", "why": "bad"})], rows
    finally:
        Machine.strict = saved
    print("State machine helper: all checks passed.")


if __name__ == "__main__":
    check()
