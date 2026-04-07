import json
import os
from datetime import datetime
from typing import List, Dict, Any

FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), "../data/feedback.jsonl")

def get_all_feedback() -> List[Dict[str, Any]]:
    """Read all feedback entries from the JSONL file."""
    if not os.path.exists(FEEDBACK_FILE):
        return []
    
    feedbacks = []
    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    feedbacks.append(json.loads(line))
                except:
                    continue
    return feedbacks

def delete_feedback_by_index(index: int) -> bool:
    """Delete a feedback entry by its index in the file. Returns True on success."""
    feedbacks = get_all_feedback()
    if 0 <= index < len(feedbacks):
        del feedbacks[index]
        
        # Rewrite the file
        os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            for fb in feedbacks:
                f.write(json.dumps(fb, ensure_ascii=False) + "\n")
        return True
    return False

def add_feedback_entry(entry: Dict[str, Any]):
    """Append a new feedback entry to the JSONL file."""
    os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
