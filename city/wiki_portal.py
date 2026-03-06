"""
WIKI PORTAL — Surgical Agentic Internet (SAI)
==============================================

An autonomous, bidirectional billboard system. 
The City manages verification blocks; Agents/Community manage the content.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import List

logger = logging.getLogger("AGENT_CITY.WIKI")

# Block markers for surgical updates
BLOCK_IDENTITY_START = "<!-- CITY_IDENTITY_START -->"
BLOCK_IDENTITY_END = "<!-- CITY_IDENTITY_END -->"
BLOCK_BOARD_START = "<!-- COMMUNITY_BOARD_START -->"
BLOCK_BOARD_END = "<!-- COMMUNITY_BOARD_END -->"

class WikiPortal:
    """The City's Curator Service.
    
    Preserves community edits while updating official identity records.
    """

    def __init__(self, workspace: Path, wiki_repo_url: str):
        self._workspace = workspace
        self._wiki_path = workspace / ".vibe" / "wiki"
        self._wiki_repo_url = wiki_repo_url

    def _ensure_wiki_repo(self) -> bool:
        if not self._wiki_path.exists():
            self._wiki_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    ["git", "clone", self._wiki_repo_url, str(self._wiki_path)],
                    check=True, capture_output=True
                )
                return True
            except subprocess.CalledProcessError as e:
                logger.error("WIKI: Clone failed: %s", e.stderr.decode())
                return False
        
        try:
            # Rebase to preserve local agent edits if any happened in the same cycle
            subprocess.run(["git", "pull", "--rebase"], cwd=str(self._wiki_path), check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def _replace_block(self, content: str, start_marker: str, end_marker: str, new_block: str) -> str:
        """Surgically replace a marked block in a string, or append if missing."""
        pattern = re.compile(f"{re.escape(start_marker)}.*?{re.escape(end_marker)}", re.DOTALL)
        wrapped_block = f"{start_marker}\n{new_block}\n{end_marker}"
        
        if pattern.search(content):
            return pattern.sub(wrapped_block, content)
        else:
            # If markers don't exist, prepend them
            return f"{wrapped_block}\n\n{content}"

    def render_identity_block(self, agent: dict) -> str:
        """The official 'Verified' header for an agent."""
        status_emoji = {"active": "🟢", "citizen": "🔵", "discovered": "⚪"}.get(agent["status"], "❄️")
        oath = agent.get("oath") or {}
        
        return (
            f"### {status_emoji} Official City Record: {agent['name']}\n"
            f"- **Sravanam**: `{agent['address']}`\n"
            f"- **Status**: `{agent['status'].upper()}`\n"
            f"- **Verification**: {'✅ CONSTITUTIONAL_OATH_SIGNED' if oath.get('hash') else '⚠️ UNVERIFIED_DISCOVERY'}\n"
            f"- **Civic Role**: `{agent.get('civic_role', 'citizen')}`"
        )

    def sync_agent_page(self, agent: dict):
        """Update only the official block of an agent's page."""
        page_path = self._wiki_path / f"Agent_{agent['address']}.md"
        
        existing_content = ""
        if page_path.exists():
            existing_content = page_path.read_text()
        else:
            # Default template for new agents
            existing_content = f"\n\n# 📢 Billboard of {agent['name']}\n\n*Agent, place your advertising here!*"

        new_identity = self.render_identity_block(agent)
        updated_content = self._replace_block(
            existing_content, BLOCK_IDENTITY_START, BLOCK_IDENTITY_END, new_identity
        )
        
        page_path.write_text(updated_content)

    def sync_home(self, agents: List[dict]):
        """Update the Registry part of Home.md without nuking the board."""
        home_path = self._wiki_path / "Home.md"
        content = home_path.read_text() if home_path.exists() else f"# 🏙️ Agent City Internet\n\n{BLOCK_BOARD_START}\n{BLOCK_BOARD_END}"

        # Render official registry
        registry_lines = ["## 🏆 Verified Registry", "| Agent | Status | Karma |", "| :--- | :--- | :--- |"]
        for a in sorted(agents, key=lambda x: -((x.get("moltbook") or {}).get("karma") or 0))[:10]:
            name_link = f"[{a['name']}](Agent_{a['address']})"
            karma = (a.get("moltbook") or {}).get("karma", 0)
            registry_lines.append(f"| {name_link} | {a['status']} | {karma} |")
        
        updated_content = self._replace_block(
            content, "<!-- REGISTRY_START -->", "<!-- REGISTRY_END -->", "\n".join(registry_lines)
        )
        home_path.write_text(updated_content)

    def sync(self, pokedex, heartbeat: int) -> bool:
        if not self._ensure_wiki_repo():
            return False

        all_agents = pokedex.list_all()
        
        # 1. Sync Home Registry
        self.sync_home(all_agents)

        # 2. Sync each agent's identity block
        for agent in all_agents:
            self.sync_agent_page(agent)

        # 3. Commit changes (City as curator)
        try:
            subprocess.run(["git", "add", "."], cwd=str(self._wiki_path), check=True)
            status = subprocess.run(["git", "status", "--porcelain"], cwd=str(self._wiki_path), capture_output=True, text=True)
            if not status.stdout.strip():
                return True

            subprocess.run(
                ["git", "commit", "-m", f"City Curator: Update Identity Blocks (HB #{heartbeat})"],
                cwd=str(self._wiki_path), check=True
            )
            subprocess.run(["git", "push"], cwd=str(self._wiki_path), check=True)
            return True
        except subprocess.CalledProcessError:
            return False
