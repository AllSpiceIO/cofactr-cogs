import os
import sys
from dataclasses import dataclass
from enum import Enum

import requests


class SearchStrategy(Enum):
    MPN_SKU_MFR = "mpn_sku_mfr"
    FUZZY = "fuzzy"

    def to_query_value(self) -> str:
        # Cofactr's default search strategy is designed for search results.
        if self == SearchStrategy.FUZZY:
            return "default"
        return self.value

    def query_needs_manufacturer(self) -> bool:
        return self == SearchStrategy.MPN_SKU_MFR


@dataclass
class PartPrices:
    cofactr_id: str
    prices: dict[int, float]


def fetch_price_for_part(
    part_number: str, manufacturer: str, search_strategy: SearchStrategy
) -> PartPrices | None:
    """
    Get the price of a component per n units.

    The return value of this function is a mapping of number of units to the
    price in dollars per unit if you purchase that many units. For example::

        {
            1: 0.5,
            10: 0.45,
            500: 0.4,
            100: 0.35,
        }

    In this case, the price per unit is 0.5, the price per unit if you buy 10
    or more is 0.45, the price per unit if you buy 50 or more is 0.4, and so on.
    Your breakpoints can be any positive integer.

    The implementation of this function depends on the API you are using to get
    pricing data. This is an example implementation that uses the cofactr API,
    and will not work unless you have a cofactr API key. You will need to
    replace this function with your own implementation if you use some other
    API, such as Octopart or TrustedParts. You have access to the `requests`
    python library to perform HTTP requests.

    :param part_number: A part number by which to search for the component.
    :returns: A mapping of price breakpoints to the price at that breakpoint.
    """

    if part_number.startswith("NOTAPART"):
        return None

    api_key = os.environ.get("COFACTR_API_KEY")
    client_id = os.environ.get("COFACTR_CLIENT_ID")
    if api_key is None or client_id is None:
        raise ValueError(
            "Please set the COFACTR_API_KEY and COFACTR_CLIENT_ID environment variables"
        )

    query = part_number
    if search_strategy.query_needs_manufacturer() and manufacturer:
        query += f" {manufacturer}"

    search_response = requests.get(
        "https://graph.cofactr.com/products/",
        headers={
            "X-API-KEY": api_key,
            "X-CLIENT-ID": client_id,
        },
        params={
            "q": query,
            "search_strategy": search_strategy.to_query_value(),
            "schema": "product-offers-v0",
            "external": "true",
            "limit": "1",
        },
    )

    if search_response.status_code != 200:
        print(
            f"Warning: Received status code {search_response.status_code} for {part_number} {manufacturer}",
            file=sys.stderr,
        )
        return None

    search_results = search_response.json()
    try:
        reference_prices = search_results.get("data", [])[0].get("reference_prices")
    except IndexError:
        print(
            f"Warning: No results found for {part_number} {manufacturer}",
            file=sys.stderr,
        )
        return None

    prices = {int(price["quantity"]): float(price["price"]) for price in reference_prices}

    return PartPrices(
        cofactr_id=search_results["data"][0]["id"],
        prices=prices,
    )
