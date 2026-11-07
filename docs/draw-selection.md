# Deterministic gift selection

Algorithm ID: `gift-draw-v1`. This algorithm operates only on locally verified drand randomness and the remaining canonically ordered pool manifest.

For counter `c`, starting at zero:

```text
digest = SHA-256(
  "gift-draw-v1"
  || drand_randomness_bytes
  || bet_id_utf8
  || pool_version_hash_ascii
  || uint64_big_endian(c)
)
candidate = unsigned_big_endian_uint256(digest)
limit = floor(2^256 / N) * N
```

If `candidate >= limit`, increment `c` and try again. Otherwise select the gift at zero-based index `candidate % N`. `N` is the number of gifts in the remaining manifest, ordered by stable gift ID. Powers of two, including a two-gift pool, have no rejected candidates. No modulo-only shortcut or substitute RNG is permitted.

## Published audit vectors

Both vectors use counter 0 and require no rejected retry.

### Vector 1

- drand quicknet round: 1
- randomness: `1466a6cd24e327188770752f6134001c64d6efcc590ccc26b721611ad96f165a`
- bet ID: `bet-0001`
- pool commitment: `8222cad41ff6051f1fe6db6ce1f1974220607b7e57068796e4f7f8bacd27c430`
- remaining gift IDs: `gift-a`, `gift-b`
- candidate digest: `25679154e32fe69bdf6cfb5ec42541c3b710561a8251ecbfabb0e650b5a2dd46`
- selected index and gift: `0`, `gift-a`

### Vector 2

- drand quicknet round: 2
- randomness: `5782d6987841c654515a0e72b2d1ebb4e741234042c37cb19608ae50d93fb60c`
- bet ID: `bet-0003`
- pool commitment: `b45208f06f88c2e723aa6ebc07c611ee4a51442a762fc7384ff94c0afa5ed071`
- remaining gift IDs: `gift-a`, `gift-b`, `gift-c`
- candidate digest: `011a46d3e1002f972312658cb1751c86aaf4ebfc03451c117e3d8cb5a976530b`
- selected index and gift: `1`, `gift-b`

The complete attributes corresponding to these commitments and the expected traces are tested in `backend/tests/test_selection.py`.

```bash
cd backend
.venv/bin/python -m pytest tests/test_selection.py -q
```
