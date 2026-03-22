from pathlib import Path
import re

path = Path("/Users/ss/projects/agent-city/city/pokedex.py")
text = path.read_text()

helpers = '''class Pokedex:
    """The living agent registry of Agent City.

    SQLite-backed. Every mutation creates an immutable event.
    Economy via CivicBank (steward-protocol). No copies.
    """

    def _reverse_bank_transfer(
        self,
        sender: str,
        recipient: str,
        amount: int,
        reason: str,
        category: str,
    ) -> bool:
        if amount <= 0:
            return True
        try:
            self._bank.transfer(sender, recipient, amount, reason, category)
            return True
        except Exception as exc:
            logger.critical(
                "SETTLEMENT: compensation failed %s -> %s amount=%d reason=%s error=%s",
                sender,
                recipient,
                amount,
                reason,
                exc,
            )
            return False

    def _safe_sqlite_commit(self, *, context: str) -> None:
        try:
            self._conn.commit()
        except Exception:
            logger.exception("SETTLEMENT: sqlite commit failed during %s", context)
            raise

    def _maybe_revive_after_prana_credit(self, name: str, previous_status: str, reason: str) -> None:
        if previous_status != "frozen":
            return

        cur = self._conn.cursor()
        cur.execute("SELECT prana FROM agents WHERE name = ?", (name,))
        row = cur.fetchone()
        if row is None:
            return

        from city.seed_constants import HIBERNATION_THRESHOLD

        if row["prana"] > HIBERNATION_THRESHOLD:
            self.revive(
                name,
                prana_dose=0,
                sponsor="system",
                reason=reason,
                membrane=self._internal_root_membrane(source_class="economy"),
            )

    def __init__(
'''
text, count = re.subn(
    r'class Pokedex:\n    """The living agent registry of Agent City\.\n\n    SQLite-backed\. Every mutation creates an immutable event\.\n    Economy via CivicBank \(steward-protocol\)\. No copies\.\n    """\n\n    def __init__\(\n',
    helpers,
    text,
    count=1,
)
if count != 1:
    raise SystemExit("failed to insert helpers")

new_bounty = '''    def fill_bounty_order(self, order_id: int, claimer: str, heartbeat: int) -> dict | None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM marketplace_orders WHERE id = ? AND status = 'open' AND asset_type = 'bounty'",
                (order_id,),
            )
            order = cur.fetchone()
            if not order:
                return None

            claimer_row = self._require(claimer)
            price = int(order["price"] or 0)
            if price <= 0:
                return None

            seller = order["seller"]
            now = datetime.now(timezone.utc).isoformat()
            tx_id: str | None = None
            try:
                tx_id = self._bank.transfer(
                    SYSTEM_TREASURY, claimer, price, f"bounty_order_{order_id}", "bounty"
                )
                cur.execute(
                    """UPDATE marketplace_orders
                       SET status = 'filled', buyer = ?, filled_at = ?
                       WHERE id = ?""",
                    (claimer, now, order_id),
                )
                cur.execute(
                    "UPDATE agents SET prana = prana + ? WHERE name = ?",
                    (price, claimer),
                )

                cur.execute(
                    "UPDATE marketplace_orders SET tx_id = ? WHERE id = ?",
                    (tx_id, order_id),
                )
                self._record_event(
                    claimer,
                    "bounty_claim",
                    claimer_row["status"],
                    claimer_row["status"],
                    json.dumps({
                        "order_id": order_id,
                        "asset_id": order["asset_id"],
                        "amount": price,
                        "heartbeat": heartbeat,
                        "seller": seller,
                    }),
                )
                self._safe_sqlite_commit(context=f"bounty_order:{order_id}")
            except Exception:
                self._conn.rollback()
                if tx_id is not None:
                    self._reverse_bank_transfer(
                        claimer,
                        SYSTEM_TREASURY,
                        price,
                        f"bounty_order_reversal_{order_id}",
                        "settlement_reversal",
                    )
                return None

            if self._prana_engine is not None and self._prana_engine.has(claimer):
                self._prana_engine.credit(claimer, price)

            self._maybe_revive_after_prana_credit(
                claimer,
                str(claimer_row["status"]),
                f"revive:bounty_claim:{order['asset_id']}",
            )

        logger.info(
            "MARKETPLACE: Bounty #%d — %s claimed %s for %d prana",
            order_id,
            claimer,
            order["asset_id"],
            price,
        )
        return {
            "order_id": order_id,
            "seller": seller,
            "buyer": claimer,
            "asset_type": order["asset_type"],
            "asset_id": order["asset_id"],
            "quantity": order["quantity"],
            "price": price,
            "commission": 0,
            "seller_receives": 0,
            "tx_id": tx_id,
        }
'''
text, count = re.subn(
    r'    def fill_bounty_order\(self, order_id: int, claimer: str, heartbeat: int\) -> dict \| None:\n.*?\n    def fill_order\(\n',
    new_bounty + '\n    def fill_order(\n',
    text,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit("failed to replace fill_bounty_order")

new_trade = '''    def fill_order(
        self,
        order_id: int,
        buyer: str,
        heartbeat: int,
        commission_pct: int | None = None,
    ) -> dict | None:
        """Execute a trade: buyer pays prana, receives asset.

        Returns trade receipt dict or None on failure.
        Commission goes to seller's zone treasury.
        If commission_pct is provided, uses that instead of the default constant.

        Transaction safety: SQLite staged first, bank transfer attempted,
        SQLite committed only if bank succeeds. Rollback on bank failure.
        """
        from city.seed_constants import TRADE_COMMISSION_PERCENT

        with self._lock:
            cur = self._conn.cursor()

            # 1. VALIDATE (read-only)
            cur.execute(
                "SELECT * FROM marketplace_orders WHERE id = ? AND status = 'open'",
                (order_id,),
            )
            order = cur.fetchone()
            if not order:
                return None

            seller = order["seller"]
            price = order["price"]

            if buyer == seller:
                return None

            # Check buyer has enough prana
            buyer_balance = self._bank.get_balance(buyer)
            if buyer_balance < price:
                return None

            # Calculate commission (council override or default constant)
            effective_rate = (
                commission_pct if commission_pct is not None else TRADE_COMMISSION_PERCENT
            )
            commission = (price * effective_rate) // 100
            seller_receives = price - commission

            # Zone treasury for commission (fallback to ZONE_DISCOVERY)
            seller_data = self.get(seller)
            zone = (seller_data or {}).get("zone", "discovery")
            zone_account = ZONE_TREASURIES.get(zone, "ZONE_DISCOVERY")

            now = datetime.now(timezone.utc).isoformat()
            tx_id: str | None = None
            commission_tx_done = False

            # 2. SQLITE STAGE (not yet committed) — inline grant, not via grant_asset()
            cur.execute(
                """UPDATE marketplace_orders
                   SET status = 'filled', buyer = ?, filled_at = ?
                   WHERE id = ?""",
                (buyer, now, order_id),
            )

            # Grant asset to buyer (inline SQL to avoid grant_asset's internal commit)
            cur.execute(
                """SELECT id, quantity FROM agent_inventory
                   WHERE agent_name = ? AND asset_type = ? AND asset_id = ?
                     AND (expires_at IS NULL OR expires_at > ?)
                     AND quantity > 0
                   LIMIT 1""",
                (buyer, order["asset_type"], order["asset_id"], now),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    "UPDATE agent_inventory SET quantity = ? WHERE id = ?",
                    (existing["quantity"] + order["quantity"], existing["id"]),
                )
            else:
                cur.execute(
                    """INSERT INTO agent_inventory
                       (agent_name, asset_type, asset_id, quantity, source, acquired_at)
                       VALUES (?, ?, ?, ?, 'trade', ?)""",
                    (buyer, order["asset_type"], order["asset_id"], order["quantity"], now),
                )

            # 3. BANK TRANSFER (separate DB) — if this fails, rollback SQLite
            try:
                tx_id = self._bank.transfer(
                    buyer, seller, seller_receives, f"trade_order_{order_id}", "trade"
                )
                if commission > 0:
                    self._bank.transfer(
                        buyer, zone_account, commission, f"trade_commission_{order_id}", "tax"
                    )
                    commission_tx_done = True

                # 4. COMMIT SQLITE (only if bank succeeded)
                cur.execute(
                    "UPDATE marketplace_orders SET tx_id = ? WHERE id = ?",
                    (tx_id, order_id),
                )
                self._safe_sqlite_commit(context=f"trade_order:{order_id}")
            except Exception:
                self._conn.rollback()
                if commission > 0 and commission_tx_done:
                    self._reverse_bank_transfer(
                        zone_account,
                        buyer,
                        commission,
                        f"trade_commission_reversal_{order_id}",
                        "settlement_reversal",
                    )
                if tx_id is not None:
                    self._reverse_bank_transfer(
                        seller,
                        buyer,
                        seller_receives,
                        f"trade_order_reversal_{order_id}",
                        "settlement_reversal",
                    )
                return None

        logger.info(
            "MARKETPLACE: Trade #%d — %s bought %s:%s from %s for %d prana (commission %d)",
            order_id,
            buyer,
            order["asset_type"],
            order["asset_id"],
            seller,
            price,
            commission,
        )
        return {
            "order_id": order_id,
            "seller": seller,
            "buyer": buyer,
            "asset_type": order["asset_type"],
            "asset_id": order["asset_id"],
            "quantity": order["quantity"],
            "price": price,
            "commission": commission,
            "seller_receives": seller_receives,
            "tx_id": tx_id,
        }
'''
text, count = re.subn(
    r'    def fill_order\(\n.*?\n    def cancel_order\(',
    new_trade + '\n    def cancel_order(',
    text,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit("failed to replace fill_order")

path.write_text(text)
print("restored pokedex settlement hardening")
