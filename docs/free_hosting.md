# Gratis hosting: status en ingebruikname

## Status op 5 november 2026

- De bestaande webapp staat op https://robinvandenbroecke.github.io/concurrent-training/.
- Supabase-project `concurrent-training` is aangemaakt op het Free-plan in Frankfurt. Projectreferentie: `dvwbkbohdgfuzjenrete`. De lege databaseverbinding is getest.
- In Render is bij de laatste controle alleen `My Workspace` zichtbaar. De gevraagde aparte werkruimte `Concurrent Training` en de server zijn nog niet aangemaakt. De dashboardaanmelding blokkeert deze stap; de Render-koppeling kan geen werkruimtes aanmaken.
- Deze wijziging bevat de hostingcode en configuratie. Dit document is geen bewijs van een actieve Render-deploy.
- Garmin- en Wahoo-synchronisatie zijn nog niet geïmplementeerd of actief. Er zijn geen providercredentials ingesteld of persoonlijke trainingsgegevens geïmporteerd.

## Wat de configuratie doet

`render.yaml` beschrijft één Free-webservice in Frankfurt. Het Docker-image bouwt en test de bestaande React-app en biedt die aan op `/concurrent-training/`. De root verwijst naar dat pad. De bestaande Python-API behoudt haar URLs en beheer-API-sleutel. `/ready` controleert verbinding én migratieversie van de database. `/health` is de bestaande, eenvoudigere livenesscontrole.

De frontend blijft in deze versie een lokaal prototype. Hosting van de API verbindt de browserhistorie niet automatisch met de database. Accounts, autorisatie per atleet en synchronisatie tussen toestellen moeten afzonderlijk worden aangesloten. Zet de beheer-API-sleutel nooit in de webapp, een `VITE_`-variabele, een URL of een GitHub-bestand. Deze beheer-API is bedoeld voor een privéprototype, niet als gedeelde gebruikerslogin.

## Database en secrets

Gebruik uitsluitend de aparte Concurrent Training-database. Kopieer de verbindingsstring uit het Supabase-dashboard: **Connect → Session pooler**, voor een verbinding vanaf Render. Neem host en gebruikersnaam over uit die string; leid de poolerhost niet af uit de regio. Gebruik **session mode**, geen transaction mode: opstartmigraties gebruiken een sessiegebonden PostgreSQL-lock. Voeg `sslmode=require` toe, of gebruik de strengere certificaatcontrole met de vereiste CA-configuratie.

Stel de volledige string in als geheime Render-variabele `DATABASE_URL`. Gebruik een database-login die eigenaar is van schema `ct_backend` en de bijbehorende tabellen. Bij de eerste start moet de login dit schema kunnen maken, of moet het schema vooraf met deze login als eigenaar zijn aangemaakt. De gratis database is al aangemaakt, maar de verbindingsgegevens zijn nog niet aan Render doorgegeven.

`python -m deployment.serve`:

1. Vereist productie-instellingen, een lange beheersleutel, PostgreSQL en TLS. Bij ontbrekende configuratie stopt de server. Er is geen terugval naar tijdelijke SQLite-opslag.
2. Stelt de zoekroute vast in op `ct_backend`, zonder terugval naar `public`, en begrenst verbindings- en querytijd.
3. Maakt het private schema indien nodig. Trekt daar toegang voor `PUBLIC`, `anon` en `authenticated` in. Voeg dit schema niet toe aan de blootgestelde Supabase Data API-schema's.
4. Voert de bestaande Alembic-migraties uit. Een gelijktijdige migratie stopt de tweede startup met een fout; die deploy moet opnieuw worden geprobeerd.
5. Schakelt RLS in op de backendtabellen. De owning database-login blijft voor de privé-API verantwoordelijk; dit introduceert geen account- of atleetbeleid.
6. Start één Uvicorn-worker op `0.0.0.0:$PORT` als een gebruiker zonder rootrechten.

Render genereert `ADMIN_API_KEY` via `generateValue`. Bij directe creatie moet dezelfde lange, willekeurige waarde via de beveiligde omgevingsvariabelen worden ingesteld. Providersecrets en tokens zijn geen buildargumenten en horen niet in het image of in GitHub. Strava blijft ongeconfigureerd.

## Render activeren

Maak de door de eigenaar gevraagde werkruimte **Concurrent Training** aan met het **Hobby-plan**. Selecteer daarna expliciet deze werkruimte. Importeer de Blueprint uit de repository, vul `DATABASE_URL` in via Render en controleer dat uitsluitend de Free-webservice wordt aangemaakt. De Blueprint maakt geen Render-database, disk, worker of cronjob aan. Er wordt dus geen database gebruikt die na 30 dagen vervalt.

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
