# Matpriskollen for Home Assistant

**Get told when the products you buy are on offer in your local stores.**

Pick your stores, add the products you want to follow (for example *Celsius* or *Nocco*), set a highest price per item and choose which phones get a notification. The integration reads this week's offers from the store pages on [matpriskollen.se](https://matpriskollen.se).

[Svenska instruktioner](README.sv.md)

> This is an unofficial integration. It is not made by, affiliated with or endorsed by Matpriskollen. All offer data belongs to Matpriskollen. Please use the site for what it offers, and visit it.

## Get started

You need [HACS](https://hacs.xyz). The integration is not in the HACS store, so you add it as a custom repository.

**1. Install**

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=TimmyUll&repository=ha-matpriskollen&category=integration)

Press the button, then **Download**, and restart Home Assistant.
(Or in HACS: **⋮ → Custom repositories**, add `https://github.com/TimmyUll/ha-matpriskollen` as type *Integration*.)

**2. Choose stores**

[![Add Matpriskollen](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=matpriskollen)

Type one or more towns (for example `Tyresö, Haninge`) and tick the stores you want. You can also paste links to store pages, like `https://matpriskollen.se/butiker/coop-tyreso--…`.

**3. Add products**

The last setup step asks which products to follow (comma-separated, e.g. `Celsius, Nocco`). Later you can add more with **Add product** on the integration page. For each product you set:

- **Product**: the brand or name as written in the offer, e.g. `Celsius`.
- **Max price per item** (optional): you are notified, and *Under price limit* turns on, when an offer costs this or less per item. Multi-buy offers like *3 för 36,00* count as 12,00 per item, packs like *24x33 cl* are divided by the pack size, and *3 för 2* next to a price per item counts as two thirds of it.
- **Notify**: the phones or other notify services that should get a message.

Products are checked against this week's pages of your stores, both during setup and when you add one later: you see how many offers there are and the cheapest one, or similar names if it was not found (e.g. *Celcius* → *Celsius*).

You can change price and notifications later with the **⋮** menu on the product.

## What you get

Each product gets its own device with:

| Entity | Shows |
| --- | --- |
| Best price | Lowest price per item this week (kr/st) |
| Best offer | e.g. *12,00 kr/st på Coop Tyresö (3 för 36,00)* |
| Under price limit | On when some store is at or below your limit |

The attributes list every offer found, cheapest first, with store, size and a link. A diagnostic *Last fetch* sensor shows when the stores were last read and if any failed.

A notification is sent when a product gets new offers under the limit. The same offers are not sent twice.

## Fair use of matpriskollen.se

The integration tries to be a polite visitor:

- It only reads public store pages (`/mataffarer` and `/butiker/…`) that the site's robots.txt allows. It never uses the search or any API.
- Pages are read once a day by default (at least 6 hours apart), with a pause between each store. Offers change weekly, so this is enough.
- The last result is saved, so a restart of Home Assistant does not read the pages again.
- Requests identify themselves with a User-Agent that links to this repository.

If Matpriskollen asks for changes or for this integration to stop, that will be respected.

## Limits

- Only offers (*extrapriser*) shown on the store page are found, not regular prices.
- Prices per kg or litre are not turned into a price per item, so they never count as under the limit.
- If matpriskollen.se changes its pages the integration may stop finding offers until it is updated.

## License

MIT
