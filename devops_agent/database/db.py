import sqlite3
import json
import os
from typing import List, Dict, Optional, Any
from datetime import datetime

# Database file path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "devops_agent.db")

class SessionRepository:
    """
    Handles all database interactions for Sessions and Messages.
    Uses SQLite but keeps SQL isolated to allow future migration.
    """
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        """Get a connection to the SQLite database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Access columns by name
        return conn

    def _init_db(self):
        """Initialize the database schema if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Sessions Table
        # context_state: JSON string for storing active state (e.g. last pod, etc.)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                last_activity TEXT,
                context_state TEXT
            )
        ''')

        # Messages Table
        # Stores every interaction (User query, Agent response, System output)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                timestamp TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        ''')
        
        conn.commit()
        conn.close()

    def create_session(self, session_id: str, title: str) -> Dict[str, Any]:
        """Create a new session."""
        created_at = datetime.now().isoformat()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO sessions (id, title, created_at, last_activity, context_state) VALUES (?, ?, ?, ?, ?)",
            (session_id, title, created_at, created_at, "{}")
        )
        
        conn.commit()
        conn.close()
        
        return {
            "id": session_id,
            "title": title,
            "created_at": created_at,
            "messages": [],
            "last_activity": created_at,
            "context_state": {}
        }

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a session and its messages by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        session_row = cursor.fetchone()
        
        if not session_row:
            conn.close()
            return None
            
        # Get messages for this session
        cursor.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,))
        message_rows = cursor.fetchall()
        
        conn.close()
        
        messages = []
        for row in message_rows:
            messages.append({
                "role": row["role"],
                "content": row["content"],
                "timestamp": row["timestamp"]
            })
            
        return {
            "id": session_row["id"],
            "title": session_row["title"],
            "created_at": session_row["created_at"],
            "messages": messages,
            "last_activity": session_row["last_activity"],
            "context_state": json.loads(session_row["context_state"] or "{}")
        }

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions ordered by last activity."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM sessions ORDER BY last_activity DESC")
        rows = cursor.fetchall()
        
        sessions = []
        for row in rows:
            # For list view, we just need the count of messages, not content
            cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (row["id"],))
            msg_count = cursor.fetchone()[0]
            
            sessions.append({
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "last_activity": row["last_activity"],
                "message_count": msg_count
            })
            
        conn.close()
        return sessions

    def add_message(self, session_id: str, role: str, content: str):
        """Add a message to a session and update last_activity."""
        timestamp = datetime.now().isoformat()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (session_id, role, content, timestamp)
            )
            
            # Update session last_activity
            cursor.execute(
                "UPDATE sessions SET last_activity = ? WHERE id = ?",
                (timestamp, session_id)
            )
            
            conn.commit()
        except Exception as e:
            print(f"⚠️  Database error adding message: {e}")
        finally:
            conn.close()

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        return deleted

    def clear_all_sessions(self):
        """Delete all sessions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions")
        conn.commit()
        conn.close()

# Global instance
db = SessionRepository()
