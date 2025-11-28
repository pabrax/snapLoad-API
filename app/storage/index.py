import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "downloads.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


class DownloadIndex:
    def __init__(self):
        self.ensure_schema()

    def ensure_schema(self):
        con = _connect()
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS downloads (
                  url TEXT NOT NULL,
                  type TEXT NOT NULL,
                  quality TEXT,
                  format TEXT,
                  files_json TEXT,
                  status TEXT NOT NULL,
                  job_id TEXT,
                  created_at TEXT NOT NULL,
                  last_access TEXT,
                  error TEXT,
                  PRIMARY KEY (url, type, quality, format)
                )
                """
            )
            con.commit()
        finally:
            con.close()

    def lookup(self, url: str, type_: str, quality: Optional[str] = None, format_: Optional[str] = None) -> Optional[Dict[str, Any]]:
        con = _connect()
        try:
            cur = con.execute(
                "SELECT url,type,quality,format,files_json,status,job_id,created_at,last_access,error FROM downloads WHERE url=? AND type=? AND IFNULL(quality,'')=IFNULL(?, '') AND IFNULL(format,'')=IFNULL(?, '')",
                (url, type_, quality, format_),
            )
            row = cur.fetchone()
            if not row:
                return None
            rec = {
                "url": row[0],
                "type": row[1],
                "quality": row[2],
                "format": row[3],
                "files": json.loads(row[4]) if row[4] else [],
                "status": row[5],
                "job_id": row[6],
                "created_at": row[7],
                "last_access": row[8],
                "error": row[9],
            }
            if rec["status"] == "ready":
                missing = [p for p in rec["files"] if not Path(p).exists()]
                if missing:
                    con.execute(
                        "UPDATE downloads SET status='failed', error=? WHERE url=? AND type=? AND IFNULL(quality,'')=IFNULL(?, '') AND IFNULL(format,'')=IFNULL(?, '')",
                        (f"missing_files:{missing}", url, type_, quality, format_),
                    )
                    con.commit()
                    return None
            return rec
        finally:
            con.close()

    def register_pending(self, url: str, type_: str, quality: Optional[str], format_: Optional[str], job_id: str, created_at: str):
        con = _connect()
        try:
            con.execute(
                "INSERT OR REPLACE INTO downloads(url,type,quality,format,files_json,status,job_id,created_at,last_access,error) VALUES (?,?,?,?,?, 'pending', ?, ?, NULL, NULL)",
                (url, type_, quality, format_, json.dumps([]), job_id, created_at),
            )
            con.commit()
        finally:
            con.close()

    def register_success(self, job_id: str, files: List[str]):
        con = _connect()
        try:
            con.execute(
                "UPDATE downloads SET files_json=?, status='ready', error=NULL WHERE job_id=?",
                (json.dumps(files), job_id),
            )
            con.commit()
        finally:
            con.close()

    def register_failed(self, job_id: str, error: str):
        con = _connect()
        try:
            con.execute(
                "UPDATE downloads SET status='failed', error=? WHERE job_id=?",
                (error, job_id),
            )
            con.commit()
        finally:
            con.close()

    def touch(self, url: str, type_: str, quality: Optional[str], format_: Optional[str], last_access: str):
        con = _connect()
        try:
            con.execute(
                "UPDATE downloads SET last_access=? WHERE url=? AND type=? AND IFNULL(quality,'')=IFNULL(?, '') AND IFNULL(format,'')=IFNULL(?, '')",
                (last_access, url, type_, quality, format_),
            )
            con.commit()
        finally:
            con.close()


download_index = DownloadIndex()
