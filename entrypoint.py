#! /usr/bin/env python3

# Compute the Cost of Goods Sold for a BOM.
#
# This script doesn't depend on py-allspice, but it requires a BOM CSV file to
# run. You can use https://github.com/AllSpiceIO/generate-bom to generate a BOM
# CSV.

from argparse import ArgumentParser
from contextlib import ExitStack
import csv
from dataclasses import dataclass
import os
import sys

import requests


@dataclass
class PartPrices:
    cofactr_id: str
    prices: dict[int, float]


def fetch_price_for_part(
    part_number: str, manufacturer: str, search_strategy: str
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
    if query_needs_manufacturer(search_strategy) and manufacturer:
        query += f" {manufacturer}"

    search_response = requests.get(
        "https://graph.cofactr.com/products/",
        headers={
            "X-API-KEY": api_key,
            "X-CLIENT-ID": client_id,
        },
        params={
            "q": query,
            "search_strategy": search_strategy,
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


def query_needs_manufacturer(search_strategy: str) -> bool:
    return search_strategy != "mpn_exact"


def main() -> None:
    parser = ArgumentParser()

    parser.add_argument(
        "bom_file",
        help="The path to the BOM file.",
    )
    parser.add_argument(
        "--quantities",
        help=(
            "A comma-separated list of quantities of PCBs to compute the COGS "
            + "for. Defaults to '%(default)s'."
        ),
        default="1,10,100,1000",
    )
    parser.add_argument(
        "--bom-part-number-column",
        help="The name of the part number column in the BOM file. Defaults to '%(default)s'.",
        default="Part Number",
    )
    parser.add_argument(
        "--bom-manufacturer-column",
        help="The name of the manufacturer column in the BOM file.  Defaults to '%(default)s'.  If "
        + "you use a search strategy that uses manufacturer, you must provide this.",
        default="",
    )
    parser.add_argument(
        "--bom-quantity-column",
        help="The name of the quantity column in the BOM file. Defaults to '%(default)s'.",
        default="Quantity",
    )
    parser.add_argument(
        "--search-strategy",
        help="The Cofactr search strategy. Can be: mpn_sku_mfr or fuzzy (uses mpn). "
        + "Defaults to '%(default)s'.  The API also supports mpn_exact and mpn_exact_mfr, "
        + "but they are not recommended.",
        default="mpn_sku_mfr",
    )
    parser.add_argument(
        "--output-file",
        help="The path to the output file. Defaults to stdout, i.e. printing to the console.",
    )
    parser.add_argument(
        "--log-level",
        help="The log level to use.  Defaults to '%(default)s'.",
        default="info",
    )

    args = parser.parse_args()

    quantities = [int(quantity) for quantity in args.quantities.split(",")]

    part_number_column = args.bom_part_number_column
    manufacturer_column = args.bom_manufacturer_column
    quantity_column = args.bom_quantity_column
    search_strategy = args.search_strategy
    if search_strategy == "fuzzy":
        # Cofactr's default search strategy is designed for search results.
        search_strategy = "default"

    with open(args.bom_file, "r") as bom_file:
        bom_csv = csv.DictReader(bom_file)

        parts = [
            part for part in bom_csv if part[part_number_column] and part[part_number_column] != ""
        ]

    print(f"Computing COGS for {len(parts)} parts", file=sys.stderr)
    print(f"Fetching prices for {len(parts)} parts", file=sys.stderr)

    prices_for_parts = {}

    use_mfr = bool(manufacturer_column)
    if not use_mfr and query_needs_manufacturer(search_strategy):
        raise ValueError(
            "Search strategy requires manufacturer, but no BOM manufacturer column was provided.  Please set bom_manufacturer_column."
        )

    if args.log_level.lower() == "debug":
        print(f"Using part number column: {part_number_column!r}", file=sys.stderr)
        print(f"Using manufacturer column: {manufacturer_column!r}", file=sys.stderr)
        print(f"Using use_mfr: {use_mfr!r}", file=sys.stderr)
        print(f"Using quantity column: {quantity_column!r}", file=sys.stderr)
        print(f"Using search strategy: {search_strategy!r}", file=sys.stderr)

    for part in parts:
        part_number = part[part_number_column]
        manufacturer = part[manufacturer_column] if use_mfr else ""
        part_prices = fetch_price_for_part(part_number, manufacturer, search_strategy)
        if part_prices is not None and len(part_prices.prices) > 0:
            prices_for_parts[(part_number, manufacturer)] = part_prices

    print(f"Found prices for {len(prices_for_parts)} parts", file=sys.stderr)

    if len(prices_for_parts) == 0:
        print("No prices found for any parts", file=sys.stderr)
        sys.exit(1)

    headers = [
        "Part Number",
        "Manufacturer",
        "Cofactr ID",
        "Quantity",
    ]

    for quantity in quantities:
        headers.append(f"Per Unit at {quantity}")
        headers.append(f"Total at {quantity}")

    rows = []
    totals: dict[int, float] = {quantity: 0 for quantity in quantities}

    for part in parts:
        part_number = part[part_number_column]
        manufacturer = part[manufacturer_column] if use_mfr else ""
        part_quantity = int(part[quantity_column])

        part_prices = prices_for_parts.get((part_number, manufacturer))
        cofactr_id = part_prices.cofactr_id if part_prices else None

        current_row = [part_number, manufacturer, cofactr_id, part_quantity]

        for quantity in quantities:
            breakpoints = price_breakpoints(part_prices, quantity)
            if part_prices and breakpoints:
                largest_breakpoint_less_than_qty = max(breakpoints)
                price_at_breakpoint = part_prices.prices[largest_breakpoint_less_than_qty]
                current_row.append(price_at_breakpoint)
                total_for_part_at_quantity = price_at_breakpoint * part_quantity
                current_row.append(total_for_part_at_quantity)
                totals[quantity] += total_for_part_at_quantity
            else:
                current_row.append(None)
                current_row.append(None)

        rows.append(current_row)

    with ExitStack() as stack:
        if args.output_file:
            file = stack.enter_context(open(args.output_file, "w"))
            writer = csv.writer(file)
        else:
            writer = csv.writer(sys.stdout)

        writer.writerow(headers)
        writer.writerows(rows)

        totals_row = ["Totals", None, None, None]
        for quantity in quantities:
            totals_row.append(None)
            totals_row.append(str(totals[quantity]))

        writer.writerow(totals_row)

    print("Computed COGS", file=sys.stderr)


def price_breakpoints(part_prices: PartPrices | None, quantity: int) -> list[int] | None:
    if part_prices is None:
        return None
    breakpoints = [breakpoint for breakpoint in part_prices.prices.keys() if breakpoint <= quantity]
    return breakpoints if len(breakpoints) > 0 else None


if __name__ == "__main__":
    main()
