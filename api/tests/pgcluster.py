"""Throwaway PostgreSQL 16 cluster for tests.

Used when BK_TEST_DATABASE_URL is not set. Needs the PostgreSQL 16 server binaries
(initdb, pg_ctl) and the pgvector extension installed for that server
(Debian/Ubuntu: `apt-get install postgresql-16 postgresql-16-pgvector`).

PostgreSQL refuses to run as root; when the tests run as root the cluster is
started as the `postgres` OS user via runuser.

Also runnable by hand for local work:  python tests/pgcluster.py  (prints a URL, Ctrl-C stops)
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

PG_BIN_CANDIDATES = [os.environ.get("BK_PG_BIN", ""), "/usr/lib/postgresql/16/bin"]


def _pg_bin() -> Path:
    for cand in PG_BIN_CANDIDATES:
        if cand and (Path(cand) / "initdb").exists():
            return Path(cand)
    found = shutil.which("initdb")
    if found:
        return Path(found).parent
    raise RuntimeError(
        "PostgreSQL server binaries not found; set BK_PG_BIN or BK_TEST_DATABASE_URL"
    )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ThrowawayCluster:
    def __init__(self) -> None:
        self.bin = _pg_bin()
        self.as_root = os.geteuid() == 0
        self.dir = Path(tempfile.mkdtemp(prefix="bk-pg-"))
        self.data = self.dir / "data"
        self.port = _free_port()
        self.user = "postgres" if self.as_root else os.environ.get("USER", "postgres")
        if self.as_root:
            shutil.chown(self.dir, "postgres", "postgres")

    def _run(self, *args: str) -> None:
        cmd = list(args)
        if self.as_root:
            cmd = ["runuser", "-u", "postgres", "--", *cmd]
        subprocess.run(
            cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )

    def start(self) -> ThrowawayCluster:
        self._run(
            str(self.bin / "initdb"),
            "-D",
            str(self.data),
            "-U",
            self.user,
            "--auth=trust",
            "--encoding=UTF8",
            "--no-sync",
        )
        opts = (
            f"-p {self.port} -k {self.dir} -c listen_addresses=127.0.0.1 -c fsync=off"
        )
        self._run(
            str(self.bin / "pg_ctl"),
            "-D",
            str(self.data),
            "-o",
            opts,
            "-l",
            str(self.dir / "log"),
            "-w",
            "start",
        )
        return self

    def url(self, dbname: str = "postgres") -> str:
        return f"postgresql+psycopg://{self.user}@127.0.0.1:{self.port}/{dbname}"

    def stop(self) -> None:
        try:
            self._run(
                str(self.bin / "pg_ctl"),
                "-D",
                str(self.data),
                "-m",
                "immediate",
                "stop",
            )
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)


if __name__ == "__main__":
    c = ThrowawayCluster().start()
    print(c.url(), flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        c.stop()
