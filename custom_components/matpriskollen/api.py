"""Fetch pages from Matpriskollen.

Only public pages that robots.txt allows are read: the chain overview
(/mataffarer), the store lists per chain and town, and the store pages with
the week's offers. Search (/sok), /api and pages behind login are not used.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import aiohttp

from .const import BASE_URL, CHAIN_NAMES, DEFAULT_CHAINS, REQUEST_DELAY, USER_AGENT
from .parse import chain_links, city_slug, page_text, store_links

_LOGGER = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=30)


class MatpriskollenError(Exception):
    """A page could not be fetched."""


@dataclass
class StorePage:
    """A store page: its name and visible text."""

    name: str | None
    text: str


class MatpriskollenClient:
    """Small client for the public pages."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(self, path: str) -> str | None:
        """Page HTML, or None when the page does not exist."""
        url = f"{BASE_URL}{path}"
        try:
            async with self._session.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
            ) as resp:
                if resp.status == 404:
                    return None
                if resp.status != 200:
                    raise MatpriskollenError(f"{url} answered {resp.status}")
                return await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MatpriskollenError(f"{url}: {err}") from err

    async def async_chains(self) -> list[str]:
        """Chain slugs, e.g. ["ica", "coop", ...]."""
        try:
            html = await self._get("/mataffarer")
        except MatpriskollenError as err:
            _LOGGER.debug("Chain list not read, using defaults: %s", err)
            html = None
        chains = chain_links(html) if html else []
        return chains or list(DEFAULT_CHAINS)

    async def async_find_stores(self, cities: list[str]) -> dict[str, str]:
        """Store slug -> name for all chains in the given towns."""
        chains = await self.async_chains()
        found: dict[str, str] = {}
        for city in cities:
            town = city_slug(city)
            if not town:
                continue
            for chain in chains:
                await asyncio.sleep(REQUEST_DELAY)
                html = await self._get(f"/mataffarer/{chain}/{town}")
                if not html:
                    continue
                chain_name = CHAIN_NAMES.get(chain, chain.replace("-", " ").title())
                for slug, text in store_links(html).items():
                    if slug in found:
                        continue
                    name = text or slug
                    found[slug] = (
                        name
                        if name.lower().startswith(chain_name.lower())
                        else f"{chain_name} {name}"
                    )
        return found

    async def async_store_page(self, slug: str) -> StorePage:
        """Name and text of one store page."""
        html = await self._get(f"/butiker/{slug}")
        if html is None:
            raise MatpriskollenError(f"Store {slug} not found")
        name, text = page_text(html)
        return StorePage(name=name, text=text)
