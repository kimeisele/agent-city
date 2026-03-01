import logging
import os
import threading
from datetime import datetime, timezone

from city.identity import AgentIdentity

logger = logging.getLogger("AGENT_CITY.SOCIAL")

MAX_MESSAGE_LENGTH = 4096

class SocialBroadcaster:
    """Agent City Sovereign Social Ledger.
    
    Senior implementation following the 'Herald' pattern:
    - Writes to ISO-dated files in broadcasts/
    - Enforces BROADCAST_LICENSE (Pokedex citizen status)
    """
    
    def __init__(self, broadcasts_dir: str = "broadcasts"):
        self.broadcasts_dir = broadcasts_dir
        self._lock = threading.Lock()
        os.makedirs(self.broadcasts_dir, exist_ok=True)

    def post(self, identity: AgentIdentity, pokedex, message: str):
        """Signs and appends a message to the daily log.
        
        Args:
            identity: The agent's cryptographic identity.
            pokedex: The Pokedex registry (MANDATORY for governance check).
            message: The message to broadcast (max MAX_MESSAGE_LENGTH chars).
        """
        # 1. Governance Check — Pokedex is MANDATORY, no bypass
        if pokedex is None:
            raise PermissionError("Pokedex is required for broadcast governance.")
        agent = pokedex.get(identity.agent_name)
        if not agent or agent.get("status") not in ("citizen", "active"):
            raise PermissionError(f"BROADCAST_LICENSE missing for {identity.agent_name}")

        # 2. Input sanitization
        if len(message) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message exceeds {MAX_MESSAGE_LENGTH} char limit ({len(message)})")
        safe_message = message.replace("\r", "")

        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        date_str = now.strftime("%Y-%m-%d")
        log_file = os.path.join(self.broadcasts_dir, f"{date_str}_sovereign_square.md")
        
        # 3. Sign the message (ECDSA — deterministic, OS-agnostic, no subprocess)
        signature = identity.sign(safe_message.encode())
        signed_msg = f"{safe_message}\n\n[Signature: {signature}]"

        post_block = f"""
## {identity.agent_name}
**Timestamp:** `{timestamp}`
**Identity:** `{identity.fingerprint}`

{signed_msg}

---
"""
        # 4. Thread-safe file append
        with self._lock:
            with open(log_file, "a") as f:
                f.write(post_block)
        
        return True
