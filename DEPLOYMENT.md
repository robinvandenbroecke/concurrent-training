# Webapp bouwen en publiceren

## Huidige versie

`webapp/src/` is de enige frontendbron. De productiebuild gebruikt React, TypeScript en Vite met een vastgelegde `package-lock.json`. De losse HTML-implementatie uit Claudes ZIP is niet opgenomen: anders konden ontwikkeling en publicatie verschillende apps opleveren.

Dit is een lokaal prototype met onboarding, een aanpasbaar A/B-krachtprogramma met 42 catalogusoefeningen en volumefeedback, registratie van kracht- en duursessies, rusttimer, historie, gemeten werkgewichten en JSON-export/import. Gegevens staan in deze browser op dit toestel. Er is geen account, serveropslag, synchronisatie met Android/Strava of gekoppeld onderzoeksmodel. Browsergegevens wissen verwijdert ook de lokale gegevens; maak exports via Historie. Een import voegt sessies toe en wijzigt het profiel niet.

De weekindeling gebruikt een transparant startschema binnen de opgegeven dagen en sessieduur. Trainingen kunnen vooraf via Vandaag/Week en tijdens de training worden aangepast. Zie [de literatuur, programmering en telregels](docs/strength_program_2026_10.md). Werkgewichten komen uit de invoer van de gebruiker. Belastbaarheid blijft onbekend zolang het onderzoeksmodel niet is gekoppeld. De app toont geen fictieve trainingshistorie, berekende 1RM of wetenschappelijk gevalideerde personalisatie.

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

De repository is openbaar gemaakt op verzoek van de eigenaar. Op 21 oktober 2026 is Settings → Pages → Source ingesteld op **GitHub Actions**. Na een relevante push naar `main` publiceert de workflow automatisch de geslaagde frontendbuild. De eerdere `PAGES_ENABLED`-variabele is niet meer nodig.

Webapp: [Concurrent Training](https://robinvandenbroecke.github.io/concurrent-training/).

Bij handmatige uitvoering: Actions → **Webapp** → Run workflow → branch `main` → vink `deploy` aan. Zonder dit vinkje voert een handmatige run alleen tests en de build uit. Controleer steeds de geslaagde `deploy`-job voordat je een nieuwe publicatie als live beschouwt.

De broncode en de Pages-site zijn publiek. Persoonlijke trainingsgegevens worden in deze versie alleen in de browser opgeslagen.

De Vite-base is `/concurrent-training/`. Navigatie zit in de appstate en gebruikt geen subroutes waarvoor serverrewrites nodig zijn. Manifest en pictogram verwijzen naar bestaande bestanden. Er is geen service worker en geen gegarandeerde offlinebeschikbaarheid.

## Verificatie van de frontend

- 34 tests: opslag en fouten, export/import, weekbeperkingen, ontbrekende en gedeeltelijke snelheidsmetingen, plus React/JSDOM-ketens voor onboarding en het vooraf/tijdens aanpassen, toevoegen en herschikken met behoud van bevestigde metingen na herladen.
- `npm run build`: TypeScript en Vite-productiebuild geslaagd.
- `npm audit`: nul gemelde kwetsbaarheden op 20 oktober 2026, inclusief ontwikkelafhankelijkheden. Dit is een momentopname, geen veiligheidsgarantie.
- Bevestigde krachtsets blijven behouden na tabwissel en herladen. Nog niet bevestigde invoervelden en een niet opgeslagen duurformulier worden niet als draft bewaard.
- Een ontbrekende rep-snelheid blijft `null`; één gemiddelde wordt nooit gekopieerd naar alle reps. Gewicht, werkelijk aantal reps, RPE en opmerking blijven behouden.
- Opslagfouten geven geen vals succesbericht. Een herhaalde opslagpoging gebruikt dezelfde sessie-ID.

De bestaande Python-CI blijft afzonderlijk de backend, PostgreSQL-migraties en de bevroren onderzoeksfixture controleren. Een JSDOM-test bewijst geen visuele kwaliteit of koppeling met een echte server.

Op 21 oktober 2026 is de live Pages-app gecontroleerd in Chrome: onboarding met twee trainingsdagen en VBT, setregistratie (42,5 kg × 3, RPE 8), tabwissel, herladen, afronden, historie en JSON-export. De export behield de drie snelheidsposities `[0.5, null, 0.42]` en de opmerking. Bij de visuele controle bleken SVG-pictogrammen zonder afmetingen knoppen sterk uit te rekken; de pictogrammen hebben nu expliciete standaardafmetingen. De uitgevoerde controle is geen volledige test op Android/iOS en valideert geen fysiologische voorspellingen.

## Nog te bouwen

- Gebruikersauthenticatie, per-atleet autorisatie en een beveiligde backendkoppeling; nooit een beheer-API-sleutel in de frontend opnemen.
- Echte planning, VBT- en vermogensdata koppelen aan de backend, met contracttests en expliciete onzekerheid.
- Synchronisatie tussen website en Android, inclusief conflicten en herstel bij verbindingsverlies.
- Apart literatuuronderzoek en empirische validatie van de deelmodellen en het concurrent model, volgens de afgesproken volgende fase.
