"""Exercise the append-only Obsidian writer with a scratch vault."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
from obsidian_notes import append_daily_note


def check():
    with tempfile.TemporaryDirectory() as temp:
        vault = Path(temp)
        filename = f"{date.today().isoformat()}.md"
        daily = vault / "daily"
        daily.mkdir()
        personal_note = daily / filename
        personal_note.write_bytes(b"Original personal daily note")

        assert append_daily_note(vault, "First note") == f"rook/{filename}"
        notes = vault / "rook" / filename
        assert notes.read_bytes() == b"First note\n"
        with ThreadPoolExecutor() as pool:
            entries = [f"Entry {i}" for i in range(12)]
            list(pool.map(lambda text: append_daily_note(vault, text), entries))
        first, *rest = notes.read_text().strip().split("\n\n\n")
        assert first == "First note" and sorted(rest) == sorted(entries)

        assert append_daily_note(vault, "Custom", "Game notes") == f"Game notes/{filename}"
        assert (vault / "Game notes" / filename).read_text() == "Custom\n"
        (vault / "alias").symlink_to(daily, target_is_directory=True)
        for folder in ("daily", "DAILY", "../daily", "rook/subfolder", "rook\\daily", "alias"):
            try:
                append_daily_note(vault, "Do not save", folder)
            except (OSError, ValueError):
                pass
            else:
                raise AssertionError(f"Accepted unsafe destination: {folder}")
        assert personal_note.read_bytes() == b"Original personal daily note"
    print("Obsidian notes: default, custom, concurrent append, and daily isolation checks passed.")


if __name__ == "__main__":
    check()
