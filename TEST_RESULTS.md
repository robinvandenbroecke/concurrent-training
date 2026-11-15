> Historisch verslag van de aangeleverde ZIP. De latere controle en correcties staan in `REVIEW_2026_11_15.md`.

# Testresultaten

Uitgevoerd op 13 en 14 november 2026 in een afgesloten Linux-omgeving, zonder toegang tot GitHub, Render, Supabase of hardware.

## Versies

Python 3.11.18. Pakketten volgens `requirements.txt` (sinds 14 november ook PyJWT 2.15.1): fastapi 0.162.7, starlette 1.10.0, pydantic 2.14.3, pydantic-settings 2.16.3, sqlalchemy 2.0.27, alembic 1.13.1, cryptography 50.0.2, uvicorn 0.54.0, httpx 0.28.1, numpy 1.26.3, pytest 9.2.0, pytest-asyncio 1.5.0. PostgreSQL 16.15 (lokale wegwerpinstantie).

Node v22.23.4 met npm 10.9.9. **Afwijking:** `package.json` en de Dockerfile vragen Node 24 of hoger. Node 24 was hier niet beschikbaar. De frontendresultaten moeten in CI op Node 24 bevestigd worden.

## Uitgangstoestand zoals aangeleverd

| Commando | Resultaat |
|---|---|
| `sha256sum -c SOURCE_SHA256SUMS.txt` | Alle 306 bestanden in orde; 36 extra bestanden buiten de lijst |
| `pytest -q` (oude pins) | Afgebroken bij verzamelen: `ModuleNotFoundError: jwt` in `tests/test_v3_api.py` |
| `pytest -q` zonder de drie nieuwe testbestanden | 786 geslaagd, 1 gefaald (`test_readiness_requires_current_migrations…`, door migratie 007), 8 overgeslagen |
| `pytest` op de drie nieuwe testbestanden, na installatie van PyJWT | 30 geslaagd, 1 gefaald, 22 errors |
| `npx tsc --noEmit` | Fouten in `generator.ts`, `engine/client.ts`, `trainer/ftms.ts`; `npm run build` faalt daardoor |
| `npm test` | 43 geslaagd |
| `pip-audit -r requirements.txt --no-deps --disable-pip` | 16 bekende kwetsbaarheden in 4 pakketten |

## Eindtoestand

Backend, vanuit de projectmap met `PYTHONPATH=. DATABASE_URL=sqlite:///./ci_test.db APP_ENV=test`:

| Commando | Resultaat |
|---|---|
| `python -m compileall -q app run_validation.py` | Geslaagd |
| `pytest -q` | **863 geslaagd, 8 overgeslagen, 0 gefaald** (14 november, na model, koppeling en planner; 824 op 13 november) |
| `pytest -q tests/test_engine_api.py` | 22 geslaagd |
| `pytest -q tests/test_science_engine.py tests/test_concurrent_model.py` | 49 geslaagd |
| `pytest -q tests/test_audit_2026_11.py` | 5 geslaagd |
| `python run_validation.py --source db --athlete-id 1 --days 30` | Exitcode 0 |
| `python -m research.evaluate --manifest research/example_manifest.json --events research/example_events.csv --output …` en vergelijking met `artifacts/audit_2026_09/reference_demo.json` (tolerantie 1e-12) | Identiek gereproduceerd |
| `pip-audit -r requirements.txt --no-deps --disable-pip` | Geen bekende kwetsbaarheden |
| `pip-audit -l` (volledige omgeving, inclusief transitieve pakketten) | Geen bekende kwetsbaarheden |

De acht overgeslagen tests staan in `tests/test_strength_csv_import.py` en melden "Fixture file not found". Dat was al zo in de uitgangstoestand; het fixturebestand zit niet in de repository.

De PostgreSQL-stappen hieronder zijn op 13 november uitgevoerd en op 14 november niet herhaald; sindsdien is er niets aan schema, migraties of afhankelijkheden veranderd.

PostgreSQL, met `DATABASE_URL=postgresql://…@127.0.0.1:5433/concurrent_training APP_ENV=test AUTO_CREATE_TABLES=false`, dezelfde stappen als de CI-job `migration-postgres`:

| Commando | Resultaat |
|---|---|
| `alembic upgrade head` | Geslaagd tot revisie 006 |
| Schemacontrole revisie 006 (kolommen `owner_subject`, `slot`; index en unieke constraint) | Geslaagd |
| `alembic downgrade 005` en opnieuw `alembic upgrade head` | Geslaagd |
| `python -m deployment.check_postgres` | "Private hosting schema, encoded credentials, data retention and Data API isolation verified" |
| `python -m deployment.check_cloud_storage` (voert `supabase/tests/ownership.sql` uit met een `auth.uid()`-stub) | "Cloud account ownership, anonymous denial, append-only sessions and stale revision rejection verified" |

Frontend, in `webapp/` na `npm ci`:

| Commando | Resultaat |
|---|---|
| `npx tsc --noEmit` | Geen fouten |
| `npm test` | **72 geslaagd, 0 gefaald** (57 vóór de programmagenerator; 44 op 13 november) |
| `npm run build` | Geslaagd |
| `npm audit` en `npm audit --omit=dev` | 0 kwetsbaarheden |

## Gericht bewijs bij de correcties

| Bevinding | Bewijs |
|---|---|
| SCI-02 | Simulatie met alleen ruis, vier kalibratiepunten, 2.000 herhalingen: oude regel 8,2 % valse signalen, nieuwe regel 1,9 %. De test in de suite gebruikt 400 herhalingen met vaste seed en eist minder dan 8 % voor de nieuwe en meer dan 8 % voor de oude regel. |
| SEC-02 | De nieuwe test faalt met de oude vergelijking en slaagt met de nieuwe. |
| LEG-01 | Voor de correctie: voorspelde snelheid 0,012 m/s bij een referentie van 0,60 m/s; erna gelijk aan een expliciet onvermoeide start. |
| LEG-02 tot LEG-04 | Gemeten waarden staan in `AUDIT_REPORT.md`; de tests leggen het huidige gedrag vast. |

## Concurrent model (14 november)

Alle cijfers komen van gesimuleerde atleten die per constructie het model volgen. Ze toetsen de schatter en de beslisregels, niet de werkelijkheid.

| Toets | Resultaat |
|---|---|
| Terugvinden van vermoeidheid en kruisvermoeidheid (12 reeksen van 240 dagen) | Afwijking kleiner dan 0,02; het 95 %-interval dekt de waarheid in minstens 10 van 12 reeksen; meer dan 80 % door data bepaald |
| Wisselwerking aanwezig (0,05) of afwezig, 10 reeksen elk | Gemeld in minstens 9 van 10 respectievelijk hoogstens 1 van 10 |
| Detectie en vals alarm bij realistische ruis, 40 reeksen per conditie | Tabel in `MODEL_REGISTER.md`, deel D |
| Alleen ruis als uitkomst | Geen dynamiek en geen wisselwerking gemeld |
| Nauwelijks variërende training | Fitnessterm voor minder dan 30 % door data bepaald |
| Vooruitlopende voorspelling, één reeks met 107 toetsen | Fout 0,013 (volledig) < 0,020 (zonder wisselwerking) < 0,026 (niveau) < 0,030 (laatste waarneming); dekking 96 % |
| Duurkant, 10 reeksen | Kruisvermoeidheid door kracht gedekt en gemeld in minstens 8 van 10 |
| Planner tegenover volledige zoektocht (5 sessies, 10 sloten, 30.240 indelingen) | Zelfde beste score na 723 evaluaties in 0,1 s tegenover 4,2 s |
| Engine op 3.000 sessies | 1,8 s (was 13 s voor PERF-01) |

## Koppeling van de rekenmotor (14 november)

| Toets | Resultaat |
|---|---|
| Tokens: geldig, verlopen, verkeerde ontvanger of uitgever, rol `anon` of `service_role`, anonieme sessie, onbekende sleutel, andere sleutel, `alg: none`, HS256 met de publieke sleutel | Alleen het geldige gebruikerstoken wordt aanvaard |
| Engine zonder login, met de beheersleutel, of zonder geconfigureerd project | 401, 401 en 503 |
| Te groot of ongeldig verzoek, onbestaande datum, andere contractversie | 413, 422 met alleen veldnamen, 409 |
| Limiet per gebruiker | Derde aanroep 429; een andere gebruiker wordt niet geraakt |
| CORS | `Authorization` toegelaten voor de Pages-oorsprong, niet voor een vreemde |
| Gehoste opstelling met verplichte beheersleutel | `/v3` bereikbaar met gebruikerstoken; de onderzoeks-API blijft dicht |
| Verzoek uit de webapp tegen de Python-engine (gedeelde fixture) | Aanvaard; signaal "explosief werk binnen 3 uur" met 1,5 uur en volgorde, snelheidsprofiel per meter en maat |
| Webapp: verzoek zonder naam, titel of notitie; cache per invoer; elke foutcode geeft een melding en geen getal; kaart rendert | Geslaagd |
| Planner: omzetting naar dosis; verzoek uit de webapp tegen de Python-planner (gedeelde fixture, 6 volgordes volledig doorgerekend); overnemen alleen als volledige verwisseling; kaart verstuurt niets voor de knop en past niets toe zonder bevestiging | Geslaagd |

De tokens in deze tests zijn hier ondertekend met een wegwerpsleutel. Dat bewijst de controlelogica, niet de werking tegen het echte Supabase-project.

## Krachtprogramma's (14 november)

`webapp/tests/generator.test.tsx`, 15 tests, alle geslaagd. Ze toetsen regels, geen trainingseffect:

| Regel | Hoe getoetst |
|---|---|
| Alleen oefeningen die met het materiaal kunnen, binnen het techniekniveau, zonder dubbels | Ruim 3000 gegenereerde sessies over alle doelen, ervaringsniveaus, materiaalkeuzes, 1 tot 6 dagen en 30 tot 90 minuten |
| Sessie past in de tijd of benoemt wat is ingekort; rusttijden blijven gelijk | 75 combinaties plus vergelijking van 30 en 120 minuten |
| Ontbrekend materiaal geeft een andere oefening in hetzelfde patroon of een gemelde lege plaats | Dumbbells, machines en geen materiaal |
| Gewicht alleen uit dezelfde oefening of het intakegewicht bij zes herhalingen of minder | Logs van een andere oefening, van dezelfde oefening en met een latere datum |
| Progressie is een suggestie; zonder gelogde RPE geen suggestie | Vijf loggeschiedenissen |
| Geen inhaalvolume na gemiste trainingen | Vergelijking met en zonder gat van tien weken |
| Vast schema standaard; lichtere vierde week en herstart alleen op verzoek | Weekregels en gegenereerde sessies in week 1, 3 en 4 |
| Profiel zonder programma krijgt het oorspronkelijke schema; eigen aanpassing van een dag gaat voor | `buildWeek` met en zonder instellingen |
| De kaart bewaart pas op verzoek, laat de rest van het profiel ongemoeid en kan terugdraaien | Weergave in jsdom |

De bestaande test op de catalogus verwacht nu 58 oefeningen in plaats van 42.

## Niet uitgevoerd

- Docker-build en de CI-workflows zelf.
- De uitrol van de koppeling: `SUPABASE_URL` op Render, en een controle met een echt account in een browser.
- Controle tegen de echte Supabase-omgeving (RLS, Auth, e-mail), de Render-service en GitHub Pages.
- Strava-, Garmin- en Wahoo-koppelingen: geen credentials en geen providertoegang.
- VBT-meters, smarttrainers en Bluetooth: geen hardware. Er is in deze ronde ook geen code voor opgeleverd.
- Tests op een telefoon of in een echte browser; toegankelijkheidstoets.
- De tests in `wip/phase3-6/tests/` horen bij onaf werk en draaien niet mee.
