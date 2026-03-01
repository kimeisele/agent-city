"""
CommitAuthority - Cryptographic Git Integration
===============================================

Provides the "Arsenal" level single point of commit execution
for Agent City with OPUS-092 gracefully degrading GPG signatures.
"""

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("AGENT_CITY.GIT")


class CommitAuthority:
    """The single point of commit execution for Agent City.
    
    Enforces OPUS-092: Graceful GPG Degradation.
    If a GPG key is available, commits are cryptographically verified (-S).
    If no key is found, falls back to standard commits.
    """

    def __init__(self, workspace: Optional[Path] = None):
        self._workspace = workspace or Path.cwd()
        self._gpg_available = self._check_gpg_key_available()
        
    def _check_gpg_key_available(self) -> bool:
        """Verify if a GPG key is loaded and available for signing."""
        try:
            # Check if gpg is installed and has secret keys
            result = subprocess.run(
                ["gpg", "--list-secret-keys"],
                cwd=str(self._workspace),
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0 and "sec " in result.stdout:
                logger.info("CommitAuthority: GPG Secret Key found. Commits WILL be verified.")
                return True
                
            logger.warning(
                "CommitAuthority: No GPG Secret Key found. "
                "Commits will NOT be verified. (OPUS-092 Graceful Degradation)"
            )
            return False
            
        except FileNotFoundError:
            logger.warning(
                "CommitAuthority: GPG is not installed on this system. "
                "Commits will NOT be verified."
            )
            return False

    def is_dirty(self) -> bool:
        """Check if the workspace has uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self._workspace),
                capture_output=True,
                text=True,
                check=True
            )
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False

    def stage(self, paths: List[str]) -> bool:
        """Stage specific paths for commit."""
        try:
            subprocess.run(
                ["git", "add"] + paths,
                cwd=str(self._workspace),
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to stage files: {e}")
            return False

    def commit(self, message: str, paths: Optional[List[str]] = None, force_unsigned: bool = False) -> bool:
        """Execute a commit, signing with GPG if available and not forced off."""
        if paths:
            self.stage(paths)
            
        if not self.is_dirty():
            logger.info("CommitAuthority: Nothing to commit.")
            return True
            
        cmd = ["git", "commit", "-m", message]
        
        # OPUS-092: Apply GPG Signature if available
        if self._gpg_available and not force_unsigned:
            cmd.append("-S")
            logger.debug("CommitAuthority: Applying GPG Verification (-S)")
            
        try:
            subprocess.run(
                cmd,
                cwd=str(self._workspace),
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"CommitAuthority: Successfully committed '{message}'")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"CommitAuthority: Commit failed: {e.stderr}")
            return False
