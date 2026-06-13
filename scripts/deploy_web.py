#!/usr/bin/env python3
from __future__ import annotations

import os
from ftplib import FTP
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"

FTP_HOST = os.environ["RQDB4AI_FTP_HOST"]
FTP_USER = os.environ["RQDB4AI_FTP_USER"]
FTP_PASS = os.environ["RQDB4AI_FTP_PASS"]
remote_dir = os.environ.get("RQDB4AI_FTP_REMOTE_DIR", "").strip()
if not remote_dir:
    raise RuntimeError("RQDB4AI_FTP_REMOTE_DIR is required, for example: web/<public-site-folder>")
REMOTE_DIR = tuple(
    part for part in remote_dir.split("/") if part
)
FILES = ("rqdb4ai.php", "config.php", "config.sample.php")


def main() -> None:
    for name in FILES:
        path = WEB_DIR / name
        if not path.is_file():
            raise RuntimeError(f"{path} がありません")

    ftp = FTP()
    ftp.encoding = "utf-8"
    ftp.connect(FTP_HOST, 21, timeout=15)
    ftp.login(FTP_USER, FTP_PASS)
    for part in REMOTE_DIR:
        try:
            ftp.cwd(part)
        except Exception:
            ftp.mkd(part)
            ftp.cwd(part)

    for name in FILES:
        print("Upload:", name)
        with (WEB_DIR / name).open("rb") as f:
            ftp.storbinary("STOR " + name, f)
    ftp.quit()
    print("done")


if __name__ == "__main__":
    main()
