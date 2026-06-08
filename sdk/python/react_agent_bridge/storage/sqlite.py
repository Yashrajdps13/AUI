import json
import logging
import os
import sqlite3
from typing import List
from react_agent_bridge.storage.base import BaseStore
from react_agent_bridge.core.transition.observation import TransitionObservation

logger = logging.getLogger("react_agent_bridge.storage.sqlite")


class SQLiteStore(BaseStore):
    """
    Persistent SQLite implementation of the observation store.
    Stores JSON representation of snapshots and indexes on type+target.
    """
    def __init__(self, db_path: str = "observations.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        dir_name = os.path.dirname(self.db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command_type TEXT,
                    command_target TEXT,
                    command_json TEXT,
                    state_before_json TEXT,
                    state_after_json TEXT,
                    ack_success INTEGER,
                    slots_changed_json TEXT,
                    time_to_settle_ms REAL,
                    session_id TEXT,
                    timestamp REAL
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cmd_target ON observations (command_type, command_target)"
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}")
        finally:
            conn.close()

    def save_observation(self, obs: TransitionObservation) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO observations (
                    command_type, command_target, command_json, state_before_json,
                    state_after_json, ack_success, slots_changed_json,
                    time_to_settle_ms, session_id, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                obs.command.get("type"),
                obs.command.get("target"),
                json.dumps(obs.command),
                json.dumps(obs.state_before),
                json.dumps(obs.state_after),
                1 if obs.ack_success else 0,
                json.dumps(obs.slots_changed),
                obs.time_to_settle_ms,
                obs.session_id,
                obs.timestamp
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save observation to SQLite: {e}")
        finally:
            conn.close()

    def get_observations(self, limit: int = 100) -> List[TransitionObservation]:
        conn = sqlite3.connect(self.db_path)
        obs_list = []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT command_json, state_before_json, state_after_json, ack_success,
                       slots_changed_json, time_to_settle_ms, session_id, timestamp
                FROM observations
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            for row in reversed(rows):
                obs_list.append(TransitionObservation(
                    command=json.loads(row[0]),
                    state_before=json.loads(row[1]),
                    state_after=json.loads(row[2]),
                    ack_success=bool(row[3]),
                    slots_changed=json.loads(row[4]),
                    time_to_settle_ms=row[5],
                    session_id=row[6],
                    timestamp=row[7]
                ))
        except Exception as e:
            logger.error(f"Failed to read observations from SQLite: {e}")
        finally:
            conn.close()
        return obs_list

    def query_observations_by_command(self, command_type: str, target: str) -> List[TransitionObservation]:
        conn = sqlite3.connect(self.db_path)
        obs_list = []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT command_json, state_before_json, state_after_json, ack_success,
                       slots_changed_json, time_to_settle_ms, session_id, timestamp
                FROM observations
                WHERE command_type = ? AND command_target = ?
                ORDER BY timestamp DESC
            """, (command_type, target))
            rows = cursor.fetchall()
            for row in rows:
                obs_list.append(TransitionObservation(
                    command=json.loads(row[0]),
                    state_before=json.loads(row[1]),
                    state_after=json.loads(row[2]),
                    ack_success=bool(row[3]),
                    slots_changed=json.loads(row[4]),
                    time_to_settle_ms=row[5],
                    session_id=row[6],
                    timestamp=row[7]
                ))
        except Exception as e:
            logger.error(f"Failed to query observations from SQLite: {e}")
        finally:
            conn.close()
        return obs_list

    def clear(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM observations")
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to clear SQLite observations: {e}")
        finally:
            conn.close()
