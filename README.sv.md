# Matpriskollen för Home Assistant

**Få veta när varorna du köper har extrapris i dina butiker.**

Välj butiker, lägg till varorna du vill bevaka (till exempel *Celsius* eller *Nocco*), sätt ett högsta pris per styck och välj vilka telefoner som ska få en notis. Integrationen läser veckans erbjudanden från butikssidorna på [matpriskollen.se](https://matpriskollen.se).

[English](README.md)

> Det här är en inofficiell integration. Den är inte gjord av, knuten till eller godkänd av Matpriskollen. All erbjudandedata tillhör Matpriskollen. Besök gärna sajten.

## Kom igång

Du behöver [HACS](https://hacs.xyz). Integrationen finns inte i HACS-butiken, så du lägger till den som eget arkiv.

**1. Installera**

[![Öppna i HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=TimmyUll&repository=ha-matpriskollen&category=integration)

Tryck på knappen, sedan **Ladda ner**, och starta om Home Assistant.
(Eller i HACS: **⋮ → Anpassade arkiv**, lägg till `https://github.com/TimmyUll/ha-matpriskollen` som typ *Integration*.)

**2. Välj butiker**

[![Lägg till Matpriskollen](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=matpriskollen)

Skriv en eller flera orter (till exempel `Tyresö, Haninge`) och bocka i butikerna du vill ha. Du kan också klistra in länkar till butikssidor, som `https://matpriskollen.se/butiker/coop-tyreso--…`.

**3. Lägg till varor**

Sista steget i installationen frågar vilka varor du vill bevaka (kommaseparerat, t.ex. `Celsius, Nocco`). Fler lägger du till senare med **Lägg till vara** på integrationens sida. För varje vara anger du:

- **Vara**: märket eller namnet som det står i erbjudandet, t.ex. `Celsius`.
- **Högsta pris per styck** (valfritt): du får en notis, och *Under prisgräns* slås på, när ett erbjudande kostar detta eller mindre per styck. Mängdpriser som *3 för 36,00* räknas som 12,00 kr/st, och flak som *24x33 cl* delas med antalet.
- **Notis till**: telefonerna eller andra notify-tjänster som ska få meddelandet.

När du lägger till en vara kontrolleras den mot veckans sidor för dina butiker. Du ser hur många erbjudanden som finns och det billigaste, eller liknande namn om den inte hittades (t.ex. *Celcius* → *Celsius*).

Pris och notiser ändrar du senare via **⋮** på varan.

## Det här får du

Varje vara får en egen enhet med:

| Entitet | Visar |
| --- | --- |
| Bästa pris | Lägsta pris per styck denna vecka (kr/st) |
| Bästa erbjudande | t.ex. *12,00 kr/st på Coop Tyresö (3 för 36,00)* |
| Under prisgräns | På när någon butik är på eller under din gräns |

Attributen listar alla erbjudanden, billigast först, med butik, storlek och länk. En diagnostiksensor *Senast hämtad* visar när butikerna lästes och om någon misslyckades.

En notis skickas när en vara får nya erbjudanden under gränsen. Samma erbjudanden skickas inte två gånger.

## Schysst mot matpriskollen.se

- Bara publika butikssidor (`/mataffarer` och `/butiker/…`) som sajtens robots.txt tillåter läses. Sökningen och API:er används aldrig.
- Sidorna läses en gång per dygn som standard (minst 6 timmar emellan), med en paus mellan varje butik. Erbjudandena byts varje vecka, så det räcker.
- Senaste resultatet sparas, så en omstart av Home Assistant läser inte sidorna igen.
- Anropen har en User-Agent som länkar hit.

Om Matpriskollen ber om ändringar eller att integrationen ska sluta så respekteras det.

## Begränsningar

- Bara extrapriser som visas på butikssidan hittas, inte ordinarie priser.
- Priser per kg eller liter räknas inte om till styckpris och hamnar därför aldrig under gränsen.
- Om matpriskollen.se ändrar sina sidor kan integrationen sluta hitta erbjudanden tills den uppdateras.

## Licens

MIT
