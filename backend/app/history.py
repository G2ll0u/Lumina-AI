import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

DB_PATH = os.path.join(os.path.dirname(__file__), "../chat_history.db")

class MessageModel(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str
    sourceNodes: Optional[List[Dict[str, Any]]] = None

class SessionModel(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[MessageModel]

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table for sessions
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    ''')
    
    # Table for messages
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        source_nodes TEXT, -- JSON stored as text
        created_at TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
    )
    ''')
    
    conn.commit()
    conn.close()

def create_session(session_id: str, title: str = "Nouvelle conversation") -> str:
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (session_id, title, now, now)
    )
    conn.commit()
    conn.close()
    return session_id

def get_session(session_id: str) -> Optional[SessionModel]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    session_row = cursor.fetchone()
    if not session_row:
        conn.close()
        return None
        
    cursor.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,))
    message_rows = cursor.fetchall()
    conn.close()
    
    messages = []
    for msg in message_rows:
        source_nodes = None
        if msg["source_nodes"]:
            try:
                source_nodes = json.loads(msg["source_nodes"])
            except:
                pass
        
        messages.append(MessageModel(
            id=str(msg["id"]),
            role=msg["role"],
            content=msg["content"],
            timestamp=msg["created_at"],
            sourceNodes=source_nodes
        ))
        
    return SessionModel(
        id=session_row["id"],
        title=session_row["title"],
        created_at=session_row["created_at"],
        updated_at=session_row["updated_at"],
        messages=messages
    )

def get_all_sessions() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def update_session_title(session_id: str, title: str):
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?", (title, now, session_id))
    conn.commit()
    conn.close()

def delete_session(session_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Due to CASCADE, deleting session deletes messages
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

def add_message(session_id: str, role: str, content: str, source_nodes: Optional[List[Dict[str, Any]]] = None):
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure session exists
    cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
    if not cursor.fetchone():
        # Title can be generated from the first message later or simply "Nouvelle conversation"
        cursor.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, "Nouvelle conversation", now, now)
        )
    
    source_nodes_json = json.dumps(source_nodes) if source_nodes else None
    
    cursor.execute(
        "INSERT INTO messages (session_id, role, content, source_nodes, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, source_nodes_json, now)
    )
    
    # Update session updated_at
    cursor.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    
    conn.commit()
    conn.close()

def get_message_context(message_id: str) -> Optional[Dict[str, Any]]:
    """
    Récupère un message par son ID (numérique) ainsi que le message précédent (la question)
    et les sources associées.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Récupérer le message en question
    cursor.execute("SELECT * FROM messages WHERE id = ?", (message_id,))
    msg = cursor.fetchone()
    if not msg:
        conn.close()
        return None
    
    # 2. Retrieve the previous message (the user's question)
    # Message IDs are sequential and auto-incremented in this system.
    cursor.execute(
        "SELECT * FROM messages WHERE session_id = ? AND id < ? ORDER BY id DESC LIMIT 1", 
        (msg["session_id"], msg["id"])
    )
    prev_msg = cursor.fetchone()
    
    conn.close()
    
    return {
        "answer": msg["content"],
        "question": prev_msg["content"] if prev_msg else "Inconnue",
        "source_nodes": json.loads(msg["source_nodes"]) if msg["source_nodes"] else [],
        "session_id": msg["session_id"],
        "timestamp": msg["created_at"]
    }
