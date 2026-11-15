> Historisch verslag van de aangeleverde ZIP. De latere controle en correcties staan in `REVIEW_2026_11_15.md`.

# Status van koppelingen

Stand 14 november 2026. De rekenmotor en de programmagenerator zitten in de webapp, in code en tests; de uitrol en een controle met een echt account moeten nog gebeuren. Externe koppelingen zijn niet gebouwd. De tabel zegt wat er werkelijk is.

| Onderdeel | Geïmplementeerd | Gesimuleerd getest | Werkelijk getest | Geblokkeerd door |
|---|---|---|---|---|
| Rekenmotor → webapp | Ja: engine-API met gebruikerslogin, client en kaart op het scherm Vandaag; starttijd en snelheidsmetadata worden opgeslagen. De weekplanner staat onderaan het weekscherm en maximale inspanningen kunnen bij Profiel worden ingevoerd. | Backend 22 API-tests met zelf ondertekende tokens; frontend 13 tests met nagebootste server; de verzoeken voor berekening en planning zijn elk aan beide kanten tegen één fixture getoetst. | Nee: niet tegen het echte Supabase-project, niet op Render, niet in een browser of op een telefoon. | Uitrol: `SUPABASE_URL` op Render. Daarna één handmatige controle met een echt account. |
| Krachtprogramma's | Ja: generator met doel, ervaring en materiaal, instelkaart op Vandaag, alternatieven in de planeditor. Werkt volledig in de browser; geen server nodig. | 15 frontendtests op de regels. | Nee: niet op een telefoon en niet met een echt account uitgeprobeerd; niet op sporters getest. | — |
| Strava | OAuth, versleutelde tokens en import in `app/integrations/strava.py`, alleen achter de beheersleutel. Niet bereikbaar voor een webappgebruiker. | Bestaande backendtests met nagebootste antwoorden. | Niet door mij. | Koppeling aan gebruikersaccounts; Strava-app-registratie en beleid voor API-gebruik moeten opnieuw bekeken worden. |
| Garmin | Niets in de build. Onbeoordeelde aanzet in `wip/phase3-6/app/integrations/providers.py`. | Nee (de bijhorende tests draaien niet). | Nee. | Toelating tot het Garmin Connect Developer Program, OAuth-configuratie, datamodel en migratie. |
| Wahoo | Idem. | Nee. | Nee. | Registratie van een Wahoo Cloud API-app, OAuth-configuratie, datamodel en migratie. |
| Bestandsimport FIT/TCX/GPX | Niets in de build. Onbeoordeelde parser in `wip/phase3-6/app/science/activity_files.py`. | Nee. | Nee. | Afhankelijkheden (`fitdecode`, `defusedxml`) en een route; echte bestanden van meerdere toestellen om mee te testen. |
| VBT-meters | Handmatige invoer per rep in de webapp. Geen apparaatlaag, geen compatibiliteitslijst. | n.v.t. | Handmatige invoer is gedekt door de frontendtests. | Keuze van apparaten met een gedocumenteerd protocol of export; echte toestellen. |
| Smarttrainer (FTMS/ERG) | Niets in de build. Onbeoordeelde aanzet in `wip/phase3-6/webapp/src/trainer/`. | Nee. | Nee. | Ondersteuning van Web Bluetooth verschilt per browser en moet voor Android en WebView actueel worden nagegaan; echte trainers voor het stop- en pauzegedrag. |
| Workoutgenerator en -export | Niets in de build. Aanzet in `wip/`. | Nee. | Nee. | Geldige CP of drempel per gebruiker; ontwerpkeuzes voor de handmatige route. |
| E-mail voor registratie en herstel | Volgens `docs/accounts_and_storage.md` stond eigen SMTP op 6 november uit. | — | Niet te controleren vanuit deze omgeving. | Instelling in het Supabase-dashboard met een eigen SMTP-sleutel. |

## Eerstvolgende concrete stappen

1. Uitrollen en met een echt account controleren dat de kaart op Vandaag een antwoord krijgt (zie `CHANGELOG.md`, "Nodig bij uitrol").
2. De planner twee trainingen per dag laten voorstellen, samen met DATA-05 (het weekscherm toont er nu één).
3. DATA-04: correctie van een foute sessie.
4. Daarna de programmagenerator, en pas dan providers en hardware, elk met een eigen review van de actuele ontwikkelaarsvoorwaarden.
