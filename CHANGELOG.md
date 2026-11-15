# Changelog

## 14 november 2026 — krachtprogramma's en programmagenerator

### Toegevoegd

- Programmagenerator `webapp/src/domain/generator.ts`: krachtsessies volgens doel (algemeen, powerlifting, spiergroei, power, kracht naast duursport), ervaring en beschikbaar materiaal. Toelichting en bronnen in `docs/strength_programs.md`.
- Kaart "Krachtprogramma" op het scherm Vandaag om doel, ervaring, materiaal, herstart en een facultatieve lichtere week te kiezen. Er verandert niets tot de sporter bewaart; terugkeren naar het oorspronkelijke schema kan altijd.
- Zestien oefeningen voor beperkt materiaal (dumbbells, kettlebell, machines, lichaamsgewicht); de catalogus telt er nu 58. Elke oefening heeft een bewegingspatroon, benodigd materiaal en techniekniveau.
- De planeditor zet bij vervangen eerst de oefeningen met hetzelfde bewegingspatroon die met het materiaal van de sporter kunnen.
- `webapp/tests/generator.test.tsx` met 15 tests.

### Gewijzigd

- Met programma-instellingen krijgt een sporter met prioriteit "duur" en twee trainingsdagen één krachttraining per week (was nul). Zonder instellingen is er niets veranderd.
- Type `AthleteProfile` heeft een optioneel veld `program`. Het profiel wordt als één geheel bewaard; er is geen migratie nodig.

### Niet gewijzigd

- Accounts zonder programma-instellingen krijgen exact het oorspronkelijke startschema. Gelogde trainingen en zelf aangepaste dagen worden niet herschreven. Backend, database en afhankelijkheden zijn ongewijzigd.

### Beperkingen

- De set- en herhalingsgetallen zijn startpunten uit groepsonderzoek en vuistregels, geen individueel optimum, en niet op sporters getest.
- Op een echt toestel of met een echt account is de kaart niet uitgeprobeerd.

## 14 november 2026 — weekplanner en maximale inspanningen in de app

### Toegevoegd

- **Volgorde doorrekenen** (`webapp/src/components/WeekPlanner.tsx`, onderaan het weekscherm). Neemt de geplande trainingen van morgen tot zeven dagen vooruit, ook over de weekgrens, en vraagt de engine in welke volgorde je aan elke training het frist begint. De trainingen en de dagen blijven dezelfde; alleen de volgorde wisselt. Je kunt een training als belangrijkste aanduiden en kiezen of je 's ochtends of 's avonds traint. Het resultaat toont per training het verwachte effect met onzekerheid, zegt of het op eigen metingen of op groepsaannames berust, en wordt pas in de planning gezet na "Deze volgorde overnemen". Er wordt niets verstuurd voor je op de knop drukt.
- **Omzetting van een geplande training naar dosis** (`planItem` in `src/engine/client.ts`): werksets per regio voor kracht, opwarmsets tellen niet; minuten met een aangenomen relatieve intensiteit per type voor duur. Titels van trainingen gaan niet mee.
- **Overnemen als één bewerking** (`api.applyArrangement`): alleen een volledige verwisseling van nog geplande dagen wordt aanvaard, zodat er geen training verdwijnt of op een bezette of voorbije dag belandt.
- **Maximale inspanningen** (bij Profiel op Vandaag): datum, duur van 2 tot 20 minuten en gemiddeld vermogen, maximaal twintig. Ze gaan mee naar de engine voor de critical-powerfit. De kaart legt in gewone woorden uit waarom een fit ontbreekt of twijfelachtig is.
- **Tests.** Zes nieuwe frontendtests en één backendtest; het plannerverzoek van de webapp is bevroren in `client_plan_request_v1.json` en wordt aan beide kanten getoetst.

### Gewijzigd

- Fout 422 van de engine geeft in de app een eigen melding in plaats van de algemene.
- De tekst op het weekscherm verwijst naar de planner in plaats van naar "toekomstig werk".

### Beperkingen

De planner verwisselt hele dagen en kent één tijdslot. Twee trainingen op één dag kan hij in de app nog niet voorstellen, al ondersteunt de engine dat. De critical power geldt voor de fiets; een tweede profiel voor lopen bestaat nog niet.

## 14 november 2026 — koppeling van de rekenmotor aan de app

### Toegevoegd

- **Opslag (DATA-06).** Een sessie bewaart nu haar starttijd (`startTime`), en elke set met snelheden de meter en de snelheidsmaat (`velocityMeta`). Beide velden zijn optioneel: bestaande records blijven geldig en worden niet herschreven, en de databaseconstraint hoeft niet te wijzigen. Een duurtraining die achteraf wordt ingevoerd krijgt geen starttijd, omdat die dan een gok zou zijn.
- **Instelling snelheidsmeter.** Bij Profiel op het scherm Vandaag, zichtbaar als VBT aanstaat: snelheidsmaat en meter. De keuze wordt bij het opslaan op nieuwe metingen gezet en overschrijft nooit een bestaande aanduiding.
- **Engine-API** `app/api_v3.py`: `GET /v3/engine/version`, `POST /v3/engine/evaluate`, `POST /v3/engine/plan`. Toegang met het eigen Supabase-sessietoken van de gebruiker, gecontroleerd tegen de publieke sleutels van het project (`app/auth_supabase.py`); de beheersleutel speelt geen rol. Stateless: de server bewaart geen trainingsgegevens. Limiet van 8 MB per verzoek en 30 verzoeken per minuut per gebruiker; foutmeldingen noemen alleen veldnamen, nooit ingestuurde waarden. Het rekenwerk loopt in een threadpool.
- **Webapp.** `src/engine/client.ts` bouwt het verzoek uit de eigen sessies zonder naam, titels of notities, en bewaart het laatste antwoord per invoer. `src/components/EngineCard.tsx` vervangt op Vandaag de lege belastbaarheidskaart en toont belasting, kracht-duursignalen, de modelverwachting met onzekerheid en de 1RM- en snelheidsuitspraken, telkens met de reden wanneer een uitspraak niet kan. Zonder login of zonder bereikbare server staat er een melding en geen nagebootst resultaat.
- **Configuratie.** `SUPABASE_URL` in `render.yaml` en `.env.example`; `Authorization` toegelaten in CORS; `PyJWT[crypto] 2.15.1` in `requirements.txt`.
- **Tests.** `tests/test_engine_api.py` (21 tests: geldige en ongeldige tokens, algoritmeverwarring, onbekende sleutels, limieten, CORS, de gehoste opstelling) en `webapp/tests/engine.test.tsx` (7 tests, waaronder het renderen van de kaart). Het verzoek dat de webapp bouwt is bevroren in `webapp/tests/fixtures/contracts/client_request_v1.json` en wordt aan beide kanten getoetst.

### Gewijzigd

- De test van de volledige appflow verwacht op Vandaag de nieuwe kaart in plaats van "Onbekend".
- `wip/phase3-6/` bevat alleen nog de onafgewerkte delen voor fase 4 tot 6.

### Nodig bij uitrol

Deze stappen zijn niet uitgevoerd; ze vragen toegang tot Render. Na het pushen neemt Render `SUPABASE_URL` over uit `render.yaml`, als de service als blueprint is gekoppeld; anders moet de variabele met de hand worden gezet. Tot dan antwoordt de engine met 503 en toont de app "nog niet gekoppeld aan accounts". Controleer daarna `GET /v3/engine/version`: `accounts_configured` moet `true` zijn.

## 14 november 2026 — nieuw concurrent model

### Toegevoegd

- `app/science/concurrent.py` (`ct-concurrent-1.0.0`): toestandsmodel voor kracht en duur met expliciete wisselwerking (acute kruisvermoeidheid in beide richtingen, afgezwakte krachtadaptatie bij sessies binnen drie uur, transfer van kracht naar duur), Bayesiaanse kalibratie per atleet, geneste modelvergelijking, vooruitlopende voorspeltoets en weekplanning. Beschrijving en onderbouwing in `MODEL_REGISTER.md`, deel D.
- `app/science/concurrent_service.py`: leidt dosis en prestatiewaarnemingen af uit opgeslagen sessies en telt elke aanname; `plan_week` rangschikt weekindelingen.
- `app/science/contract.py`: `PlanRequest` en `PlanSessionIn`.
- De engine-uitvoer heeft een nieuw blok `concurrent_model`. `ENGINE_VERSION` is `ct-engine-3.2.0`; het contract blijft versie 1 omdat er alleen een veld bijkomt.
- `tests/test_concurrent_model.py`: 17 tests (wiskundige eigenschappen, terugvinden van parameters op gesimuleerde atleten, vals-alarmpercentage, planning, service).

### Hersteld

- **PERF-01** `app/science/service.py`: de zoektocht naar een bevroren kalibratieprofiel paste het profiel opnieuw op elk beginstuk van de historie. Bij 1.500 krachtsessies zonder geldig profiel duurde één engine-aanroep 13 seconden; nu 1,8. De zoektocht is begrensd tot de eerste twaalf sessies met snelheidsmeting.

### Niet gewijzigd

Het oude model onder `app/domain` blijft staan als onderzoekscode. De webapp, het opslagformaat en de databases zijn niet aangeraakt.

## 13 november 2026 — audit fase 1 en 2

Basis: `main` op commit `8bcc3e2f26cd12b2a32cbe429bf0e6f80c4b2e6e`. De nummers verwijzen naar `AUDIT_REPORT.md`.

### Hersteld

- **BLD-01** Zestien niet-bouwbare bestanden van een afgebroken eerdere uitvoering verplaatst naar `wip/phase3-6/`. `pytest.ini` beperkt de tests tot `tests/`; `.dockerignore` sluit `wip` uit.
- **SEC-01** `requirements.txt`: fastapi 0.109.0 → 0.162.7, pydantic 2.6.1 → 2.14.3, pydantic-settings 2.1.0 → 2.16.3, cryptography 42.0.5 → 50.0.2, uvicorn 0.27.0 → 0.54.0, httpx 0.26.0 → 0.28.1, python-dotenv 1.0.0 → 1.2.4, pytest 8.0.0 → 9.2.0, pytest-asyncio 0.23.5 → 1.5.0.
- **SEC-02** `app/main.py`: API-sleutel wordt op bytes vergeleken; een sleutel met niet-ASCII-tekens geeft een weigering in plaats van een serverfout.
- **DATA-01** `webapp/src/api/local.ts`: import weigert niet-bestaande datums (`isCalendarDate`). `app/science/contract.py`: idem voor sessiedatum, peildatum en datum van een maximale inspanning.
- **DATA-02** `app/science`: exacte dubbele sessies worden genegeerd en geteld; tegenstrijdige records met dezelfde id worden geweigerd.
- **DATA-03** `start.sh` wist de lokale database niet meer en bevat geen vast pad.
- **UI-01** `webapp/src/data/demoData.ts` met verzonnen belastbaarheid, historie en trend verwijderd; weergavenamen staan in `data/names.ts`. Ongebruikte `getProfile` uit `api/adapter.ts` verwijderd.
- **SCI-01** `app/science/service.py`: een vermogensreferentie geldt alleen voor de sport van het duurprofiel.
- **SCI-02** `app/science/load_velocity.py`, `service.py`: ruisgrens volgt de Student-t-verdeling; `noise_limit` in de uitvoer.
- **SCI-03** `app/science/critical_power.py`: beste inspanning per duur; waarschuwingen voor sets zonder inspanning van tien minuten of langer, voor verspreide of ongedateerde inspanningen; documentatie in lijn met de code (2–20 minuten).
- **SCI-04** `app/science/strength_estimates.py`: Brzycki in plaats van Epley met uitzondering; methode heet nu `brzycki_with_reported_rir`.
- **SCI-05** `app/science/service.py`: concurrent signaal bevat `order` en `lower_body_strength_work`; explosief werk voor alleen het bovenlichaam krijgt niet langer de bronverwijzing.
- **LEG-01** `app/domain/rep_engine.py`: een lift zonder beginstatus start onvermoeid.
- **BLD-03** Kop van `README.md` beschrijft de accountopslag en de werkelijke status.

### Gewijzigde uitvoer van de engine

`ENGINE_VERSION` is `ct-engine-3.1.0`. `CONTRACT_VERSION` blijft `1`: er zijn alleen velden bijgekomen (`duplicate_sessions_ignored`, `reference.sport`, `noise_limit`, `order`, `lower_body_strength_work`, `power_not_used`) en de waarde van `e1rm_estimate.method` is veranderd. Getallen van de 1RM-schatting verschillen van 3.0.0. De fixtures in `webapp/tests/fixtures/contracts/` zijn opnieuw gegenereerd. Er was nog geen opgeslagen engine-uitvoer bij gebruikers, dus er is niets te herberekenen.

### Toegevoegd

- `tests/test_audit_2026_11.py`: regressietests voor LEG-01 en SEC-02, en drie tests die bekende gebreken van het oude model vastleggen (LEG-02, LEG-03, LEG-04).
- Acht tests in `tests/test_science_engine.py` voor SCI-01 tot SCI-05, DATA-01 en DATA-02, waaronder een simulatie van het percentage valse signalen.
- Eén test in `webapp/tests/local.test.tsx` voor DATA-01.
- `AUDIT_REPORT.md`, `MODEL_REGISTER.md`, `TEST_RESULTS.md`, `INTEGRATION_STATUS.md`, `wip/README.md`.

### Niet gewijzigd

Databaseschema en migraties (Supabase en Alembic), login en registratie, opslagformaat van sessies en profiel, schermen en huisstijl. Er zijn geen bestaande meetgegevens herschreven.
