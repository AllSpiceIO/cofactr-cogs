# Cofactr COGS

Generate cost of goods sold (COGS) using Cofactr.

## Usage

Add the following step to your actions:

```yaml
- name: Generate COGS using Cofactr
  uses: https://hub.allspice.io/Actions/cofactr-cogs@main
  with:
    bom_file: bom.csv
    quantities: "1,10,100,1000"
    client_id: YOUR_COFACTR_CLIENT_ID
    api_key: ${{ secrets.COFACTR_API_KEY }}
    output_file: cogs.csv
```
