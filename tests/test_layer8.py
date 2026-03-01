"""Layer 8 Tests — The 8th Dimension (Steward-Protocol Arsenal & Chaos Engineering).

Linked to GitHub Issue #15.
"""

import shutil
import tempfile
import time
from pathlib import Path

from city.daemon import DaemonService
from city.gateway import CityGateway
from city.mayor import Mayor
from city.network import CityNetwork
from city.pokedex import Pokedex
from vibe_core.cartridges.system.civic.tools.economy import CivicBank
def test_prahlad_survives_hiranyakashipu():
    """RED TEST: The domain-native chaos engineering dynamic.
    Hiranyakashipu (Anti-pattern) attacks by refusing to yield resource/CPU.
    Prahlad (Resilience) must detect the starvation, absorb the attack, and recover.
    """
    from vibe_core.protocols.mahajanas.bali.yield_cpu import Hiranyakashipu
    from city.registry import CityServiceRegistry
    
    # The Attack
    demon = Hiranyakashipu()
    assert demon.yield_cpu().yielded is False, "Hiranyakashipu must refuse to yield"
    
    # The System
    registry = CityServiceRegistry()
    
    # Layer 8 Boot (Simulating heartbeat.py wiring)
    try:
        from vibe_core.naga.services.prahlad.service import PrahladService
        prahlad = PrahladService()
        registry.register("prahlad", prahlad)
    except ImportError:
        pass
    
    # Prahlad (The Defender) should be registered to absorb this
    assert registry.has("prahlad"), "Diamond Protocol RED: Prahlad is not protecting the system"


def test_daemon_heartbeat_frequency():
    """GREEN TEST: DaemonService maintains long-running heartbeat with entropy-based frequency."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db_path = tmp / "city.db"
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pokedex = Pokedex(db_path=str(db_path), bank=bank)
        gateway = CityGateway()
        network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

        mayor = Mayor(
            _pokedex=pokedex,
            _gateway=gateway,
            _network=network,
            _state_path=tmp / "mayor_state.json",
            _offline_mode=True,
        )

        # Set 10Hz to make the test extremely fast
        daemon = DaemonService(mayor=mayor, frequency_hz=10.0)
        
        # Non-blocking start
        daemon.start(block=False)
        time.sleep(0.3)  # Let it run for ~3 cycles
        daemon.stop()
        
        # Mayor should have advanced its heartbeat
        assert mayor._heartbeat_count >= 1
    finally:
        shutil.rmtree(tmp)


def test_arsenal_gateway_integration():
    """GREEN TEST: The city gateway must integrate with the Steward Protocol Arsenal."""
    import json
    import hmac
    import hashlib
    
    gateway = CityGateway()
    secret = "my_arsenal_secret"
    
    payload_dict = {
        "action": "completed",
        "workflow_run": {
            "id": 849302,
            "conclusion": "failure"
        },
        "repository": {
            "full_name": "kimeisele/agent-city"
        }
    }
    payload_bytes = json.dumps(payload_dict).encode("utf-8")
    
    # 3. Cryptographic Signature
    sig = hmac.new(secret.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256).hexdigest()
    sig_header = f"sha256={sig}"
    
    # 4. Gateway Ingests Arsenal Webhook
    result = gateway.ingest_github_webhook(payload_bytes, sig_header, secret)
    
    # 5. Assertions
    assert result["status"] == "success"
    assert result["event"] == "workflow_run_failed"
    assert result["run_id"] == 849302
    assert result["repo_name"] == "kimeisele/agent-city"


def test_8th_dimension_telemetry(monkeypatch):
    """GREEN TEST: Cross-dimension telemetry between agent-city and steward routing.
    
    Proves that the Gateway can fetch Arsenal JSON artifacts using a GitHub token
    and extract the traceback payloads as actionable Pathogens.
    """
    import sys
    import json
    import zipfile
    import io
    from unittest.mock import MagicMock
    from city.gateway import CityGateway
    
    # 1. Setup Mock PyGithub
    mock_github = MagicMock()
    mock_g = MagicMock()
    mock_repo = MagicMock()
    mock_run = MagicMock()
    mock_artifact = MagicMock()
    
    mock_artifact.name = "pytest-json-report"
    mock_artifact.archive_download_url = "http://fake-artifact-url"
    mock_run.get_artifacts.return_value = [mock_artifact]
    mock_repo.get_workflow_run.return_value = mock_run
    mock_g.get_repo.return_value = mock_repo
    mock_github.Github.return_value = mock_g
    
    sys.modules["github"] = mock_github
    
    # 2. Setup Mock Artifact Download (Zip File parsing)
    report_data = {
        "tests": [
            {
                "outcome": "failed",
                "call": {
                    "crash": {
                        "path": "tests/test_layer8.py",
                        "message": "Chaos Engineering Vulnerability"
                    }
                }
            }
        ]
    }
    
    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, mode="w") as zf:
        zf.writestr(".report.json", json.dumps(report_data))
        
    class MockResponse:
        def __init__(self, data):
            self.data = data
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return self.data
        
    def mock_urlopen(request):
        return MockResponse(mem_zip.getvalue())
        
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    # 3. Execute the Gateway Telemetry Retrieval
    gateway = CityGateway()
    pathogens = gateway.fetch_github_artifact("steward/repo", 999, "fake_token")
    
    # 4. Assert Tracebacks were extracted cleanly as Pathogen payloads
    assert len(pathogens) == 1
    assert "tests/test_layer8.py" in pathogens[0]
    assert "Chaos Engineering Vulnerability" in pathogens[0]
    
    # Cleanup mock
    del sys.modules["github"]

def test_commit_authority_gpg(monkeypatch, tmp_path):
    """GREEN TEST: GitStateAuthority enforces GPG verification when available,
    and predictably degrades when GPG is missing/disabled. (OPUS-092)
    """
    from city.git_client import GitStateAuthority
    import subprocess
    
    # 1. Init a fake git repo in tmp_path
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@agent.city"], cwd=str(tmp_path), check=True)
    
    # 2. Mock GPG sign test to simulate NO GPG available
    original_run = subprocess.run
    def mock_run_no_gpg(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if isinstance(cmd, list) and "--sign" in cmd and "gpg" in cmd[0]:
            return subprocess.CompletedProcess(cmd, 2, stdout=b"", stderr=b"no key")
        return original_run(*args, **kwargs)
        
    monkeypatch.setattr(subprocess, "run", mock_run_no_gpg)
    
    # 3. Instantiate GitStateAuthority
    ca_no_gpg = GitStateAuthority(workspace=tmp_path)
    assert ca_no_gpg._gpg_available is False, "GitStateAuthority should realize GPG is missing"
    
    # 4. Mock GPG sign test to simulate ACTIVE GPG
    def mock_run_yes_gpg(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if isinstance(cmd, list) and "--sign" in cmd and "gpg" in cmd[0]:
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        return original_run(*args, **kwargs)
        
    monkeypatch.setattr(subprocess, "run", mock_run_yes_gpg)
    
    # 5. Instantiate GitStateAuthority
    ca_yes_gpg = GitStateAuthority(workspace=tmp_path)
    assert ca_yes_gpg._gpg_available is True, "GitStateAuthority should detect the active GPG key"
    
    # 6. Test a mock commit flow using `ca_yes_gpg` (we just intercept the final `git commit`)
    commit_cmd_called = []
    
    def mock_run_intercept_commit(*args, **kwargs):
        if args[0][:2] == ["git", "commit"]:
            commit_cmd_called.append(args[0])
            return subprocess.CompletedProcess(args[0], 0, stdout="[main xxx] test", stderr="")
        if args[0][:2] == ["git", "status"]:
            return subprocess.CompletedProcess(args[0], 0, stdout="M  test.txt\n", stderr="")
        return subprocess.run(*args, **kwargs)
        
    monkeypatch.setattr(subprocess, "run", mock_run_intercept_commit)
    
    # Attempt a commit that SHOULD use GPG
    ca_yes_gpg.commit("Test signed commit")
    assert "-S" in commit_cmd_called[0], "GitStateAuthority MUST inject -S for GPG verified commits"
    
    # Attempt a commit that is FORCED unsigned
    commit_cmd_called.clear()
    ca_yes_gpg.commit("Test forced unsigned", force_unsigned=True)
    assert "-S" not in commit_cmd_called[0], "GitStateAuthority MUST respect force_unsigned"


