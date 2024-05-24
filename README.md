# Cofactr COGS

Generate cost of goods sold (COGS) in AllSpice Actions using Cofactr.

This uses the Cofactr API.  See the [Cofactr API docs](https://help.cofactr.com/en/articles/8868930-cofactr-component-cloud-api-documentation) for more information.

## Usage

Add the following step to your actions:

```yaml
- name: Generate COGS using Cofactr
  uses: https://hub.allspice.io/Actions/cofactr-cogs@v1
  with:
    bom_file: bom.csv
    bom_part_number_column: Part Number
    bom_manufacturer_column: Manufacturer
    bom_quantity_column: Quantity
    quantities: "1,10,100,1000"
    search_strategy: mpn_sku_mfr
    client_id: YOUR_COFACTR_CLIENT_ID
    api_key: ${{ secrets.COFACTR_API_KEY }}
    output_file: cogs.csv
```
