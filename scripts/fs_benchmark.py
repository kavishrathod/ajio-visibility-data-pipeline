"""Measure the file-system and SQLite costs that dominate the test suite on this machine.

    python scripts/fs_benchmark.py

It times small operations in two places, the system temp folder (where pytest puts its temporary files) and a
folder inside the project, so a slow location or slow disk syncs show up as numbers instead of a guess:

* creating, writing and deleting small files (what the pipeline does for every raw page);
* committing to SQLite with its durable defaults (journal file created and deleted, disk sync);
* committing to SQLite the way the tests do (in-memory journal, no sync);
* opening and closing a connection.

It creates and removes its own scratch folders and touches nothing else.
"""
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

FILES, COMMITS, CONNECTS = 300, 100, 200


def timed(fn, count):
    start = time.perf_counter()
    fn()
    return (time.perf_counter() - start) * 1000 / count


def small_files(folder: Path):
    def run():
        for i in range(FILES):
            path = folder / f"f{i}.html"
            path.write_text("<html>" + "x" * 2000 + "</html>", encoding="utf-8")
            path.unlink()
    return run


def commits(folder: Path, fast: bool):
    def run():
        conn = sqlite3.connect(folder / ("fast.db" if fast else "durable.db"))
        if fast:
            conn.execute("PRAGMA journal_mode = MEMORY")
            conn.execute("PRAGMA synchronous = OFF")
        conn.execute("CREATE TABLE IF NOT EXISTS t (a INTEGER)")
        conn.commit()
        for i in range(COMMITS):
            conn.execute("INSERT INTO t VALUES (?)", (i,))
            conn.commit()
        conn.close()
    return run


def connects(folder: Path):
    def run():
        for _ in range(CONNECTS):
            sqlite3.connect(folder / "durable.db").close()
    return run


def measure(label: str, folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    try:
        return label, {
            f"create+write+delete a small file ({FILES}x)": timed(small_files(folder), FILES),
            f"SQLite commit, durable defaults ({COMMITS}x)": timed(commits(folder, False), COMMITS),
            f"SQLite commit, test mode ({COMMITS}x)": timed(commits(folder, True), COMMITS),
            f"open+close a connection ({CONNECTS}x)": timed(connects(folder), CONNECTS),
        }
    finally:
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    here = Path(__file__).resolve().parents[1] / ".fs_benchmark_scratch"
    results = [
        measure(f"system temp ({tempfile.gettempdir()})", Path(tempfile.gettempdir()) / "ajio_fs_benchmark"),
        measure(f"project folder ({here.parent})", here),
    ]
    width = max(len(name) for name in results[0][1])
    print(f"{'milliseconds per operation':<{width}}", *[f"{label[:34]:>36}" for label, _ in results], sep="  ")
    for name in results[0][1]:
        print(f"{name:<{width}}", *[f"{values[name]:>36.2f}" for _, values in results], sep="  ")
    durable = results[0][1][f"SQLite commit, durable defaults ({COMMITS}x)"]
    fast = results[0][1][f"SQLite commit, test mode ({COMMITS}x)"]
    print(f"\nTest mode commits are {durable / fast:.1f}x faster than durable commits in the system temp folder.")
    print("A large difference between the two columns means the location is the problem (for example antivirus "
          "scanning the temp folder); a large create+write+delete time in both means file creation itself is slow.")
