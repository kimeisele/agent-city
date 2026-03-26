import json
import os

OUTBOX_FILE = "data/moltbook_outbox.json"

def _load_outbox() -> list:
    if not os.path.exists(OUTBOX_FILE):
        return[]
    try:
        with open(OUTBOX_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return[]

def _save_outbox(data: list) -> None:
    os.makedirs(os.path.dirname(OUTBOX_FILE), exist_ok=True)
    with open(OUTBOX_FILE, "w") as f:
        json.dump(data, f, indent=2)

def append_message(text: str, thread_id: str = "", metadata: dict = None) -> None:
    outbox = _load_outbox()
    outbox.append({
        "text": text,
        "thread_id": thread_id,
        "metadata": metadata or {},
        "status": "pending"
    })
    _save_outbox(outbox)

def get_pending_messages() -> list:
    outbox = _load_outbox()
    return[m for m in outbox if m.get("status") == "pending"]

def mark_as_sent(index: int) -> None:
    outbox = _load_outbox()
    pending_idx = 0
    for msg in outbox:
        if msg.get("status") == "pending":
            if pending_idx == index:
                msg["status"] = "sent"
                break
            pending_idx += 1
    _save_outbox(outbox)
