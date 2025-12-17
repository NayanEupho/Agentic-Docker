import os
import uuid
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

# Import the Database Repository
from .db import db

class Message(BaseModel):
    role: str
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

class Session(BaseModel):
    id: str
    title: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    messages: List[Message] = []
    
    @property
    def last_activity(self) -> str:
        if not self.messages:
            return self.created_at
        return self.messages[-1].timestamp

class SessionManager:
    """
    Manages active session state and delegates storage to the Database.
    """
    def __init__(self, active_session_file: str = ".agent_active_session"):
        self.active_session_file = active_session_file
        # No more self.sessions = {} (Stateless manager now)
        
        # Check if we need to migrate legacy JSON data
        self._check_migration()

    def _check_migration(self):
        """One-time migration from .agent_sessions.json to SQLite."""
        json_file = ".agent_sessions.json"
        if os.path.exists(json_file):
            # Optimization: Check DB first silently. If we have data, we don't need to migrate.
            if db.list_sessions():
                return 

            print("📦 Checking for legacy session data...")
            try:

                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                count = 0
                for session_id, s_data in data.items():
                    # Create Session
                    db.create_session(session_id, s_data.get("title") or f"Session {session_id}")
                    # Add Messages
                    for msg in s_data.get("messages", []):
                        db.add_message(session_id, msg["role"], msg["content"])
                    count += 1
                
                if count > 0:
                    print(f"✅ Migrated {count} sessions to Database.")
                    # Rename legacy file to avoid confusion? Or keep as backup.
                    # os.rename(json_file, json_file + ".bak") 
            except Exception as e:
                print(f"⚠️  Migration warning: {e}")

    def create_session(self, session_id: Optional[str] = None, title: Optional[str] = None) -> Session:
        """Create a new session via DB."""
        if not session_id:
            session_id = str(uuid.uuid4())[:8]
        
        if not title:
            title = f"Session {session_id}"

        # DB Create
        data = db.create_session(session_id, title)
        # Return Pydantic object
        return Session(**data)

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID via DB."""
        data = db.get_session(session_id)
        if data:
            return Session(**data)
        return None
        
    def set_active_session(self, session_id: str):
        """Mark a session as currently active globally."""
        try:
            with open(self.active_session_file, "w", encoding="utf-8") as f:
                f.write(session_id)
        except Exception as e:
            print(f"⚠️  Error setting active session: {e}")
            
    def get_active_session_id(self) -> Optional[str]:
        """Retrieve the currently active session ID."""
        if os.path.exists(self.active_session_file):
            try:
                with open(self.active_session_file, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                return None
        return None

    def clear_active_session(self):
        """Clear the active session state."""
        if os.path.exists(self.active_session_file):
            try:
                os.remove(self.active_session_file)
            except Exception as e:
                print(f"⚠️  Error clearing active session: {e}")

    def add_message(self, session_id: str, role: str, content: str):
        """Add a message via DB."""
        # Just delegate to DB
        db.add_message(session_id, role, content)

    def list_sessions(self) -> List[Session]:
        """List all sessions sorted by date via DB."""
        # The DB returns dicts with message_count
        # We need to map them to Session objects (messages list will be empty but that is okay for listing)
        rows = db.list_sessions()
        sessions = []
        for row in rows:
            # Reconstruct minimal session object
            s = Session(id=row["id"], title=row["title"], created_at=row["created_at"])
            # Hack: Manually set a dummy message to reflect last_activity for sorting UI if needed
            # But the DB already sorted them.
            # We can just return the objects.
            sessions.append(s)
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete a session via DB."""
        if db.delete_session(session_id):
            active_id = self.get_active_session_id()
            if active_id == session_id:
                self.clear_active_session()
            return True
        return False

    def clear_all(self):
        """Delete all sessions via DB."""
        db.clear_all_sessions()
        self.clear_active_session()

# Global instance
session_manager = SessionManager()
