# Compute the Cost of Goods Sold for a BOM.
#
# This script doesn't depend on py-allspice, but it requires a BOM CSV file to
# run. You can use https://github.com/AllSpiceIO/generate-bom to generate a BOM
# CSV.
import csv
import sys
from argparse import ArgumentParser
from contextlib import ExitStack

from cofactr_cogs.api import PartPrices, SearchStrategy, fetch_price_for_part


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
        help="The name of the part number column in the BOM file.  You must provide this.",
        default="",
    )
    parser.add_argument(
        "--bom-manufacturer-column",
        help="The name of the manufacturer column in the BOM file.  Defaults to '%(default)s'.  If "
        + "you use a search strategy that uses manufacturer, you must provide this.",
        default="",
    )
    parser.add_argument(
        "--bom-quantity-column",
        help="The name of the quantity column in the BOM file.  You must provide this.",
        default="",
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
    if not part_number_column:
        raise ValueError(
            "BOM part number column needs to be specified.  Please set bom_part_number_column."
        )

    manufacturer_column = args.bom_manufacturer_column
    quantity_column = args.bom_quantity_column
    if not quantity_column:
        raise ValueError(
            "BOM quantity column needs to be specified.  Please set bom_quantity_column."
        )

    search_strategy = SearchStrategy(args.search_strategy)

    with open(args.bom_file, "r") as bom_file:
        bom_csv = csv.DictReader(bom_file)

        parts = [
            part for part in bom_csv if part[part_number_column] and part[part_number_column] != ""
        ]

    print(f"Computing COGS for {len(parts)} parts", file=sys.stderr)
    print(f"Fetching prices for {len(parts)} parts", file=sys.stderr)

    prices_for_parts = {}

    use_mfr = bool(manufacturer_column)
    if not use_mfr and search_strategy.query_needs_manufacturer():
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

    # The number of columns that the output should have.
    expected_columns = (4 if use_mfr else 3) + 2 * len(quantities)

    headers = ["Part Number"]
    if use_mfr:
        headers.append("Manufacturer")
    headers.append("Cofactr ID")
    headers.append("Quantity")

    for quantity in quantities:
        headers.append(f"Per Unit at {quantity}")
        headers.append(f"Total at {quantity}")

    assert len(headers) == expected_columns

    rows = []
    totals: dict[int, float] = {quantity: 0 for quantity in quantities}

    for part in parts:
        part_number = part[part_number_column]
        manufacturer = part[manufacturer_column] if use_mfr else ""
        part_quantity = int(part[quantity_column])

        part_prices = prices_for_parts.get((part_number, manufacturer))
        cofactr_id = part_prices.cofactr_id if part_prices else None

        current_row = [part_number]
        if use_mfr:
            current_row.append(manufacturer)
        current_row.append(cofactr_id)
        current_row.append(part_quantity)

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

        assert len(current_row) == expected_columns
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
        if use_mfr:
            totals_row.append(None)
        for quantity in quantities:
            totals_row.append(None)
            totals_row.append(str(totals[quantity]))

        assert len(totals_row) == expected_columns
        writer.writerow(totals_row)

    print("Computed COGS", file=sys.stderr)


def price_breakpoints(part_prices: PartPrices | None, quantity: int) -> list[int] | None:
    if part_prices is None:
        return None
    breakpoints = [breakpoint for breakpoint in part_prices.prices.keys() if breakpoint <= quantity]
    return breakpoints if len(breakpoints) > 0 else None


if __name__ == "__main__":
    main()
