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
    api_key: YOUR_COFACTR_API_KEY
    client_id: YOUR_COFACTR_CLIENT_ID
    output_file: cogs.csv
```
