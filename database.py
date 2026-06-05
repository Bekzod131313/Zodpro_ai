"""
Database - SQLite orqali ma'lumotlar saqlash
"""

import sqlite3
from datetime import datetime, date
from typing import Optional, List, Dict, Any


class Database:
    def __init__(self, db_path: str = "otaplama.db"):
        self.db_path = db_path
        self.init_db()

    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Barcha jadvallarni yaratish"""
        with self.get_conn() as conn:
            conn.executescript("""
                -- Guruh turlari
                CREATE TABLE IF NOT EXISTS guruhlar (
                    chat_id     INTEGER PRIMARY KEY,
                    tur         TEXT NOT NULL,
                    nomi        TEXT,
                    qoshildi    TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- Zakazlar
                CREATE TABLE IF NOT EXISTS zakazlar (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id     INTEGER NOT NULL,
                    mijoz       TEXT NOT NULL,
                    summa       REAL NOT NULL,
                    obyekt      TEXT DEFAULT '—',
                    holat       TEXT DEFAULT 'faol',
                    qoshgan     TEXT,
                    qoshildi    TEXT DEFAULT CURRENT_TIMESTAMP,
                    yopildi     TEXT
                );

                -- Prixodlar
                CREATE TABLE IF NOT EXISTS prixodlar (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id     INTEGER NOT NULL,
                    postavshik  TEXT NOT NULL,
                    summa       REAL NOT NULL,
                    izoh        TEXT DEFAULT '—',
                    qoshgan     TEXT,
                    qoshildi    TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- Kassa
                CREATE TABLE IF NOT EXISTS kassa (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id     INTEGER NOT NULL,
                    tur         TEXT NOT NULL,
                    kim         TEXT NOT NULL,
                    summa       REAL NOT NULL,
                    izoh        TEXT DEFAULT '—',
                    qoshgan     TEXT,
                    qoshildi    TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- Ishchilar ballari
                CREATE TABLE IF NOT EXISTS balllar (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    username    TEXT NOT NULL,
                    ball        INTEGER NOT NULL,
                    sabab       TEXT DEFAULT '—',
                    admin       TEXT,
                    qoshildi    TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    # ===================== GURUHLAR =====================

    def set_group_type(self, chat_id: int, tur: str):
        with self.get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO guruhlar (chat_id, tur)
                VALUES (?, ?)
            """, (chat_id, tur))
            conn.commit()

    def get_group_type(self, chat_id: int) -> Optional[str]:
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT tur FROM guruhlar WHERE chat_id = ?", (chat_id,)
            ).fetchone()
            return row["tur"] if row else None

    # ===================== ZAKAZLAR =====================

    def add_zakaz(self, chat_id, mijoz, summa, obyekt, qoshgan) -> int:
        with self.get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO zakazlar (chat_id, mijoz, summa, obyekt, qoshgan)
                VALUES (?, ?, ?, ?, ?)
            """, (chat_id, mijoz, summa, obyekt, qoshgan))
            conn.commit()
            return cursor.lastrowid

    def close_zakaz(self, chat_id: int, mijoz: str) -> Optional[Dict]:
        with self.get_conn() as conn:
            row = conn.execute("""
                SELECT * FROM zakazlar
                WHERE chat_id = ? AND holat = 'faol'
                AND LOWER(mijoz) LIKE LOWER(?)
                ORDER BY qoshildi DESC LIMIT 1
            """, (chat_id, f"%{mijoz}%")).fetchone()

            if not row:
                return None

            conn.execute("""
                UPDATE zakazlar SET holat = 'yopilgan', yopildi = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), row["id"]))
            conn.commit()
            return dict(row)

    def get_zakaz_stats(self, chat_id: int) -> Dict:
        with self.get_conn() as conn:
            faol = conn.execute(
                "SELECT COUNT(*) as c FROM zakazlar WHERE chat_id = ? AND holat = 'faol'",
                (chat_id,)
            ).fetchone()["c"]

            yopilgan = conn.execute(
                "SELECT COUNT(*) as c FROM zakazlar WHERE chat_id = ? AND holat = 'yopilgan'",
                (chat_id,)
            ).fetchone()["c"]

            jami_summa = conn.execute(
                "SELECT COALESCE(SUM(summa), 0) as s FROM zakazlar WHERE chat_id = ?",
                (chat_id,)
            ).fetchone()["s"]

            return {"faol": faol, "yopilgan": yopilgan, "jami_summa": jami_summa}

    def get_zakaz_hisobot(self, chat_id: int, davr: str) -> Dict:
        with self.get_conn() as conn:
            if davr == "bugun":
                filter_sql = "AND DATE(qoshildi) = DATE('now')"
            else:
                filter_sql = "AND strftime('%Y-%m', qoshildi) = strftime('%Y-%m', 'now')"

            faol_rows = conn.execute(f"""
                SELECT * FROM zakazlar
                WHERE chat_id = ? AND holat = 'faol' {filter_sql}
                ORDER BY qoshildi DESC
            """, (chat_id,)).fetchall()

            yopilgan_rows = conn.execute(f"""
                SELECT * FROM zakazlar
                WHERE chat_id = ? AND holat = 'yopilgan' {filter_sql}
                ORDER BY yopildi DESC
            """, (chat_id,)).fetchall()

            jami_summa = sum(r["summa"] for r in faol_rows) + sum(r["summa"] for r in yopilgan_rows)
            yopilgan_summa = sum(r["summa"] for r in yopilgan_rows)

            return {
                "faol": len(faol_rows),
                "yopilgan": len(yopilgan_rows),
                "jami_summa": jami_summa,
                "yopilgan_summa": yopilgan_summa,
                "faollar": [dict(r) for r in faol_rows],
                "yopilganlar": [dict(r) for r in yopilgan_rows],
            }

    # ===================== PRIXODLAR =====================

    def add_prixod(self, chat_id, postavshik, summa, izoh, qoshgan) -> int:
        with self.get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO prixodlar (chat_id, postavshik, summa, izoh, qoshgan)
                VALUES (?, ?, ?, ?, ?)
            """, (chat_id, postavshik, summa, izoh, qoshgan))
            conn.commit()
            return cursor.lastrowid

    def get_prixod_stats(self, chat_id: int) -> Dict:
        with self.get_conn() as conn:
            bugun = conn.execute("""
                SELECT COALESCE(SUM(summa), 0) as s FROM prixodlar
                WHERE chat_id = ? AND DATE(qoshildi) = DATE('now')
            """, (chat_id,)).fetchone()["s"]

            oylik = conn.execute("""
                SELECT COALESCE(SUM(summa), 0) as s FROM prixodlar
                WHERE chat_id = ? AND strftime('%Y-%m', qoshildi) = strftime('%Y-%m', 'now')
            """, (chat_id,)).fetchone()["s"]

            return {"bugun": bugun, "oylik": oylik}

    def get_prixod_hisobot(self, chat_id: int, davr: str) -> Dict:
        with self.get_conn() as conn:
            if davr == "bugun":
                filter_sql = "AND DATE(qoshildi) = DATE('now')"
            else:
                filter_sql = "AND strftime('%Y-%m', qoshildi) = strftime('%Y-%m', 'now')"

            rows = conn.execute(f"""
                SELECT * FROM prixodlar
                WHERE chat_id = ? {filter_sql}
                ORDER BY qoshildi DESC
            """, (chat_id,)).fetchall()

            by_postavshik = {}
            for r in rows:
                p = r["postavshik"]
                if p not in by_postavshik:
                    by_postavshik[p] = {"postavshik": p, "summa": 0, "soni": 0}
                by_postavshik[p]["summa"] += r["summa"]
                by_postavshik[p]["soni"] += 1

            return {
                "soni": len(rows),
                "summa": sum(r["summa"] for r in rows),
                "postavshiklar": sorted(by_postavshik.values(), key=lambda x: x["summa"], reverse=True),
            }

    # ===================== KASSA =====================

    def add_kassa(self, chat_id, tur, kim, summa, izoh, qoshgan):
        with self.get_conn() as conn:
            conn.execute("""
                INSERT INTO kassa (chat_id, tur, kim, summa, izoh, qoshgan)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (chat_id, tur, kim, summa, izoh, qoshgan))
            conn.commit()

    def get_kassa_balans(self, chat_id: int) -> float:
        with self.get_conn() as conn:
            kirim = conn.execute(
                "SELECT COALESCE(SUM(summa), 0) as s FROM kassa WHERE chat_id = ? AND tur = 'kirim'",
                (chat_id,)
            ).fetchone()["s"]
            chiqim = conn.execute(
                "SELECT COALESCE(SUM(summa), 0) as s FROM kassa WHERE chat_id = ? AND tur = 'chiqim'",
                (chat_id,)
            ).fetchone()["s"]
            return kirim - chiqim

    def get_kassa_hisobot(self, chat_id: int, davr: str) -> Dict:
        with self.get_conn() as conn:
            if davr == "bugun":
                filter_sql = "AND DATE(qoshildi) = DATE('now')"
            else:
                filter_sql = "AND strftime('%Y-%m', qoshildi) = strftime('%Y-%m', 'now')"

            kirim_rows = conn.execute(f"""
                SELECT * FROM kassa WHERE chat_id = ? AND tur = 'kirim' {filter_sql}
                ORDER BY qoshildi DESC
            """, (chat_id,)).fetchall()

            chiqim_rows = conn.execute(f"""
                SELECT * FROM kassa WHERE chat_id = ? AND tur = 'chiqim' {filter_sql}
                ORDER BY qoshildi DESC
            """, (chat_id,)).fetchall()

            kirim = sum(r["summa"] for r in kirim_rows)
            chiqim = sum(r["summa"] for r in chiqim_rows)

            return {
                "kirim": kirim,
                "chiqim": chiqim,
                "balans": kirim - chiqim,
                "kirimlar": [dict(r) for r in kirim_rows],
                "chiqimlar": [dict(r) for r in chiqim_rows],
            }

    # ===================== BALLLAR =====================

    def add_ball(self, username: str, ball: int, sabab: str, admin: str):
        with self.get_conn() as conn:
            conn.execute("""
                INSERT INTO balllar (username, ball, sabab, admin)
                VALUES (?, ?, ?, ?)
            """, (username, ball, sabab, admin))
            conn.commit()

    def get_worker_balls(self, username: str) -> int:
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(ball), 0) as s FROM balllar WHERE LOWER(username) = LOWER(?)",
                (username,)
            ).fetchone()
            return row["s"]

    def get_reyting(self) -> List[Dict]:
        with self.get_conn() as conn:
            rows = conn.execute("""
                SELECT username, SUM(ball) as ball
                FROM balllar
                WHERE strftime('%Y-%m', qoshildi) = strftime('%Y-%m', 'now')
                GROUP BY LOWER(username)
                ORDER BY ball DESC
            """).fetchall()
            return [dict(r) for r in rows]

    # ===================== UMUMIY =====================

    def get_umumiy_stats(self) -> Dict:
        with self.get_conn() as conn:
            zakaz_faol = conn.execute(
                "SELECT COUNT(*) as c FROM zakazlar WHERE holat = 'faol'"
            ).fetchone()["c"]

            zakaz_yopilgan = conn.execute(
                "SELECT COUNT(*) as c FROM zakazlar WHERE holat = 'yopilgan'"
            ).fetchone()["c"]

            zakaz_summa = conn.execute(
                "SELECT COALESCE(SUM(summa), 0) as s FROM zakazlar WHERE holat = 'faol'"
            ).fetchone()["s"]

            prixod_oy = conn.execute("""
                SELECT COALESCE(SUM(summa), 0) as s FROM prixodlar
                WHERE strftime('%Y-%m', qoshildi) = strftime('%Y-%m', 'now')
            """).fetchone()["s"]

            kassa_kirim = conn.execute(
                "SELECT COALESCE(SUM(summa), 0) as s FROM kassa WHERE tur = 'kirim'"
            ).fetchone()["s"]

            kassa_chiqim = conn.execute(
                "SELECT COALESCE(SUM(summa), 0) as s FROM kassa WHERE tur = 'chiqim'"
            ).fetchone()["s"]

            return {
                "zakaz_faol": zakaz_faol,
                "zakaz_yopilgan": zakaz_yopilgan,
                "zakaz_summa": zakaz_summa,
                "prixod_oy": prixod_oy,
                "kassa_kirim": kassa_kirim,
                "kassa_chiqim": kassa_chiqim,
                "kassa_balans": kassa_kirim - kassa_chiqim,
            }
