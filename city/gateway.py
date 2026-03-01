"""
GOVARDHAN GATEWAY — The City Wall
===================================

ALL external input passes through MahaCompression before touching internal state.
This IS the security boundary.

Wired from steward-protocol:
- MahaCompression — sanitize input (any string → seed)
- Buddhi.think() — cognitive frame before routing
- MahaHeader — 72-byte routing header

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TypedDict

from vibe_core.mahamantra.adapters.compression import MahaCompression
from vibe_core.mahamantra.substrate.buddhi import get_buddhi

from city.addressing import CityAddressBook

logger = logging.getLogger("AGENT_CITY.GATEWAY")


MAX_PATHOGEN_COUNT = 50
MAX_PATHOGEN_LENGTH = 500

# Source classification: determines trust level for immune system
SOURCE_CLASSES = {
    "ci": "ci",  # CI/CD pipeline (authenticated via HMAC)
    "github": "ci",  # GitHub webhook
    "webhook": "ci",  # Generic webhook
    "local": "local",  # Local dev environment
    "dev": "local",  # Developer
    "agent": "agent",  # Agent-to-agent (authenticated via ECDSA)
    "moltbook": "agent",  # Moltbook social
    "federation": "agent",  # Federation relay
}


def _classify_source(source: str) -> str:
    """Classify source into trust tier: local, ci, agent, external."""
    source_lower = source.lower()
    for prefix, cls in SOURCE_CLASSES.items():
        if source_lower.startswith(prefix):
            return cls
    return "external"


class GatewayResult(TypedDict):
    """Result of processing input through the gateway."""

    seed: int
    source: str
    source_class: str
    source_address: int
    buddhi_function: str
    buddhi_chapter: int
    buddhi_mode: str
    buddhi_prana: int
    buddhi_is_alive: bool
    compressed_size: int
    input_size: int


@dataclass
class CityGateway:
    """Single entry point for ALL external input.

    Compress → Buddhi.think → Address Resolution.
    Nothing touches internal state without passing through here.
    """

    _address_book: CityAddressBook = field(default_factory=CityAddressBook)
    _compression: MahaCompression = field(default_factory=MahaCompression)
    _processed_count: int = 0

    @property
    def address_book(self) -> CityAddressBook:
        return self._address_book

    def process(self, input_text: str, source: str) -> GatewayResult:
        """Process external input through the gateway.

        Pipeline: Compress → Buddhi.think → Address Resolution.
        """
        # Step 1: MahaCompression — sanitize input to deterministic seed
        compressed = self._compression.compress(input_text)

        # Step 2: Buddhi — cognitive frame (what is this input about?)
        buddhi = get_buddhi()
        cognition = buddhi.think(input_text)

        # Step 3: Address resolution
        source_address = self._address_book.resolve(source)

        self._processed_count += 1

        result: GatewayResult = {
            "seed": compressed.seed,
            "source": source,
            "source_class": _classify_source(source),
            "source_address": source_address,
            "buddhi_function": cognition.function,
            "buddhi_chapter": cognition.chapter,
            "buddhi_mode": cognition.mode,
            "buddhi_prana": cognition.prana,
            "buddhi_is_alive": cognition.is_alive,
            "compressed_size": compressed.output_size,
            "input_size": compressed.input_size,
        }

        logger.debug(
            "Gateway processed input from %s: seed=%d, function=%s, chapter=%d",
            source,
            compressed.seed,
            cognition.function,
            cognition.chapter,
        )
        return result

    def validate_agent_message(
        self,
        from_agent: str,
        payload: bytes,
        signature_b64: str,
        public_key_pem: str,
    ) -> bool:
        """Verify agent-to-agent messages using ECDSA signature verification."""
        from city.identity import verify_ownership

        passport = {"public_key": public_key_pem}
        return verify_ownership(passport, payload, signature_b64)

    def ingest_github_webhook(self, payload: bytes, signature_header: str, secret: str) -> dict:
        """Verify and ingest a GitHub Webhook (Arsenal Telemetry).

        Requires `X-Hub-Signature-256` header to verify the HMAC.
        Secret MUST be non-empty — unauthenticated webhooks are rejected.
        """
        import hmac
        import hashlib
        import json

        if not secret:
            logger.warning("Gateway: Webhook secret is empty — rejecting unauthenticated input.")
            return {"status": "error", "message": "missing_secret"}

        if not signature_header or not signature_header.startswith("sha256="):
            logger.warning("Invalid GitHub webhook signature format.")
            return {"status": "error", "message": "invalid_signature_format"}

        expected_sig = hmac.new(
            secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
        ).hexdigest()

        provided_sig = signature_header[7:]  # Strip 'sha256='

        if not hmac.compare_digest(expected_sig, provided_sig):
            logger.warning("GitHub webhook HMAC verification failed.")
            return {"status": "error", "message": "signature_mismatch"}

        try:
            data = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            return {"status": "error", "message": "invalid_json"}

        # Optional: We only care about workflow_runs that completed and failed
        if "workflow_run" in data:
            action = data.get("action")
            conclusion = data["workflow_run"].get("conclusion")
            logger.info(
                "Gateway received GitHub workflow_run: action=%s conclusion=%s", action, conclusion
            )

            if action == "completed" and conclusion == "failure":
                run_id = data["workflow_run"]["id"]
                repo_name = data["repository"]["full_name"]
                return {
                    "status": "success",
                    "event": "workflow_run_failed",
                    "run_id": run_id,
                    "repo_name": repo_name,
                }

        return {"status": "success", "event": "ignored"}

    def fetch_github_artifact(self, repo_name: str, run_id: int, github_token: str) -> list[str]:
        """Fetch the pytest-json-report payload from a failed GitHub Actions run.

        Uses PyGithub to download the artifact and extract the traceback pathogens.
        """
        try:
            from github import Github
            import zipfile
            import io
            import json
            import urllib.request
        except ImportError:
            logger.error("PyGithub missing. Cannot retrieve Arsenal telemetry.")
            return []

        g = Github(github_token)
        try:
            repo = g.get_repo(repo_name)
            workflow_run = repo.get_workflow_run(run_id)

            # Find the pytest json report artifact
            target_artifact = None
            for artifact in workflow_run.get_artifacts():
                if "report" in artifact.name.lower() or "json" in artifact.name.lower():
                    target_artifact = artifact
                    break

            if not target_artifact:
                logger.warning("No JSON report artifact found for run %d in %s", run_id, repo_name)
                return []

            logger.info("Downloading Arsenal artifact: %s", target_artifact.name)

            # Download the artifact zip using urllib with the token auth
            req = urllib.request.Request(target_artifact.archive_download_url)
            req.add_header("Authorization", f"Bearer {github_token}")

            with urllib.request.urlopen(req) as response:
                zip_data = response.read()

            pathogens: list[str] = []
            with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                for filename in z.namelist():
                    if filename.endswith(".json"):
                        with z.open(filename) as f:
                            report = json.load(f)

                        for test in report.get("tests", []):
                            if test.get("outcome") == "failed":
                                crash = test.get("call", {}).get("crash", {})
                                path = crash.get("path", "")
                                msg = crash.get("message", "")
                                if path and msg:
                                    trimmed = f"CI Failure in {path}: {msg}"[:MAX_PATHOGEN_LENGTH]
                                    pathogens.append(trimmed)
                                    if len(pathogens) >= MAX_PATHOGEN_COUNT:
                                        break
                    if len(pathogens) >= MAX_PATHOGEN_COUNT:
                        break

            if len(pathogens) == MAX_PATHOGEN_COUNT:
                logger.warning(
                    "Pathogen limit reached (%d), remaining failures trimmed.", MAX_PATHOGEN_COUNT
                )
            logger.info("Extracted %d pathogens from GitHub Arsenal artifact.", len(pathogens))
            return pathogens

        except Exception as e:
            logger.error("Failed to fetch Arsenal artifact: %s", e)
            return []

    def stats(self) -> dict:
        """Gateway statistics."""
        return {
            "processed": self._processed_count,
            "address_book": self._address_book.stats(),
        }
