


def test_identity_keys_are_unique_per_agent():
    """No two agents must share cryptographic identity.

    If this fails, agents can impersonate each other.
    Test: Generate 50 identities, verify all unique.
    """
    from city.identity import generate_identity
    from city.jiva import derive_jiva

    fingerprints = set()
    names = [f"UniqueAgent_{i}" for i in range(50)]

    for name in names:
        jiva = derive_jiva(name)
        identity = generate_identity(jiva)
        assert identity.fingerprint not in fingerprints, (
            f"CRITICAL: Identity collision! {name} shares fingerprint "
            f"with another agent. Impersonation possible."
        )
        fingerprints.add(identity.fingerprint)


def test_address_space_no_collisions():
    """No two different agents must share the same network address.

    Address collision = messages delivered to wrong agent.
    Test: 100 unique names, all unique addresses.
    """
    from city.addressing import CityAddressBook

    book = CityAddressBook()
    addresses = set()
    names = [f"AddressTest_{i}" for i in range(100)]

    for name in names:
        addr = book.resolve(name)
        assert addr not in addresses, (
            f"CRITICAL: Address collision! {name} got address {addr} "
            "which is already assigned. Messages will be misdelivered."
        )
        addresses.add(addr)