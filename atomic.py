import os
import time


def replace(temporary, path, *, attempts=10, delay=0.05):
    """os.replace, retried past transient Windows locks.

    On Windows a virus scanner or the search indexer can hold a freshly written
    file open for a few milliseconds. os.replace then fails with ACCESS_DENIED
    (WinError 5) or SHARING_VIOLATION (WinError 32), both of which surface as
    PermissionError and both of which clear on their own. Everywhere else the
    call is left exactly as it was.
    """
    for attempt in range(attempts):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if os.name != "nt" or attempt == attempts - 1:
                raise
            time.sleep(delay)


def demo():
    from pathlib import Path
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temp:
        root = Path(temp)
        destination = root / "settings.json"
        destination.write_text("old", encoding="utf-8")
        staged = root / ".settings.json.tmp"
        staged.write_text("new", encoding="utf-8")

        replace(staged, destination)
        assert destination.read_text(encoding="utf-8") == "new"
        assert not staged.exists()

        # A destination that cannot be written is still an error, not a hang.
        missing = root / "nope" / "settings.json"
        staged.write_text("new", encoding="utf-8")
        try:
            replace(staged, missing, attempts=2, delay=0)
        except OSError:
            pass
        else:  # pragma: no cover
            raise AssertionError("expected an error for an unwritable target")
    print("ok")


if __name__ == "__main__":
    demo()
