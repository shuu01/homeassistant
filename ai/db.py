import queue
import sqlite3
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Any

db_queue = queue.Queue()
response = queue.Queue()

@dataclass
class DbRequest:
    sql: str
    params: tuple = ()
    fetch: str | None = None      # None, "one", or "all"
    response: queue.Queue | None = None

def db_worker(db_path):
    conn = sqlite3.connect(db_path)
    try:
        initialize_database(conn)
        while True:
            request = db_queue.get()

            if request is None:
                break
            try:
                cursor = conn.execute(request.sql, request.params)
                if request.fetch == "one":
                    result = cursor.fetchone()
                elif request.fetch == "all":
                    result = cursor.fetchall()
                else:
                    conn.commit()
                    result = None

                if request.response:
                    request.response.put(result)

            except Exception as e:
                if request.response:
                    request.response.put(e)

    finally:
        conn.close()


def initialize_database(conn):
    schema = Path("schema.sql").read_text()

    conn.executescript(schema)
    conn.commit()


def get_facts():
    db_queue.put(
        DbRequest("SELECT * FROM facts", fetch="all", response=response)
    )
    rows = response.get()
    return rows


def update_facts(facts):
    for fact in facts:
        db_queue.put(
            DbRequest("INSERT INTO facts (fact) VALUES (?)", (fact,))
        )

def get_messages(limit=20):
    db_queue.put(
        DbRequest(
            """
            select role, text from (
              select id, role, text
              from messages
              order by id
              desc limit ?
            ) order by id asc
            """,
            (limit,),
            fetch="all",
            response=response
        )
    )
    rows = response.get()
    return rows

def update_messages(text):
    db_queue.put(
        DbRequest("INSERT INTO facts(text) VALUES (?)", (text,))
    )
