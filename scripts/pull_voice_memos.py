"""Pull Voice Memos off a USB-connected iPhone/iPad into a folder `stt ingest` reads.

Steve, 11/14: "is there a way I can have you transfer voice memos off my phone
for me if I plug it in to this pc? same q about ipad". Voice Memos aren't
exposed over USB as files, so this makes a local MobileBackup2 backup (kept to
the Voice Memos payloads with --only-regex) and copies the recordings out,
named by the title he gave each one in Voice Memos.

One-time: the Apple Devices app (Microsoft Store) for the USB driver, then plug
in and tap "Trust This Computer" + passcode on the device.

    .venv\\Scripts\\python.exe scripts\\pull_voice_memos.py            # every connected device
    .venv\\Scripts\\python.exe scripts\\pull_voice_memos.py --list     # just show what's connected
    ... --skip-backup     # re-extract from the last backup without touching the device
    ... --password P      # if the device has encrypted backups turned on

Output: uploads\\voice_memos\\<device name>\\<title>[ MM-DD-YY].m4a, plus a
.pulled.json ledger so each run copies only what's new. The date suffix is
added only when the title has no MM-DD-YY in it, so `stt ingest` dates it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable
AUDIO_EXT = {".m4a", ".qta", ".caf", ".wav", ".aac", ".mp3"}
APPLE_EPOCH = dt.datetime(2001, 1, 1, tzinfo=dt.timezone.utc)
DATE_IN_NAME = re.compile(r"\d{2}-\d{2}-\d{2}")


def pmd3(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-m", "pymobiledevice3", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


def devices() -> list[dict]:
    r = pmd3("usbmux", "list", check=False)
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        sys.exit(f"couldn't list devices (is the Apple Devices app installed?):\n{r.stdout}\n{r.stderr}")
    out = []
    for d in data:
        udid = d.get("UniqueDeviceID") or d.get("Identifier") or d.get("SerialNumber")
        if not udid or d.get("ConnectionType", "USB") not in ("USB", "usb"):
            continue
        out.append({"udid": udid, "name": d.get("DeviceName") or udid, "type": d.get("ProductType", "")})
    return out


def safe(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".")
    return name[:150] or "untitled"


def titles_from(db_path: Path) -> dict[str, dict]:
    """CloudRecordings.db: recording filename -> {title, date}."""
    out: dict[str, dict] = {}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(ZCLOUDRECORDING)")}
        if "ZPATH" not in cols:
            return out
        title_col = next((c for c in ("ZENCRYPTEDTITLE", "ZCUSTOMLABEL", "ZCUSTOMLABELFORSORTING") if c in cols), None)
        sel = ["ZPATH", title_col or "NULL", "ZDATE" if "ZDATE" in cols else "NULL"]
        for path, title, date in con.execute(f"SELECT {', '.join(sel)} FROM ZCLOUDRECORDING"):
            if not path:
                continue
            when = APPLE_EPOCH + dt.timedelta(seconds=float(date)) if date is not None else None
            out[Path(path).name] = {"title": title, "date": when}
    finally:
        con.close()
    return out


def extract(backup_root: Path, udid: str, dest: Path) -> list[Path]:
    bdir = backup_root / udid
    manifest = bdir / "Manifest.db"
    if not manifest.exists():
        sys.exit(f"no backup at {bdir} (run without --skip-backup)")
    con = sqlite3.connect(f"file:{manifest}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT fileID, domain, relativePath FROM Files "
                           "WHERE domain LIKE '%VoiceMemos%' AND flags = 1").fetchall()
    except sqlite3.DatabaseError as exc:
        sys.exit(f"can't read {manifest} ({exc}); if backups are encrypted, rerun with --password")
    finally:
        con.close()
    blob = lambda fid: bdir / fid[:2] / fid  # noqa: E731
    meta: dict[str, dict] = {}
    for fid, _dom, rel in rows:
        if rel.endswith("CloudRecordings.db") and blob(fid).exists():
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td) / "CloudRecordings.db"
                shutil.copy2(blob(fid), tmp)
                for side in ("-wal", "-shm"):  # pick up uncheckpointed rows if the backup carries them
                    sib = next((f for f, _d, r in rows if r.endswith("CloudRecordings.db" + side)), None)
                    if sib and blob(sib).exists():
                        shutil.copy2(blob(sib), Path(td) / ("CloudRecordings.db" + side))
                meta.update(titles_from(tmp))
    dest.mkdir(parents=True, exist_ok=True)
    ledger_path = dest / ".pulled.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {}
    taken = {v for v in ledger.values()}
    new: list[Path] = []
    for fid, _dom, rel in sorted(rows, key=lambda r: r[2]):
        src = blob(fid)
        if Path(rel).suffix.lower() not in AUDIO_EXT or rel in ledger or not src.exists():
            continue
        m = meta.get(Path(rel).name, {})
        when = m.get("date")
        if when is None:  # filenames look like "20250407 093012-ABCD1234.m4a"
            mm = re.match(r"(\d{8}) (\d{6})", Path(rel).name)
            when = dt.datetime.strptime("".join(mm.groups()), "%Y%m%d%H%M%S") if mm else None
        title = safe(m.get("title") or Path(rel).stem)
        if when and not DATE_IN_NAME.search(title):
            title += " " + when.astimezone().strftime("%m-%d-%y") if when.tzinfo else " " + when.strftime("%m-%d-%y")
        name, n = f"{title}{Path(rel).suffix.lower()}", 2
        while name in taken or (dest / name).exists():
            name, n = f"{title} ({n}){Path(rel).suffix.lower()}", n + 1
        out = dest / name
        shutil.copy2(src, out)
        if when:
            ts = when.timestamp()
            os.utime(out, (ts, ts))
        ledger[rel] = name
        taken.add(name)
        new.append(out)
    ledger_path.write_text(json.dumps(ledger, indent=1, ensure_ascii=False), encoding="utf-8")
    return new


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(REPO / "uploads" / "voice_memos"))
    ap.add_argument("--backups", default=str(Path.home() / "stt_device_backups"))
    ap.add_argument("--udid", help="only this device")
    ap.add_argument("--password", help="backup password, if encrypted backups are on")
    ap.add_argument("--skip-backup", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    backups = Path(a.backups)
    devs = devices() if not (a.skip_backup and a.udid) else [{"udid": a.udid, "name": a.udid, "type": ""}]
    if a.udid:
        devs = [d for d in devs if d["udid"] == a.udid] or [{"udid": a.udid, "name": a.udid, "type": ""}]
    if a.list or not devs:
        print("connected:" if devs else "no device connected over USB (plugged in, unlocked, trusted?)")
        for d in devs:
            print(f"  {d['name']}  ({d['type']})  {d['udid']}")
        return
    for d in devs:
        print(f"== {d['name']} ({d['type']})")
        if not a.skip_backup:
            backups.mkdir(parents=True, exist_ok=True)
            args = ["backup2", "backup", "--udid", d["udid"], "--only-regex", "VoiceMemos", "--patch-manifest"]
            if a.password:
                args += ["--password", a.password]
            print("   backing up the Voice Memos payloads (keep it plugged in and unlocked)...")
            r = subprocess.run([PY, "-m", "pymobiledevice3", *args, str(backups)])
            if r.returncode:
                sys.exit(f"backup failed for {d['name']} (exit {r.returncode})")
        new = extract(backups, d["udid"], Path(a.out) / safe(d["name"]))
        print(f"   {len(new)} new recording(s) -> {Path(a.out) / safe(d['name'])}")
        for p in new:
            print(f"     {p.name}")


if __name__ == "__main__":
    main()
