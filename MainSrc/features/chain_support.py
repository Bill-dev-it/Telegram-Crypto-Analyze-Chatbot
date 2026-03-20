"""
features/chain_support.py
─────────────────────────
Multi-chain detection and per-chain URL/config routing.

Supported chains:
  • Ethereum   (ETH)   — EVM, 0x prefix
  • BNB Chain  (BSC)   — EVM, 0x prefix
  • Arbitrum   (ARB)   — EVM, 0x prefix
  • Base       (BASE)  — EVM, 0x prefix
  • Polygon    (MATIC) — EVM, 0x prefix
  • Solana     (SOL)   — base58, 32-44 chars, no 0x

Detection strategy:
  1. Solana  → base58, length 32-44, no 0x
  2. EVM     → 0x + 40 hex chars
  3. EVM sub-chains are identified by user hint or GoPlus fallback
     (we query GoPlus on all EVM chains and use the first hit)
"""

import re
from dataclasses import dataclass


# ── Chain definitions ─────────────────────────────────────────────────

@dataclass
class ChainInfo:
    id:            str    # internal key
    name:          str    # display name
    emoji:         str
    goplus_id:     str    # GoPlus chain param
    dexscreener:   str    # DexScreener chain slug
    explorer_url:  str    # block explorer address URL (use {addr} placeholder)
    explorer_name: str


CHAINS: dict[str, ChainInfo] = {
    "eth": ChainInfo(
        id="eth", name="Ethereum", emoji="🔷",
        goplus_id="1",
        dexscreener="ethereum",
        explorer_url="https://etherscan.io/address/{addr}",
        explorer_name="Etherscan",
    ),
    "bsc": ChainInfo(
        id="bsc", name="BNB Chain", emoji="🟡",
        goplus_id="56",
        dexscreener="bsc",
        explorer_url="https://bscscan.com/address/{addr}",
        explorer_name="BscScan",
    ),
    "arbitrum": ChainInfo(
        id="arbitrum", name="Arbitrum", emoji="🔵",
        goplus_id="42161",
        dexscreener="arbitrum",
        explorer_url="https://arbiscan.io/address/{addr}",
        explorer_name="Arbiscan",
    ),
    "base": ChainInfo(
        id="base", name="Base", emoji="🟦",
        goplus_id="8453",
        dexscreener="base",
        explorer_url="https://basescan.org/address/{addr}",
        explorer_name="Basescan",
    ),
    "polygon": ChainInfo(
        id="polygon", name="Polygon", emoji="🟣",
        goplus_id="137",
        dexscreener="polygon",
        explorer_url="https://polygonscan.com/address/{addr}",
        explorer_name="Polygonscan",
    ),
    "solana": ChainInfo(
        id="solana", name="Solana", emoji="🟢",
        goplus_id="solana",
        dexscreener="solana",
        explorer_url="https://solscan.io/token/{addr}",
        explorer_name="Solscan",
    ),
}

# EVM chains to probe in order when chain is unknown
EVM_PROBE_ORDER = ["eth", "bsc", "arbitrum", "base", "polygon"]


# ── Address format detection ──────────────────────────────────────────

_EVM_RE     = re.compile(r"^0x[a-fA-F0-9]{40}$")
_SOLANA_RE  = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")   # base58


def detect_address_type(addr: str) -> str:
    """
    Returns 'evm', 'solana', or 'unknown'.
    Does NOT identify which EVM chain — use detect_chain() for that.
    """
    addr = addr.strip()
    if _EVM_RE.match(addr):
        return "evm"
    if _SOLANA_RE.match(addr):
        return "solana"
    return "unknown"


def is_valid_address(addr: str) -> bool:
    return detect_address_type(addr) in ("evm", "solana")


async def detect_chain(addr: str, goplus_fetcher) -> ChainInfo:
    """
    For EVM addresses: probe GoPlus on each chain until we get a hit.
    For Solana addresses: return Solana immediately.
    Falls back to Ethereum if nothing matches.

    goplus_fetcher: your existing check_goplus_token_security function
                    — we call it with (addr, chain_id) pairs
    """
    addr_type = detect_address_type(addr)

    if addr_type == "solana":
        return CHAINS["solana"]

    if addr_type == "evm":
        import asyncio
        loop = asyncio.get_running_loop()

        for chain_key in EVM_PROBE_ORDER:
            chain = CHAINS[chain_key]
            try:
                # Try calling with chain_id if your goplus_fetcher supports it
                # If it only takes addr, we fall through to eth default
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, _goplus_with_chain, goplus_fetcher, addr, chain.goplus_id
                    ),
                    timeout=6.0
                )
                if result and isinstance(result, dict) and len(result) > 0:
                    # Got a real response → this is the chain
                    return chain
            except Exception:
                continue

        # Default fallback
        return CHAINS["eth"]

    return CHAINS["eth"]


def _goplus_with_chain(fetcher, addr: str, chain_id: str):
    """
    Tries to call fetcher with chain_id param.
    Falls back to just addr if the function signature doesn't support chain_id.
    """
    try:
        import inspect
        sig = inspect.signature(fetcher)
        params = list(sig.parameters.keys())
        if len(params) >= 2:
            return fetcher(addr, chain_id)
        else:
            return fetcher(addr)
    except Exception:
        return None


# ── Per-chain URL builders ────────────────────────────────────────────

def explorer_url(chain: ChainInfo, addr: str) -> str:
    return chain.explorer_url.format(addr=addr)


def dexscreener_url(chain: ChainInfo, addr: str) -> str:
    clean = addr.lower().replace("0x", "") if addr.startswith("0x") else addr
    return f"https://dexscreener.com/{chain.dexscreener}/{clean}"


def goplus_url(chain: ChainInfo, addr: str) -> str:
    return f"https://gopluslabs.io/token-security/{chain.goplus_id}/{addr}"


# ── Inline keyboard builder (chain-aware) ────────────────────────────

def build_chain_scan_buttons(addr: str, chain: ChainInfo):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"🌐 DexScreener",
                url=dexscreener_url(chain, addr)
            ),
            InlineKeyboardButton(
                f"{chain.emoji} {chain.explorer_name}",
                url=explorer_url(chain, addr)
            ),
        ],
        [
            InlineKeyboardButton(
                "🛡️ GoPlus",
                url=goplus_url(chain, addr)
            ),
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data=f"scan_refresh|{addr}|{chain.id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "📋 Full Report",
                callback_data=f"full_report|{addr}|{chain.id}"
            ),
            InlineKeyboardButton("← Menu", callback_data="main_menu"),
        ],
    ])


def build_chain_report_buttons(addr: str, chain: ChainInfo):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌐 DexScreener", url=dexscreener_url(chain, addr)),
            InlineKeyboardButton(
                f"{chain.emoji} {chain.explorer_name}",
                url=explorer_url(chain, addr)
            ),
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_report|{addr}|{chain.id}"),
            InlineKeyboardButton("← Menu",     callback_data="main_menu"),
        ],
    ])