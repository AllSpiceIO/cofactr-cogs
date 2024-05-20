#! /usr/bin/env python3

# Compute the Cost of Goods Sold for a BOM.
#
# This script doesn't depend on py-allspice, but it requires a BOM CSV file to
# run. You can use https://github.com/AllSpiceIO/generate-bom to generate a BOM
# CSV.

from argparse import ArgumentParser
from contextlib import ExitStack
import csv
import os
import sys

import requests


def fetch_price_for_part(
    part_number: str, manufacturer: str, search_strategy: str
) -> dict[int, float]:
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
        return {}

    api_key = os.environ.get("COFACTR_API_KEY")
    client_id = os.environ.get("COFACTR_CLIENT_ID")
    if api_key is None or client_id is None:
        raise ValueError(
            "Please set the COFACTR_API_KEY and COFACTR_CLIENT_ID environment variables"
        )

    query = part_number
    if search_strategy != "mpn_exact" and manufacturer:
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
        return {}

    search_results = search_response.json()
    try:
        reference_prices = search_results.get("data", [])[0].get("reference_prices")
    except IndexError:
        print(
            f"Warning: No results found for {part_number} {manufacturer}",
            file=sys.stderr,
        )
        return {}

    prices = {int(price["quantity"]): float(price["price"]) for price in reference_prices}

    return prices


if __name__ == "__main__":
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
        help="The name of the manufacturer column in the BOM file. Defaults to '%(default)s'.",
        default="Manufacturer",
    )
    parser.add_argument(
        "--bom-quantity-column",
        help="The name of the quantity column in the BOM file. Defaults to '%(default)s'.",
        default="Quantity",
    )
    parser.add_argument(
        "--search-strategy",
        help="The Cofactr search strategy. Can be: default, mpn_sku_mfr, mpn_exact, mpn_exact_mfr. "
        + "Defaults to '%(default)s'.",
        default="mpn_sku_mfr",
    )
    parser.add_argument(
        "--output-file",
        help="The path to the output file. Defaults to stdout, i.e. printing to the console.",
    )

    args = parser.parse_args()

    quantities = [int(quantity) for quantity in args.quantities.split(",")]

    part_number_column = args.bom_part_number_column
    manufacturer_column = args.bom_manufacturer_column
    quantity_column = args.bom_quantity_column

    with open(args.bom_file, "r") as bom_file:
        bom_csv = csv.DictReader(bom_file)

        parts = [
            part for part in bom_csv if part[part_number_column] and part[part_number_column] != ""
        ]

    print(f"Computing COGS for {len(parts)} parts", file=sys.stderr)
    print(f"Fetching prices for {len(parts)} parts", file=sys.stderr)

    prices_for_parts = {}

    for part in parts:
        part_number = part[part_number_column]
        manufacturer = part[manufacturer_column]
        prices = fetch_price_for_part(part_number, manufacturer, args.search_strategy)
        if prices and len(prices) > 0:
            prices_for_parts[part_number] = prices

    print(f"Found prices for {len(prices_for_parts)} parts", file=sys.stderr)

    if len(prices_for_parts) == 0:
        print("No prices found for any parts", file=sys.stderr)
        sys.exit(1)

    headers = [
        "Part Number",
        "Manufacturer",
        "Quantity",
    ]

    for quantity in quantities:
        headers.append(f"Per Unit at {quantity}")
        headers.append(f"Total at {quantity}")

    rows = []
    totals: dict[int, float] = {quantity: 0 for quantity in quantities}

    for part in parts:
        part_number = part[part_number_column]
        manufacturer = part[manufacturer_column]
        part_quantity = int(part[quantity_column])

        current_row = [part_number, manufacturer, part_quantity]

        for quantity in quantities:
            try:
                prices = prices_for_parts[part_number]
                largest_breakpoint_less_than_qty = max(
                    [breakpoint for breakpoint in prices.keys() if breakpoint <= quantity]
                )
                price_at_breakpoint = prices[largest_breakpoint_less_than_qty]
                current_row.append(price_at_breakpoint)
                total_for_part_at_quantity = price_at_breakpoint * part_quantity
                current_row.append(total_for_part_at_quantity)
                totals[quantity] += total_for_part_at_quantity
            except (ValueError, KeyError):
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

        totals_row = ["Totals", None, None]
        for quantity in quantities:
            totals_row.append(None)
            totals_row.append(str(totals[quantity]))

        writer.writerow(totals_row)

    print("Computed COGS", file=sys.stderr)
