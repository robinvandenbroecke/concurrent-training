# Webapp bouwen en publiceren

## Huidige versie

`webapp/src/` is de enige frontendbron. De productiebuild gebruikt React, TypeScript en Vite met een vastgelegde `package-lock.json`. De losse HTML-implementatie uit Claudes ZIP is niet opgenomen: anders konden ontwikkeling en publicatie verschillende apps opleveren.

Dit is een lokaal prototype met onboarding, een voorlopige weekindeling, registratie van kracht- en duursessies, rusttimer, historie, gemeten werkgewichten en JSON-export/import. Gegevens staan in deze browser op dit toestel. Er is geen account, serveropslag, synchronisatie met Android/Strava of gekoppeld onderzoeksmodel. Browsergegevens wissen verwijdert ook de lokale gegevens; maak exports via Historie. Een import voegt sessies toe en wijzigt het profiel niet.

De weekindeling is een eenvoudige template binnen de opgegeven dagen en sessieduur. Werkgewichten komen uit de invoer van de gebruiker. Belastbaarheid blijft onbekend zolang het onderzoeksmodel niet is gekoppeld. De app toont geen fictieve trainingshistorie, berekende 1RM of wetenschappelijk gevalideerde personalisatie.

## Lokaal uitvoeren

Gebruik Node.js 24 of nieuwer:

```bash
cd webapp
npm ci
npm test
npm run dev
```

Open `http://localhost:5173/concurrent-training/`. Voor de productiebuild:

```bash
npm run build
npm run preview
```

Open `http://localhost:4173/concurrent-training/`. Alleen `webapp/dist/` wordt gehost; publiceer nooit de volledige repository of backendconfiguratie.

## GitHub Actions en Pages

`.github/workflows/deploy-webapp.yml` installeert de lockfile, voert tests uit, compileert TypeScript en bouwt de React-app. De workflow draait op relevante pushes naar `main` en `agent/**`, pull requests en handmatige uitvoering. Het downloadbare artifact `webapp-dist` bevat de deploybare frontend.

**Hostingblokkade vastgesteld op 20 oktober 2026:** Settings → Pages van deze privérepository toont “Upgrade or make this repository public to enable Pages”. De repository blijft privé. Pages is dus nog niet actief en de onderstaande URL is nog geen werkende publicatie.

Zodra het GitHub-abonnement Pages voor deze privérepository ondersteunt:

1. Kies Settings → Pages → Build and deployment → Source: **GitHub Actions**.
2. Ga naar Actions → **Webapp** → Run workflow, selecteer `main` en vink `deploy` aan.
3. Voor automatisch publiceren bij volgende pushes: voeg onder Settings → Secrets and variables → Actions → Variables de repositoryvariabele `PAGES_ENABLED` toe met waarde `true`.
4. Controleer de geslaagde deployment en de door GitHub geretourneerde site-URL. De verwachte project-URL is `https://robinvandenbroecke.github.io/concurrent-training/`.

Zonder `PAGES_ENABLED=true` of een handmatige `deploy`-uitvoering blijft CI bouwen en testen, zonder een onmogelijke Pages-deployment te starten. Openbaar maken van de broncode is een afzonderlijke keuze en gebeurt niet automatisch. De standaard Pages-site zelf is publiek; de persoonlijke trainingsgegevens staan alleen in de browser.

De Vite-base is `/concurrent-training/`. Navigatie zit in de appstate en gebruikt geen subroutes waarvoor serverrewrites nodig zijn. Manifest en pictogram verwijzen naar bestaande bestanden. Er is geen service worker en geen gegarandeerde offlinebeschikbaarheid.

## Verificatie van de frontend

- 16 tests: opslag en fouten, export/import, weekbeperkingen, ontbrekende en gedeeltelijke snelheidsmetingen, plus een React/JSDOM-keten van onboarding naar training, navigatie, herladen, opslaan en historie.
- `npm run build`: TypeScript en Vite-productiebuild geslaagd.
- `npm audit`: nul gemelde kwetsbaarheden op 20 oktober 2026, inclusief ontwikkelafhankelijkheden. Dit is een momentopname, geen veiligheidsgarantie.
- Bevestigde krachtsets blijven behouden na tabwissel en herladen. Nog niet bevestigde invoervelden en een niet opgeslagen duurformulier worden niet als draft bewaard.
- Een ontbrekende rep-snelheid blijft `null`; één gemiddelde wordt nooit gekopieerd naar alle reps. Gewicht, werkelijk aantal reps, RPE en opmerking blijven behouden.
- Opslagfouten geven geen vals succesbericht. Een herhaalde opslagpoging gebruikt dezelfde sessie-ID.

De bestaande Python-CI blijft afzonderlijk de backend, PostgreSQL-migraties en de bevroren onderzoeksfixture controleren. Een JSDOM-test bewijst geen visuele kwaliteit of koppeling met een echte server. De gehoste browsercontrole blijft open tot hosting beschikbaar is.

## Nog te bouwen

- Gebruikersauthenticatie, per-atleet autorisatie en een beveiligde backendkoppeling; nooit een beheer-API-sleutel in de frontend opnemen.
- Echte planning, VBT- en vermogensdata koppelen aan de backend, met contracttests en expliciete onzekerheid.
- Synchronisatie tussen website en Android, inclusief conflicten en herstel bij verbindingsverlies.
- Apart literatuuronderzoek en empirische validatie van de deelmodellen en het concurrent model, volgens de afgesproken volgende fase.
