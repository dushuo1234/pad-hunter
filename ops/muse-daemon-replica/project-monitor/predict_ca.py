#!/usr/bin/env python3
"""CREATE / CREATE2 next-address prediction for high-confidence watched wallets (P1 optional).

EVM only. Pure functions — no RPC required for the math; callers supply nonce / salt /
init_code_hash. Used to pre-register a predicted_ca on a find before the deploy confirms.
"""
from __future__ import annotations

from eth_hash.auto import keccak  # type: ignore
import rlp  # type: ignore


def _norm(addr: str) -> bytes:
    a = addr.lower().removeprefix("0x")
    if len(a) != 40:
        raise ValueError(f"bad address length: {addr}")
    return bytes.fromhex(a)


def predict_create(deployer: str, nonce: int) -> str:
    """EIP-161 CREATE address = keccak256(rlp([sender, nonce]))[12:]."""
    raw = rlp.encode([_norm(deployer), nonce])
    return "0x" + keccak(raw)[12:].hex()


def predict_create2(deployer: str, salt: bytes | str, init_code_hash: bytes | str) -> str:
    """CREATE2 address = keccak256(0xff ++ sender ++ salt ++ keccak(init_code))[12:]."""
    if isinstance(salt, str):
        salt = bytes.fromhex(salt.removeprefix("0x"))
    if isinstance(init_code_hash, str):
        init_code_hash = bytes.fromhex(init_code_hash.removeprefix("0x"))
    if len(salt) != 32 or len(init_code_hash) != 32:
        raise ValueError("salt and init_code_hash must be 32 bytes")
    return "0x" + keccak(b"\xff" + _norm(deployer) + salt + init_code_hash)[12:].hex()


def predict_next_nonces(deployer: str, start_nonce: int, count: int = 5) -> list[dict]:
    """Predict the next `count` CREATE addresses from start_nonce inclusive."""
    return [{"nonce": start_nonce + i, "predicted_ca": predict_create(deployer, start_nonce + i)}
            for i in range(max(0, count))]
