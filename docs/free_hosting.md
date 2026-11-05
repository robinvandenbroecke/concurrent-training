# Gratis hosting: status en ingebruikname

## Status op 5 november 2026

- De gecombineerde webapp en Python-API zijn live op [Render](https://concurrent-training.onrender.com/concurrent-training/). De bestaande [GitHub Pages-app](https://robinvandenbroecke.github.io/concurrent-training/) blijft beschikbaar.
- De Free-webservice `concurrent-training` draait in Frankfurt in de aparte Render-werkruimte **Concurrent Training**. Workspace-ID: `tea-dbmdl10u01pc73a8f5ng`; service-ID: `srv-dbmdoomk1f9s73dhr2l0`.
- Supabase-project `concurrent-training` gebruikt het Free-plan in Frankfurt. Projectreferentie: `dvwbkbohdgfuzjenrete`. De API gebruikt TLS en de session pooler met een eigen database-login `ct_backend_app`. Deze login heeft geen superuser-, databasecreatie- of rolcreatierechten.
- De migraties hebben 13 tabellen met RLS aangemaakt in het private schema `ct_backend`, met `ct_backend_app` als eigenaar. De rollen `anon` en `authenticated` hebben geen toegang tot dit schema. Dit is infrastructuurisolatie; gebruikersauthenticatie en autorisatie per atleet zijn nog niet aangesloten.
- Deploy `dep-dbme0cmgekts73b2ad40` van commit `4340f576f256c81f759c0943478ac23638857728` is op 5 november 2026 om 20:00 UTC als `live` bevestigd. `/ready` gaf HTTP 200 met een verbonden database. De webapp en alle vier gekoppelde buildassets laadden. Een API-aanroep zonder sleutel gaf 401, met een onjuiste sleutel 403 en met de geldige beheersleutel 200.
- Databasewachtwoord en beheer-API-sleutel zijn als geheime Render-omgevingsvariabelen ingesteld. Ze staan niet in deze repository of de frontend.
- Garmin- en Wahoo-synchronisatie zijn nog niet geïmplementeerd of actief. Er zijn geen providercredentials ingesteld of persoonlijke trainingsgegevens geïmporteerd.

Controles op de hostingcode: 787 Python-tests geslaagd (8 bestaande skips), 34 frontendtests geslaagd, productiebuild geslaagd en `render.yaml` gevalideerd tegen het actuele officiële JSON-schema. GitHub Actions heeft ook het volledige Docker-image gebouwd, de weigering van tijdelijke SQLite-opslag getest, de PostgreSQL-migraties uitgevoerd en private-schema-isolatie met behoud van gegevens na herhaalde startup bevestigd. Zie [CI](https://github.com/robinvandenbroecke/concurrent-training/actions/runs/42095999283) en [containerbuild](https://github.com/robinvandenbroecke/concurrent-training/actions/runs/42095999585). De live controles hierboven zijn aanvullend uitgevoerd; er zijn daarbij geen persoonlijke trainingsgegevens geïmporteerd.

## Wat de configuratie doet

`render.yaml` beschrijft één Free-webservice in Frankfurt. Het Docker-image bouwt en test de bestaande React-app en biedt die aan op `/concurrent-training/`. De root verwijst naar dat pad. De bestaande Python-API behoudt haar URLs en beheer-API-sleutel. `/ready` controleert verbinding én migratieversie van de database. `/health` is de bestaande, eenvoudigere livenesscontrole.

De frontend blijft in deze versie een lokaal prototype. Hosting van de API verbindt de browserhistorie niet automatisch met de database. Accounts, autorisatie per atleet en synchronisatie tussen toestellen moeten afzonderlijk worden aangesloten. Zet de beheer-API-sleutel nooit in de webapp, een `VITE_`-variabele, een URL of een GitHub-bestand. Deze beheer-API is bedoeld voor een privéprototype, niet als gedeelde gebruikerslogin.

## Database en secrets

Gebruik uitsluitend de aparte Concurrent Training-database. Kopieer de verbindingsstring uit het Supabase-dashboard: **Connect → Session pooler**, voor een verbinding vanaf Render. Neem host en gebruikersnaam over uit die string; leid de poolerhost niet af uit de regio. Gebruik **session mode**, geen transaction mode: opstartmigraties gebruiken een sessiegebonden PostgreSQL-lock. Voeg `sslmode=require` toe, of gebruik de strengere certificaatcontrole met de vereiste CA-configuratie.

Stel de volledige string in als geheime Render-variabele `DATABASE_URL`. Gebruik een database-login die eigenaar is van schema `ct_backend` en de bijbehorende tabellen. Bij de eerste start moet de login dit schema kunnen maken, of moet het schema vooraf met deze login als eigenaar zijn aangemaakt. In de actieve omgeving is dit schema vooraf met de beperkte login als eigenaar aangemaakt en is de verbinding in Render ingesteld.

`python -m deployment.serve`:

1. Vereist productie-instellingen, een lange beheersleutel, PostgreSQL en TLS. Bij ontbrekende configuratie stopt de server. Er is geen terugval naar tijdelijke SQLite-opslag.
2. Stelt de zoekroute vast in op `ct_backend`, zonder terugval naar `public`, en begrenst verbindings- en querytijd.
3. Maakt het private schema indien nodig. Trekt daar toegang voor `PUBLIC`, `anon` en `authenticated` in. Voeg dit schema niet toe aan de blootgestelde Supabase Data API-schema's.
4. Voert de bestaande Alembic-migraties uit. Een gelijktijdige migratie stopt de tweede startup met een fout; die deploy moet opnieuw worden geprobeerd.
5. Schakelt RLS in op de backendtabellen. De owning database-login blijft voor de privé-API verantwoordelijk; dit introduceert geen account- of atleetbeleid.
6. Start één Uvicorn-worker op `0.0.0.0:$PORT` als een gebruiker zonder rootrechten.

Render genereert `ADMIN_API_KEY` via `generateValue`. Bij directe creatie moet dezelfde lange, willekeurige waarde via de beveiligde omgevingsvariabelen worden ingesteld. Providersecrets en tokens zijn geen buildargumenten en horen niet in het image of in GitHub. Strava blijft ongeconfigureerd.

## Een nieuwe omgeving in gebruik nemen

De huidige omgeving is al actief; maak daarvoor geen tweede service aan. Voor een nieuwe omgeving: importeer de Blueprint uit de repository, vul `DATABASE_URL` in via Render en controleer dat uitsluitend de Free-webservice wordt aangemaakt. De Blueprint maakt geen Render-database, disk, worker of cronjob aan. Er wordt dus geen database gebruikt die na 30 dagen vervalt.

Bij een gekoppelde GitHub-repository staat automatisch deployen op **After CI Checks Pass**. Een service die alleen via een openbare Git-URL is gekoppeld ondersteunt geen automatische deploys. Gebruik in dat geval een gecontroleerde handmatige deploy; een nieuwe commit is dan niet vanzelf live.

Verklaar de server pas actief wanneer de specifieke deploy `live` is, `/ready` een HTTP 200 geeft, `/concurrent-training/` en de assets laden, en een API-aanroep zonder sleutel wordt geweigerd. De eerste ingebruikname mag geen bestaande browsergegevens automatisch verplaatsen of verwijderen. Bestaande lokale gegevens bij de GitHub Pages-origin verhuizen ook niet mee naar een nieuwe Render-origin.

## Grenzen van gratis hosting

Render Free gaat na 15 minuten zonder inkomend verkeer in slaap en kan bij het ontwaken ongeveer een minuut nodig hebben. Daarom is dit een proefomgeving en geen garantie op directe synchronisatie. Lokale bestanden verdwijnen bij herstarts; de database staat daarom apart bij Supabase. Ook het gratis Supabase-project kan bij weinig activiteit worden gepauzeerd en heeft geen automatische databaseback-ups. Bewaar exports en plan een echte back-up voordat waardevolle cloudgegevens worden verzameld.

Voor een latere automatische koppeling is de beoogde taakverdeling:

- Supabase Edge Functions voor snelle ontvangst, verificatie en duurzame registratie van Wahoo-events.
- Supabase Cron voor het ophalen van Garmin-gegevens volgens het toegangsmodel waarvoor de app is toegelaten.
- Een duurzame importwachtrij met herhaalde verwerking, bronidentiteit, ontdubbeling en verwerking van intrekking/verwijdering.
- De Python-server voor de bestaande rekenmotor en zwaardere verwerking. Een slapende server mag een al ontvangen event niet laten verdwijnen.

Deze onderdelen zijn hier nog geen werkende integratie. Providerregistraties, toestemming, gebruiksrechten, accounts en daadwerkelijke importcode zijn volgende stappen. Een werkende deploy bewijst geen fysiologische of wetenschappelijke validatie.

## Bronnen, gecontroleerd op 5 november 2026

- https://render.com/docs/free
- https://render.com/docs/blueprint-spec
- https://render.com/docs/deploys
- https://render.com/docs/health-checks
- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://supabase.com/docs/guides/platform/free-project-pausing
- https://supabase.com/pricing
