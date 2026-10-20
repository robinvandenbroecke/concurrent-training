# Integratie van Claudes webapp

Bron: `agent/scientific-audit-2026-09`, commit `64655e28b49dfd86c93447c2859c531959ac4143`. Ontvangen en nagekeken op 20 oktober 2026.

## Omvang

Claudes ZIP nam alle 249 bestaande bronbestanden ongewijzigd over. De frontend wordt geïntegreerd bovenop die auditversie, met behoud van de backend, bestaande tests, migraties en onderzoeksartefacten. De Python-modellen zijn in deze integratie niet opnieuw wetenschappelijk beoordeeld of aangepast. De README vermeldt de nieuwe productstatus; `.gitignore` sluit frontend-buildproducten en afhankelijkheden uit.

## Correcties bij integratie

- Eén React/Vite-implementatie voor ontwikkeling én publicatie; de concurrerende losse `webapp/app.html` is weggelaten.
- Vastgelegde npm-lockfile, Node 24 en bijgewerkte buildafhankelijkheden. CI test en bouwt exact dezelfde broncode.
- Geen verzonnen belastbaarheid, historische sessies of capaciteitstrends in het lokale prototype. De trend toont werkelijk gelogde werkgewichten.
- Weekplanning respecteert beschikbare dagen en duur; overslaan wordt opgeslagen en voegt geen inhaalvolume toe. De indeling blijft expliciet een voorlopige template.
- Werkgewichten starten leeg en worden als recente werkgewichten beschreven, niet als gemeten 1RM.
- VBT-invoer per rep, met behoud van ontbrekende metingen en alle werkelijk uitgevoerde reps. RPE en opmerkingen worden opgeslagen.
- Bevestigde sets blijven bewaard bij navigatie en herladen. De verstreken tijd telt omhoog en wordt berekend op basis van tijdstempels.
- Werkelijk opgeslagen sessies verschijnen in de historie; JSON-export/import voor sessies toegevoegd. Dubbele opslag met dezelfde ID is idempotent; opslagfouten tonen geen succesbericht.
- Kleine schermen kunnen scrollen; toetsenbordfocus is zichtbaar; het manifest verwijst alleen naar bestaande assets.
- GitHub Pages-publicatie blijft uitgeschakeld tot de repository daar toegang toe heeft. Een privébronrepository wordt niet automatisch openbaar gemaakt.

## Controle

16 frontendtests en de productiebuild slagen lokaal. De React-integratietest doorloopt onboarding → plan → set → tabwissel → herladen → afronden → echte lokale historie. `npm audit` meldt op 20 oktober 2026 nul bekende kwetsbaarheden. Backend- en migratiecontrole lopen via de bestaande GitHub CI. Zie `DEPLOYMENT.md` voor precieze grenzen en hostinginstructies.

## Resterend werk

Geen actieve backendkoppeling, geen Android-synchronisatie en geen nieuw wetenschappelijk gevalideerd model. Nog niet bevestigde invoervelden worden niet hersteld na herladen. Visuele controle van de gehoste app volgt zodra hosting beschikbaar is. De afgesproken systematische literatuurtoets is een afzonderlijke volgende fase.
