import pytest
from datetime import datetime, timezone
from city.social import SocialBroadcaster, MAX_MESSAGE_LENGTH
from city.pokedex import Pokedex
from city.jiva import derive_jiva
from city.identity import generate_identity

def test_social_unauthorized_post(tmp_path):
    """Verify that only citizens with a broadcast license (status) can post."""
    db_path = tmp_path / "social_test.db"
    broadcasts_dir = tmp_path / "broadcasts"
    pokedex = Pokedex(db_path=db_path)
    broadcaster = SocialBroadcaster(broadcasts_dir=str(broadcasts_dir))
    
    # 1. New agent (discovered, NOT citizen)
    pokedex.discover("Stranger")
    jiva = derive_jiva("Stranger")
    identity = generate_identity(jiva)
    
    # Attempt post should fail with PermissionError
    with pytest.raises(PermissionError, match="BROADCAST_LICENSE missing"):
        broadcaster.post(identity, pokedex, "I am a stranger!")

def test_social_citizen_post(tmp_path):
    """Verify that a registered citizen can post."""
    db_path = tmp_path / "social_test.db"
    broadcasts_dir = tmp_path / "broadcasts"
    pokedex = Pokedex(db_path=db_path)
    broadcaster = SocialBroadcaster(broadcasts_dir=str(broadcasts_dir))
    
    pokedex.register("CitizenX")
    jiva = derive_jiva("CitizenX")
    identity = generate_identity(jiva)
    
    # Should work
    assert broadcaster.post(identity, pokedex, "Hello Citizens!") is True
    
    # Check the file creation
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = broadcasts_dir / f"{date_str}_sovereign_square.md"
    assert log_file.exists()
    assert "CitizenX" in log_file.read_text()
    assert "Hello Citizens!" in log_file.read_text()


def test_social_no_pokedex_bypass(tmp_path):
    """REGRESSION: Passing pokedex=None must raise, not silently bypass governance."""
    broadcasts_dir = tmp_path / "broadcasts"
    broadcaster = SocialBroadcaster(broadcasts_dir=str(broadcasts_dir))
    
    jiva = derive_jiva("Sneaky")
    identity = generate_identity(jiva)
    
    with pytest.raises(PermissionError, match="Pokedex is required"):
        broadcaster.post(identity, None, "I bypassed governance!")


def test_social_message_length_limit(tmp_path):
    """REGRESSION: Messages exceeding MAX_MESSAGE_LENGTH must be rejected."""
    db_path = tmp_path / "social_test.db"
    broadcasts_dir = tmp_path / "broadcasts"
    pokedex = Pokedex(db_path=db_path)
    broadcaster = SocialBroadcaster(broadcasts_dir=str(broadcasts_dir))
    
    pokedex.register("Verbose")
    jiva = derive_jiva("Verbose")
    identity = generate_identity(jiva)
    
    huge_message = "X" * (MAX_MESSAGE_LENGTH + 1)
    with pytest.raises(ValueError, match="char limit"):
        broadcaster.post(identity, pokedex, huge_message)
