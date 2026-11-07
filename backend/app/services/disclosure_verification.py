from decimal import ROUND_CEILING, Decimal
from statistics import median

from pydantic import ValidationError

from app.services.commitments import canonical_manifest_json, verify_pool_commitment
from app.services.disclosures import DisclosurePackage, canonical_disclosure_json
from app.services.drand import QUICKNET_CHAIN_HASH, verify_quicknet_beacon
from app.services.selection import select_gift

TARGET_RTP = Decimal("0.90")
EXPECTED_ALGORITHMS = {
    "pool_commitment": "gift-pool-v1-sha256",
    "selection": "gift-draw-v1-sha256-rejection-v1",
    "beacon": "drand-quicknet-bls-unchained-g1-rfc9380",
    "canonical_json": "utf8-sorted-keys-compact",
}


class DisclosureVerificationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DisclosureVerificationError(message)


def _stored(value: Decimal, decimal_places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-decimal_places))


def _verify_pool_economics(package: DisclosurePackage) -> None:
    for pool in package.pool_versions:
        gifts = pool.manifest.gifts
        count = Decimal(len(gifts))
        expected_value = sum((gift.player_sale_estimate for gift in gifts), Decimal(0)) / count
        exact_price = expected_value / TARGET_RTP
        price = int(exact_price.to_integral_value(rounding=ROUND_CEILING))
        mean_replacement = sum((gift.replacement_cost for gift in gifts), Decimal(0)) / count
        sale_estimates = [Decimal(gift.player_sale_estimate) for gift in gifts]
        distribution = {
            "minimum": str(min(sale_estimates)),
            "median": str(median(sale_estimates)),
            "maximum": str(max(sale_estimates)),
            "below_ticket_count": sum(value < price for value in sale_estimates),
            "at_or_above_ticket_count": sum(value >= price for value in sale_estimates),
        }
        _require(pool.price == price, f"Pool version {pool.version} has an invalid price")
        _require(
            pool.expected_value == _stored(expected_value, 8),
            f"Pool version {pool.version} has invalid expected value",
        )
        _require(
            pool.actual_rtp == _stored(expected_value / Decimal(price), 8),
            f"Pool version {pool.version} has invalid RTP",
        )
        _require(
            pool.operator_margin == _stored(Decimal(price) - mean_replacement, 8),
            f"Pool version {pool.version} has invalid operator margin",
        )
        _require(
            pool.value_distribution == distribution,
            f"Pool version {pool.version} has an invalid value distribution",
        )


def _verify_pool_history(package: DisclosurePackage) -> None:
    pools = package.pool_versions
    _require(bool(pools), "Round has no committed pool")
    _require(
        [pool.version for pool in pools] == list(range(1, len(pools) + 1)),
        "Pool versions are missing, duplicated, or out of order",
    )
    _require(len({pool.id for pool in pools}) == len(pools), "Duplicate pool version ID")
    completed_by_pool = {
        bet.pool_version_id: bet for bet in package.bets if bet.state == "COMPLETED"
    }
    _require(
        len(completed_by_pool) == sum(bet.state == "COMPLETED" for bet in package.bets),
        "A pool version has duplicate completed attempts",
    )
    for index, pool in enumerate(pools):
        manifest_json = canonical_manifest_json(pool.manifest)
        _require(
            verify_pool_commitment(package.round.id, pool.version, manifest_json, pool.commitment),
            f"Pool version {pool.version} commitment does not match its manifest",
        )
        _require(
            [gift.id for gift in pool.manifest.gifts]
            == sorted(gift.id for gift in pool.manifest.gifts),
            f"Pool version {pool.version} is not ordered by gift ID",
        )
        _require(
            pool.remaining_count == len(pool.manifest.gifts),
            f"Pool version {pool.version} has an invalid remaining count",
        )
        if index == 0:
            continue
        previous_ids = {gift.id for gift in pools[index - 1].manifest.gifts}
        current_ids = {gift.id for gift in pool.manifest.gifts}
        _require(
            current_ids <= previous_ids,
            f"Pool version {pool.version} reintroduces or adds a gift",
        )
        removed_ids = previous_ids - current_ids
        _require(len(removed_ids) <= 1, f"Pool version {pool.version} removes multiple gifts")
        if removed_ids:
            bet = completed_by_pool.get(pools[index - 1].id)
            _require(
                bet is not None and bet.selected_gift_id in removed_ids,
                f"Pool version {pool.version} has an unexplained gift removal",
            )


def _verify_gifts(package: DisclosurePackage) -> None:
    _require(bool(package.gifts), "Round has no gift inventory")
    gift_ids = {gift.id for gift in package.gifts}
    _require(len(gift_ids) == len(package.gifts), "Duplicate disclosed gift ID")
    initial = package.pool_versions[0].manifest.gifts
    initial_by_id = {gift.id: gift for gift in initial}
    _require(gift_ids == set(initial_by_id), "Final gifts differ from the original pool")
    for gift in package.gifts:
        original = initial_by_id[gift.id]
        _require(
            (
                gift.model,
                gift.backdrop,
                gift.symbol,
                gift.rarity,
                gift.number,
            )
            == (
                original.model,
                original.backdrop,
                original.symbol,
                original.rarity,
                original.number,
            ),
            f"Gift {gift.id} attributes changed after commitment",
        )
    _require(
        len({gift.number for gift in package.gifts}) == len(package.gifts),
        "Duplicate gift number in round",
    )


def _verify_bet(package: DisclosurePackage, bet_index: int) -> None:
    bet = package.bets[bet_index]
    pools = {pool.id: pool for pool in package.pool_versions}
    pool = pools.get(bet.pool_version_id)
    _require(pool is not None, f"Bet {bet.id} references an unknown pool")
    assert pool is not None
    _require(
        bet.pool_version_hash == pool.commitment
        and bet.price == pool.price
        and bet.remaining_count == pool.remaining_count,
        f"Bet {bet.id} binding differs from its pool version",
    )
    entries = bet.ledger_entries
    _require(
        len({entry.id for entry in entries}) == len(entries),
        f"Bet {bet.id} has duplicate ledger IDs",
    )
    debits = [entry for entry in entries if entry.kind == "DEBIT"]
    restorations = [entry for entry in entries if entry.kind == "RESTORATION"]
    _require(
        len(debits) == 1 and debits[0].amount == -bet.price,
        f"Bet {bet.id} does not have exactly one matching debit",
    )
    _require(
        all(entry.balance_after >= 0 for entry in entries),
        f"Bet {bet.id} has a negative ledger balance",
    )
    if bet.state == "CANCELLED":
        _require(
            bet.selected_gift_id is None
            and bet.beacon_proof is None
            and bet.cancellation_reason is not None
            and len(restorations) == 1
            and restorations[0].amount == bet.price
            and len(entries) == 2,
            f"Cancelled bet {bet.id} has an invalid outcome or restoration",
        )
        return

    _require(
        bet.selected_gift_id is not None
        and bet.beacon_proof is not None
        and bet.cancellation_reason is None
        and not restorations
        and len(entries) == 1,
        f"Completed bet {bet.id} has an invalid outcome or ledger",
    )
    proof = bet.beacon_proof
    assert proof is not None
    _require(
        proof.network == QUICKNET_CHAIN_HASH
        and proof.round == bet.future_beacon_round
        and proof.response
        == {
            "round": proof.round,
            "randomness": proof.randomness,
            "signature": proof.signature,
        },
        f"Bet {bet.id} has inconsistent beacon evidence",
    )
    _require(
        verify_quicknet_beacon(proof.round, proof.signature, proof.randomness),
        f"Bet {bet.id} has an invalid drand signature or randomness",
    )
    selection = select_gift(
        drand_randomness_hex=proof.randomness,
        bet_id=bet.id,
        pool_version_hash=bet.pool_version_hash,
        remaining_manifest=pool.manifest,
    )
    _require(
        selection.gift_id == bet.selected_gift_id,
        f"Bet {bet.id} outcome does not replay to the selected gift",
    )


def verify_disclosure(package: DisclosurePackage) -> None:
    """Independently verify one disclosed round without reading application storage."""
    _require(package.asset_mode == "simulated", "Disclosure is not for simulated assets")
    _require(package.algorithms == EXPECTED_ALGORITHMS, "Unknown disclosure algorithms")
    _verify_pool_history(package)
    _verify_pool_economics(package)
    _verify_gifts(package)
    _require(len({bet.id for bet in package.bets}) == len(package.bets), "Duplicate bet ID")
    _require(
        all(bet.resolved_at >= bet.created_at for bet in package.bets),
        "A bet resolves before its creation",
    )
    for index in range(len(package.bets)):
        _verify_bet(package, index)

    selected_ids = [bet.selected_gift_id for bet in package.bets if bet.selected_gift_id]
    _require(len(selected_ids) == len(set(selected_ids)), "A gift was awarded more than once")
    gifts = {gift.id: gift for gift in package.gifts}
    for bet in package.bets:
        if bet.state == "COMPLETED":
            assert bet.selected_gift_id is not None
            gift = gifts.get(bet.selected_gift_id)
            _require(gift is not None, f"Bet {bet.id} selected an undisclosed gift")
            assert gift is not None
            _require(
                gift.lifecycle == "AWARDED" and gift.owner_epoch == bet.user_epoch,
                f"Bet {bet.id} has inconsistent final gift ownership",
            )
    awarded_ids = set(selected_ids)
    for gift in package.gifts:
        if gift.id not in awarded_ids:
            _require(
                gift.lifecycle == "AVAILABLE" and gift.owner_epoch is None,
                f"Unawarded gift {gift.id} has an invalid final state",
            )
    if awarded_ids != set(gifts):
        _require(
            package.round.disclosed_at >= package.round.disclosure_deadline,
            "An unsold round was disclosed before its deadline",
        )
    snapshot_ids = {snapshot.id for snapshot in package.market_snapshots}
    _require(len(snapshot_ids) == len(package.market_snapshots), "Duplicate market snapshot ID")
    _require(
        all(pool.market_snapshot_id in snapshot_ids for pool in package.pool_versions),
        "A pool references an undisclosed valuation snapshot",
    )
    _require(
        all(
            snapshot.collection_id == package.round.collection_id
            for snapshot in package.market_snapshots
        ),
        "A valuation snapshot belongs to another collection",
    )


def verify_disclosure_json(package_json: str) -> DisclosurePackage:
    try:
        package = DisclosurePackage.model_validate_json(package_json)
    except (ValidationError, ValueError) as exc:
        raise DisclosureVerificationError(f"Invalid disclosure schema: {exc}") from exc
    _require(canonical_disclosure_json(package) == package_json, "Disclosure JSON is not canonical")
    verify_disclosure(package)
    return package
