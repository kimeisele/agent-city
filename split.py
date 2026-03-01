import sys, os

content = open("tests/test_hardening.py").read()
blocks = content.split("\n# ═══════════════════════════════════════════════════════════════════════\n")

header = blocks[0]

categories = {
    "1. LEDGER INTEGRITY": "test_ledger_integrity.py",
    "2. ECONOMY EXPLOITS": "test_economy_exploits.py",
    "3. GOVERNANCE ATTACKS": "test_governance_attacks.py",
    "4. FEDERATION POISONING": "test_federation_poisoning.py",
    "5. STATE CORRUPTION": "test_state_corruption.py",
    "6. MURALI CYCLE INVARIANTS": "test_murali_invariants.py",
    "7. CROSS-LAYER INVARIANTS": "test_cross_layer.py"
}

os.makedirs("tests/hardening", exist_ok=True)

# Find the point to split the header (after imports)
header_split_idx = header.find("import pytest\n")
if header_split_idx != -1:
    header_base = header[:header_split_idx + len("import pytest\n")]
else:
    header_base = header

for block in blocks[1:]:
    lines = block.split("\n")
    title = lines[0].strip("# ")
    
    for prefix, filename in categories.items():
        if title.startswith(prefix):
            # Create the file content: imports + block header + block code
            file_content = header_base + "\n\n# ═══════════════════════════════════════════════════════════════════════\n" + block
            
            with open(f"tests/hardening/{filename}", "w") as f:
                f.write(file_content)
            print(f"Created {filename}")
            break
