# Overdracht voor uitrol

Stand 14 november 2026. Voor de ontwikkelaar die deze ZIP nakijkt en naar GitHub pusht. Ik heb niets uitgerold en had geen toegang tot GitHub, Render of Supabase; alles hieronder is lokaal gecontroleerd, tenzij anders vermeld. Dit document bevat alleen namen van variabelen, geen waarden van geheimen.

## Wat er in de ZIP zit

De volledige repository op basis van commit `8bcc3e2`, met de wijzigingen uit `CHANGELOG.md`. Geen `node_modules`, geen virtuele omgeving, geen databases, geen `.env`, geen persoonsgegevens. `CHANGED_FILES.md` somt elk gewijzigd, nieuw en verwijderd bestand op; `RESULT_SHA256SUMS.txt` bevat de controlesommen.

Map `wip/` bevat onafgewerkte aanzetten voor providers, bestandsimport en trainersturing. Ze zitten niet in de build, de tests of het Docker-image. Neem ze niet over naar `app/` of `webapp/src/` zonder review; zie `wip/README.md`.

## Lokaal starten

Vereist: Python 3.11, Node 24 (de CI gebruikt 24; hier is met Node 22 getest), npm.

Backend:

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # vul lokale waarden in; commit dit bestand niet
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Webapp:

```
cd webapp
npm ci
npm run dev
```

De webapp werkt zonder backend: registratie, opslag en programmagenerator lopen via Supabase en de browser. Alleen de kaart van de rekenmotor en de weekplanner hebben de backend nodig; zonder backend tonen ze een melding in plaats van getallen.

## Controles vóór het pushen

```
PYTHONPATH=. DATABASE_URL=sqlite:///./ci_test.db APP_ENV=test python -m pytest -q
cd webapp && npx tsc --noEmit && npm test && npm run build
```

Verwacht: backend 863 geslaagd en 8 overgeslagen; frontend 72 geslaagd. `TEST_RESULTS.md` heeft de details, ook wat niet is uitgevoerd.

## Omgevingsvariabelen

Backend (Render). Waarden staan in het Render-dashboard, niet in de repository.

| Naam | Nodig | Opmerking |
|---|---|---|
| `APP_ENV` | ja | `production` op Render |
| `DATABASE_URL` | ja, geheim | PostgreSQL met TLS, session pooler; zie `docs/free_hosting.md` |
| `ADMIN_API_KEY` | ja, geheim | Minstens 32 tekens; door Render gegenereerd. Alleen voor de beheer-API, nooit in de frontend |
| `REQUIRE_API_KEY`, `AUTO_CREATE_TABLES`, `DEFAULT_OWNER_SUBJECT`, `ALLOWED_ORIGINS` | ja | Staan in `render.yaml` |
| `SUPABASE_URL` | **nieuw**, ja | Publieke project-URL; nodig om gebruikerstokens te controleren voor `/v3/engine/*`. Staat in `render.yaml` |
| `SUPABASE_JWT_AUDIENCE` | optioneel | Standaard `authenticated` |
| `SUPABASE_JWT_SECRET` | optioneel, geheim | Alleen als het project nog HS256-tokens uitgeeft; anders leeg laten |
| `STRAVA_*` | nee | Strava blijft ongeconfigureerd |

Frontend (build): `VITE_ENGINE_URL` is optioneel. Zonder die variabele gebruikt de app op `github.io` het Render-adres en elders hetzelfde domein. De publieke Supabase-URL en de publieke sleutel staan zoals voorheen in de frontendcode; de service-role-sleutel hoort daar niet en staat er niet.

## Migraties

- Backend (Alembic): geen nieuwe revisie; de laatste blijft 006. `python -m deployment.serve` voert bij elke start `alembic upgrade head` uit, dus er gebeurt niets nieuws.
- Supabase: geen nieuwe migratie. Starttijd, snelheidsmetadata, maximale inspanningen en programma-instellingen zitten in de bestaande JSON-velden van profiel en training; oude records zonder die velden blijven geldig en worden niet herschreven.
- `wip/phase3-6/alembic/versions/007_provider_connections.py` is **niet** actief en mag niet naar `alembic/versions/` zonder de bijhorende modellen en review.

## Uitrollen

1. Push naar een branch en laat de drie workflows lopen (`ci.yml`, `hosting.yml`, `deploy-webapp.yml`). `hosting.yml` bouwt het Docker-image, dat ook de frontendtests draait.
2. Merge naar `main`. GitHub Pages bouwt de webapp; Render rolt uit zodra de controles slagen, als de service als blueprint aan de repository hangt.
3. Controleer in Render dat `SUPABASE_URL` is gezet. Bij een service die niet als blueprint is gekoppeld moet dat met de hand.
4. Controleer na de uitrol:
   - `GET /ready` geeft 200.
   - `GET /v3/engine/version` geeft `accounts_configured: true`.
   - `POST /v3/engine/evaluate` zonder token geeft 401.
   - Inloggen met een bestaand account toont de bestaande trainingen; op Vandaag verschijnt de kaart van de rekenmotor met een antwoord of met "onvoldoende gegevens", niet met een foutmelding.
   - De kaart "Krachtprogramma" bewaart een keuze en het weekoverzicht toont daarna "sessie A/B".

Render Free slaapt na 15 minuten; de eerste aanvraag kan ongeveer een minuut duren. De app toont dan een melding en geen getallen.

## Terugdraaien

- Code: zet `main` terug naar de vorige commit; Pages en Render rollen opnieuw uit. In Render kan ook een eerdere deploy opnieuw actief worden gemaakt.
- Gegevens: er is geen schemawijziging, dus er is niets terug te migreren. Profielen die al programma-instellingen of snelheidsmetadata bevatten, blijven leesbaar voor de oude code: die negeert de extra velden. Trainingen die met de nieuwe versie zijn gelogd, blijven bestaan.
- `SUPABASE_URL` mag blijven staan; de oude code gebruikt ze niet.

## Registraties bij derden

Niets hiervan is gebouwd of aangevraagd. Ze zijn pas nodig voor prioriteit 5 en 6 van de opdracht; zie `INTEGRATION_STATUS.md`.

| Dienst | Wat nodig is | Geheimen (alleen op de server) |
|---|---|---|
| Garmin | Toelating tot het Garmin Connect Developer Program en een app met redirect-URL | client-id en client-secret |
| Wahoo | Een app voor de Wahoo Cloud API met redirect- en webhook-URL | client-id, client-secret, webhook-token |
| Strava | Herbekijken van de bestaande app en de API-voorwaarden | `STRAVA_CLIENT_SECRET`, `STRAVA_TOKEN_ENCRYPTION_KEY` |
| E-mail | Eigen SMTP in Supabase voor registratie en herstel | SMTP-sleutel in het Supabase-dashboard |

## Bekende open punten

Zie `AUDIT_REPORT.md`: DATA-04 (gelogde trainingen corrigeren of verwijderen kan niet), DATA-05 (weekscherm toont één training per dag), de datumbeperking in de database als voorstel, en de menging van UTC en lokale tijd. Niets hiervan is door deze ZIP verergerd.
