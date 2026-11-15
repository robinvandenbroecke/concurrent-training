> Historisch verslag van de aangeleverde ZIP. De latere controle en correcties staan in `REVIEW_2026_11_15.md`.

# Auditrapport Concurrent Training — fase 1 en 2

Datum: 13 november 2026. Basis: `main`, commit `8bcc3e2f26cd12b2a32cbe429bf0e6f80c4b2e6e` (6 november 2026), zoals aangeleverd in de ZIP met `FABLE_5_2_AUDITOPDRACHT.md`.

Dit rapport dekt de eerste twee prioriteiten uit de opdracht: inventaris met kritieke fouten en dataveiligheid, en daarna de wetenschappelijke en numerieke correctheid. De koppeling van de rekenmotor aan de app, de krachtprogramma's, Garmin/Wahoo, VBT-meters en de Bluetooth-trainersturing zijn in deze ronde niet gebouwd. Wat daarvan al als half werk in de ZIP zat, staat apart en is niet nagekeken op volledigheid (zie BLD-01 en `INTEGRATION_STATUS.md`).

## Oordeel in het kort

De gebruiker van de webapp raakt vandaag geen enkel fysiologisch model. Alles wat hij ziet komt uit de browser en uit Supabase: zijn eigen sessies, een vast startschema, een setstelling per spiergroep en tekstuele signalen. Die keten is zorgvuldig gebouwd. De rijbeveiliging in de database klopt, sessies zijn idempotent, en ontbrekende metingen blijven ontbrekend.

De aangeleverde ZIP was daarentegen niet bouwbaar. Naast de 306 ongewijzigde bronbestanden bevatte ze 36 bestanden van een afgebroken eerdere uitvoering van deze opdracht. Die verwezen naar wijzigingen die nooit zijn doorgevoerd, waardoor de webapp niet compileerde, de Docker-build zou stranden en de backendtests faalden. Dat is rechtgezet zonder werk weg te gooien.

In de nieuwe, nog niet gekoppelde rekenkern (`app/science`) zaten vijf inhoudelijke fouten. De twee zwaarste: het referentievermogen van de fiets werd ook op loopvermogen toegepast, en de grens voor "trager dan verwacht" was bij kleine profielen statistisch te krap. Alle vijf zijn gecorrigeerd en met tests vastgelegd. Het oude driecompartimentenmodel (`app/domain`) blijft onderzoekscode. Het heeft structurele gebreken die niet met andere getallen op te lossen zijn; ik raad af het aan de app te koppelen.

De vastgepinde Python-pakketten hadden zestien bekende kwetsbaarheden. Die zijn weggewerkt.

## Wat de gebruiker werkelijk raakt

| Stap | Code | Rekent het iets uit dat de gebruiker ziet? |
|---|---|---|
| Login, registratie, herstel | `webapp/src/screens/Auth.tsx`, `AccountGate.tsx`, Supabase Auth | Nee |
| Opslag profiel, planning, open training | `api/cloud.ts`, `api/supabase.ts` → `ct_training_accounts` (revisiecontrole) | Nee |
| Opslag afgeronde sessies | `api/cloud.ts` → `ct_training_sessions` (alleen toevoegen) | Nee |
| Weekindeling | `api/local.ts: buildWeek, planForDay`, `domain/program.ts` | Ja: vaste verdeling kracht/duur over gekozen dagen, startschema A/B |
| Werkgewicht voorstellen | `domain/program.ts: strengthProgram` | Ja: laatst gelogde werkgewicht van dezelfde oefening, geen berekening |
| Volumefeedback | `domain/volume.ts` | Ja: directe sets tellen 1, indirecte 0,5; signaalgrenzen zijn instelbaar |
| Tijdsschatting sessie | `domain/volume.ts: estimatedMinutes` | Ja: vuistregel (4–6 s per rep plus rust) |
| Trend | `api/local.ts: measuredTrend` | Ja: zwaarste gelogde set per dag, geen schatting |
| Inzicht uit eigen gegevens (sinds 14 november) | `components/EngineCard.tsx` → `POST /v3/engine/evaluate` → `app/science` | Ja: beschrijvende totalen, 1RM-schatting met band, snelheidsprofiel, kracht-duursignalen en de modelverwachting met onzekerheid; "onvoldoende gegevens" is een normale uitkomst |

De onderzoeksbackend onder `app/` (FastAPI, 19.500 regels Python) draait op Render achter de beheersleutel en wordt door de webapp niet aangeroepen: de `backend`-modus in `api/adapter.ts` wordt nergens ingeschakeld. De enige uitzondering is sinds 14 november de engine-API onder `/v3`, die met het sessietoken van de gebruiker werkt. Het repmodel, dagmodel, de coach-, doel- en programmamotor, de Strava-koppeling en alle `sprint_*`- en `run_*`-scripts zijn dus onderzoekscode zonder invloed op een gebruiker. `app/science` is een zuivere rekenbibliotheek; de route ernaartoe bewaart niets.

## Bevindingen

Ernst: **kritiek** blokkeert oplevering of publicatie, **hoog** geeft een fout resultaat of een reëel veiligheidsrisico, **middel** geeft een fout resultaat in een randgeval, **laag** is beperkt van gevolg. De kolom "aard" scheidt programmeerfouten van wetenschappelijke onzekerheid.

### Oplevering en build

| ID | Ernst | Aard | Bevinding en bewijs | Correctie | Rest |
|---|---|---|---|---|---|
| BLD-01 | Kritiek | Programmeerfout | De ZIP bevatte 36 bestanden die niet in `SOURCE_SHA256SUMS.txt` staan, aangemaakt op 13 november tussen 19:00 en 19:22. Ze hingen af van nooit gemaakte wijzigingen in `types.ts`, `data/exercises.ts`, `config.py` en `models.py`. Gemeten: `tsc --noEmit` gaf fouten in `generator.ts`, `engine/client.ts` en `trainer/ftms.ts`, dus `npm run build` en de Docker-build falen. `pytest` stopte bij het verzamelen (`jwt` ontbreekt) en gaf daarna 22 errors en 1 failure. Migratie `007_provider_connections.py` zonder bijhorende modellen liet de `/ready`-test falen; `deployment/serve.py` voert bij elke start `alembic upgrade head` uit, dus die migratie zou zonder review tegen de productiedatabase zijn gelopen. | Zestien bestanden verplaatst naar `wip/phase3-6/` met behoud van hun pad. Die map valt buiten `tsc`, `pytest` (`pytest.ini`), Alembic en de Docker-context. De zuivere rekenkern, zijn tests en fixtures zijn gebleven. | Het werk in `wip/` is niet geaudit en niet af. |
| BLD-02 | Laag | Oplevering | Tegen de notitie in `SOURCE_SNAPSHOT.json` in bevatte de ZIP `node_modules` (2.973 bestanden), 130 `.pyc`-bestanden, `webapp/dist` en drie SQLite-bestanden. De databases zijn nagekeken en bevatten geen rijen. | Niet opnieuw meegeleverd. | — |
| BLD-03 | Laag | Documentatie | De kop van `README.md` meldde nog lokale opslag zonder accounts. | Herschreven. | De rest van de README beschrijft de onderzoeksbackend en is historisch. |

### Dataveiligheid en beveiliging

| ID | Ernst | Aard | Bevinding en bewijs | Correctie | Rest |
|---|---|---|---|---|---|
| SEC-01 | Hoog | Afhankelijkheden | `pip-audit` op `requirements.txt` meldde 16 advisories in vier pakketten: `fastapi 0.109.0`, `cryptography 42.0.5` (tokenversleuteling), `python-dotenv 1.0.0` en `pytest 8.0.0`. Na een eerste upgrade bleven er tien in het transitieve `starlette 0.50.0`. | Bijgewerkt naar `fastapi 0.162.7` (met `starlette 1.10.0`), `pydantic 2.14.3`, `pydantic-settings 2.16.3`, `cryptography 50.0.2`, `uvicorn 0.54.0`, `httpx 0.28.1`, `python-dotenv 1.2.4`, `pytest 9.2.0`, `pytest-asyncio 1.5.0`. `pip-audit` op de volledige omgeving: geen bekende kwetsbaarheden. Alle 824 tests en de PostgreSQL-migratiecontroles slagen op deze versies. | Momentopname van 13 november 2026. Een grote sprong in het webframework verdient één controle op de gehoste omgeving voor publicatie. `pytest` staat nog in het productie-image; splitsen in runtime- en testvereisten is netter. |
| SEC-02 | Laag | Programmeerfout | `hmac.compare_digest` gooit `TypeError` bij een headerwaarde met niet-ASCII-tekens; de API antwoordde dan met een serverfout in plaats van een weigering (`app/main.py`). | Vergelijking op bytes. Test: `tests/test_audit_2026_11.py`. | — |
| SEC-03 | — | Gecontroleerd | RLS op `ct_training_accounts` en `ct_training_sessions`: eigen rijen, `WITH CHECK` op update, geen rechten voor `anon`, sessies alleen toevoegen, revisie door trigger. `supabase/tests/ownership.sql` slaagt lokaal op PostgreSQL 16 met de `auth.uid()`-stub. In de frontend staat alleen de publiceerbare sleutel. Zoektocht naar geheimen in de hele boom: niets gevonden. | Geen wijziging nodig. | De controle tegen de echte Supabase-omgeving is door mij niet herhaald. |
| DATA-01 | Middel | Programmeerfout | Een datum als `2026-02-30` voldoet aan het patroon `^\d{4}-\d{2}-\d{2}$` in de databaseconstraint, in `importLocal` en in het enginecontract. De engine riep daarna `date.fromisoformat` aan en zou op één zo'n rij volledig stuklopen. | `importLocal` en het contract weigeren nu niet-bestaande datums. Tests in `webapp/tests/local.test.tsx` en `tests/test_science_engine.py`. | De databaseconstraint is niet aangescherpt, omdat een strengere check eerst tegen bestaande productierijen getoetst moet worden. Voorstel: `to_char(to_date(payload->>'date','YYYY-MM-DD'),'YYYY-MM-DD') = payload->>'date'` in een nieuwe migratie na die controle. |
| DATA-02 | Middel | Programmeerfout | Dezelfde sessie twee keer in één engineverzoek telde dubbel in tonnage, sets en load–velocity-punten. | Exacte herhalingen worden genegeerd en geteld (`duplicate_sessions_ignored`); twee verschillende records met dezelfde id worden geweigerd. | Dezelfde training via twee providers met verschillende id's is hiermee niet opgelost; dat hoort bij de providerkoppeling. |
| DATA-03 | Middel | Programmeerfout | `start.sh` wiste bij elke start `concurrent_training.db` en bevatte een vast pad van een andere machine. | Script wist niets meer en werkt vanuit zijn eigen map. | — |
| DATA-04 | Laag | Ontwerp, open | Afgeronde sessies kunnen niet gecorrigeerd of gewist worden: er is geen `UPDATE`- of `DELETE`-recht. Een tikfout blijft staan en telt mee; wissen kan alleen via het hele account. | Niet gewijzigd; dit vraagt een keuze (bijvoorbeeld een correctierecord dat het origineel vervangt zonder het te overschrijven) en een procedure voor inzage en wissing onder de AVG. | Open. |
| DATA-05 | Laag | Programmeerfout, open | `buildWeek` koppelt per dag alleen de eerste gevonden sessie (`sessions.find`). Een tweede training op dezelfde dag, juist bij concurrent training gewoon, verschijnt niet in het weekscherm. Historie en volumetelling tonen hem wel. | Niet gewijzigd: het raakt het type `WeekDay` en drie schermen en hoort bij de schermaanpassing van fase 3. | Open. |
| DATA-06 | Middel | Ontbrekende gegevens, open | Een sessie bewaart geen starttijd, en een snelheidsmeting geen meetgrootheid of apparaat. Zonder starttijd is het interval tussen kracht en duur onbekend; zonder meetgrootheid mogen snelheden niet in één profiel. | Opgelost op 14 november: `startTime` per sessie en `velocityMeta` per set, optioneel, zonder oude records te herschrijven. | Oude sessies blijven zonder starttijd; de engine telt ze en past de drie-uurregel daar niet toe. Tijden worden als UTC bewaard, sessies zonder tijd op de lokale middag gezet: een verschil van één tot twee uur dat alleen meespeelt wanneer beide soorten op dezelfde dag vallen. |
| UI-01 | Middel | Misleidende inhoud | `data/demoData.ts` bevatte verzonnen belastbaarheid (0,82 met een verzonnen verklaring), fictieve historie en trend en een "Demo Atleet" met capaciteiten. Het was dode code, maar zat deels in de bundel en `getProfile` kon het demoprofiel teruggeven. | Bestand verwijderd; alleen de weergavenamen zijn verhuisd naar `data/names.ts`. De ongebruikte `getProfile` is weg. | — |

### Rekenkern `app/science` (nog niet aan de app gekoppeld)

| ID | Ernst | Aard | Bevinding en bewijs | Correctie | Rest |
|---|---|---|---|---|---|
| SCI-01 | Hoog | Modelfout | Het referentievermogen uit het duurprofiel (standaard fietsen) werd ook gebruikt om loopvermogen te schalen. Loopvermogen is afhankelijk van apparaat en algoritme en heeft geen vaste verhouding tot fietsvermogen. | De referentie geldt alleen voor de sport van het profiel. Bij een andere sport valt de berekening terug op sessie-RPE of duur en meldt ze `power_not_used`. | Een tweede profiel per sport is nog niet mogelijk in het contract. |
| SCI-02 | Hoog | Statistische fout | De afwijking van de laatste sessie werd "trager" of "sneller" genoemd bij \|z\| ≥ 2, ongeacht het aantal kalibratiepunten. Een profiel mag al op vier punten gefit worden (twee vrijheidsgraden). Simulatie met alleen ruis, 2.000 herhalingen: de oude regel gaf 8,2 % valse signalen. | Student-t-grens voor de vrijheidsgraden van het profiel (4,30 bij vier punten). Zelfde simulatie: 1,9 %. De grens staat in de uitvoer (`noise_limit`). | Bewust conservatief: het gemiddelde over meerdere lasten wordt als één waarneming behandeld. Bij kleine profielen is het signaal daardoor weinig gevoelig; dat is de eerlijke stand bij zo weinig data. |
| SCI-03 | Middel | Modelfout | Critical power: (a) twee inspanningen van dezelfde duur gingen beide de regressie in, terwijl de zwakste per definitie niet maximaal was, en de controle "vermogen daalt met duur" wees zo'n set ten onrechte af; (b) de documentatie zei 2–15 minuten, de code 2–20; (c) geen waarschuwing als alle inspanningen korter dan tien minuten zijn, terwijl CP dan overschat wordt; (d) inspanningen van maanden uit elkaar werden zonder opmerking gecombineerd. | Beste inspanning per duur; bereik en onderbouwing in de documentatie gelijkgetrokken op 2–20 minuten; waarschuwingen `no_effort_of_10_min_or_longer_cp_may_be_overestimated`, `efforts_span_more_than_6_weeks`, `effort_dates_unknown`. | De zes weken zijn een praktische keuze, geen gepubliceerde grens. Met drie inspanningen blijft er één vrijheidsgraad; dat wordt gemeld, niet opgelost. |
| SCI-04 | Middel | Numerieke fout | De 1RM-schatting gebruikte Epley met een uitzondering bij één herhaling. Daardoor sprong de schatting 5 % tussen een single op RPE 10 en dezelfde single op RPE 9,5. | Brzycki (1993): exact gelijk aan de last bij één herhaling en continu daarboven. Test op continuïteit en monotonie. | Beide formules zijn op kleine groepen afgeleid en zijn niet gevalideerd voor sets die voor falen stoppen. De band bevat alleen de fout in de zelfgerapporteerde reserve. |
| SCI-05 | Laag | Modelfout | Het signaal "explosief werk binnen drie uur van duurtraining" keek niet naar volgorde en ook niet naar lichaamsregio; explosief werk voor alleen het bovenlichaam kreeg hetzelfde label met dezelfde bronverwijzing. | Uitvoer bevat `order` en `lower_body_strength_work`; explosief werk voor alleen het bovenlichaam valt buiten het bewijs en krijgt het algemene label. | De meta-analyse vond geen effect van volgorde op de adaptatie; `order` is context, geen oordeel. |
| SCI-06 | Laag | Onzekerheid, open | De 1RM-schatting neemt de hoogste schatting over de sets van de laatste sessie. Het maximum van meerdere ruisige schattingen is naar boven vertekend. | Niet gewijzigd; gedocumenteerd in `MODEL_REGISTER.md`. | Open. |
| SCI-07 | Laag | Onzekerheid, open | De duurbelasting ∫(P/P_ref)² dt in minuten is een eigen maat. Ze is geen TSS en de exponent 2 is niet empirisch onderbouwd. Totalen met verschillende methodes worden terecht niet opgeteld. | Niet gewijzigd; als heuristiek gelabeld. | Open; kandidaat voor vervanging of weglating bij de koppeling. |

### Oud driecompartimentenmodel `app/domain` (onderzoekscode)

| ID | Ernst | Aard | Bevinding en bewijs | Correctie | Rest |
|---|---|---|---|---|---|
| LEG-01 | Middel | Programmeerfout | Een lift zonder beginstatus kreeg in `RepState` de ondergrens van 2 % beschikbaarheid in plaats van "geen vermoeidheid". Gemeten: voorspelde snelheid 0,012 m/s bij een referentie van 0,60 m/s. De services vullen de status altijd in, dus het was een latente fout. | Standaard is nu onvermoeid. Test toegevoegd. | — |
| LEG-02 | Middel | Modelfout, open | De dichtheidsfactor is onstetig: de eerste set van een sessie (geen rust geregistreerd) kost meer systemische beschikbaarheid dan dezelfde set na 24 uur rust (0,926 tegen 0,973), en één seconde rust kost meer dan geen rust. | Niet afgestemd. Als uitvoerbaar feit vastgelegd in `test_known_defect_first_set_…`. | Open. |
| LEG-03 | Hoog | Modelfout, open | Capaciteit wordt elke trainingsdag verlaagd met `h_l · D_l` en krijgt dat nooit terug wanneer de vermoeidheid verdwijnt. Vermoeidheid telt zo twee keer: tijdelijk in de belastbaarheid en blijvend in de capaciteit. Een fitness-fatiguemodel doet dat algebraïsch, niet cumulatief. | Niet afgestemd; vastgelegd in `test_known_defect_capacity_integrates_fatigue_…`. | Open. |
| LEG-04 | Hoog | Modelfout, open | De krachtimpuls schaalt met de absolute last. Dezelfde relatieve sessie (3×5 op 80 %) geeft bij 200 kg capaciteit precies het dubbele van die bij 100 kg, en `D_l` stijgt met 1,19 tegen 0,60. Belastbaarheid is `1 − D_l − 0,5·D_sys`, dus een gewone sessie zet de sterkere atleet de volgende dag op nul. | Niet afgestemd; vastgelegd in `test_known_defect_impulse_scales_…`. | Open. |
| LEG-05 | Laag | Programmeerfout, open | De overbelastingsindicator vergelijkt `u_sys > 30`, terwijl `u_sys` voor 3×5 op 100 kg rond 1.300 ligt. De voorwaarde is op elke krachtdag waar en heeft geen betekenis. | Niet gewijzigd: het effect is verwaarloosbaar klein en een andere drempel zou evenmin onderbouwd zijn. | Open. |
| LEG-06 | Laag | Modelfout, open | Het snelheidsverlies per set in het repmodel is 0 wanneer de eerste of laatste rep niet gemeten is, en gebruikt de eerste in plaats van de snelste rep (0,10 tegen 0,25 in een voorbeeld). Een ontbrekende meting wordt zo een meetwaarde. | Niet gewijzigd in de oude motor; `app/science/load_velocity.py` doet het wel juist. | Open. |

De bevindingen uit de audit van september 2026 (`docs/audit_2026_09.md`) blijven staan. Van de daar als gecorrigeerd gemelde punten heb ik M01 (rustherstel onafhankelijk van opdeling) en M05/M06 (dagverval) in de code teruggevonden; de overige heb ik niet opnieuw getoetst.

## Wetenschappelijk oordeel per deelmodel

Het volledige overzicht met bronnen staat in `MODEL_REGISTER.md`. Hier de hoofdlijn.

**Oud model.** Drie multiplicatieve beschikbaarheden die samen één gemeten snelheid verklaren zijn op één tijdstip niet te onderscheiden; dat stond al in de vorige audit. De literatuur van de laatste jaren maakt het beeld strenger: ook het veel eenvoudiger fitness-fatiguemodel is slecht geconditioneerd, en de vermoeidheidsterm verbeterde de voorspelling niet in een Bayesiaanse analyse met kruisvalidatie op meerdere datasets (Marchal e.a. 2025). Een model met zeven toestanden per dag en tientallen vaste coëfficiënten kan op een trainingslog niet gekalibreerd worden. Samen met LEG-03 en LEG-04 is dat reden om het niet te koppelen, ook niet "voorlopig".

**Critical power en W′.** De tweeparameterfit op door de gebruiker aangemerkte maximale inspanningen is een verdedigbare, eenvoudige keuze. De kwaliteit hangt aan het protocol: aantal, duur en spreiding van de inspanningen bepalen de uitkomst mee. De W′-balans in differentiaalvorm is correct geïmplementeerd (stapgrootte-onafhankelijk, uitval is geen nul watt), maar gebruikt een gemiddelde herstelkinetiek. Die onderschat herstel in de eerste twee minuten, overschat het na vijf, en vertraagt bij herhaalde uitputting. De balans is dus bruikbaar als planningshulp in een workoutspeler, niet als meting.

**Load–velocity.** Het profiel wordt per oefening, apparaat en meetgrootheid gefit en alleen binnen het gemeten lastbereik gebruikt. Dat volgt het bewijs: extrapolatie naar een 1RM overschat structureel, en complexere modellen doen het niet beter. Meetgrootheden en apparaten niet mengen is terecht. Snelheidsverlies is een prestatiemaat binnen de set; als voorspeller van resterende herhalingen is het onbetrouwbaar.

**Concurrente interactie.** Het enige wat de engine zegt is een contextsignaal bij explosief onderlichaamwerk binnen drie uur van duurtraining. Meer geeft het bewijs niet: gemiddeld geen aantasting van maximale kracht of spiermassa, wel van explosieve kracht, vooral in dezelfde sessie. Een individuele interferentieschatting zou verzonnen zijn en ontbreekt terecht.

**Volumefeedback in de webapp.** Indirecte sets als halve set tellen sluit aan bij de meta-regressies van Pelland e.a., waar die telwijze de beste voorspeller bleek. De instelbare signaalgrenzen worden in de app al als startpunt en niet als persoonlijke herstelgrens gepresenteerd. Dat is juist.

## Validatiestatus

Niets in deze repository is empirisch gevalideerd op echte atleten. De tests bewijzen software-eigenschappen: juiste formules, eenheden, behoud van ontbrekende metingen, determinisme, geen lekkage van toekomstige data in de eigen voorspeltoets. De synthetische vergelijking in `research/` laat de eenvoudige "laatste waarneming" winnen van M0, M1 en M2; ze is opnieuw gereproduceerd en ongewijzigd.

## Vervolg 14 november: nieuw concurrent model

Op vraag van de opdrachtgever is het onderliggende model herontworpen. Het oude driecompartimentenmodel is niet bijgestuurd, omdat LEG-02 tot LEG-04 in zijn structuur zitten. In de plaats is er een kleiner model gekomen in `app/science/concurrent.py`: één vergelijking per domein, relatieve dosis, exacte tijdsafhandeling, en de wisselwerking tussen kracht en duur als vier afzonderlijke, toetsbare termen. Het wordt per atleet gekalibreerd en meldt per coëfficiënt hoeveel de eigen data ervan hebben bepaald. Het kan vooruit voorspellen en weekindelingen rangschikken. De volledige beschrijving, de onderbouwing en de simulatieresultaten staan in `MODEL_REGISTER.md`, deel D.

Twee dingen horen hier uitdrukkelijk bij. "Geoptimaliseerd" betekent dat het model wiskundig klopt, schatbaar is en zijn onzekerheid toont; de getallen zelf kunnen pas beter worden met echte trainingsdata, en die waren er niet. En op gesimuleerde atleten heeft een bescheiden wisselwerking ruim 150 gemeten krachtsessies nodig om zichtbaar te worden; tot dan rekent het model met aannames op groepsniveau en zegt het dat ook.

Tijdens dit werk kwam één extra fout boven (PERF-01): de bestaande voorspeltoets was kwadratisch in de lengte van de historie. Die is hersteld.

## Vervolg 14 november: krachtprogramma's (prioriteit 4 van de opdracht)

De programmagenerator uit de aangeleverde aanzet is herwerkt en opgenomen. Drie dingen zijn inhoudelijk veranderd tegenover die aanzet. Een lichtere vierde week was verplicht; het gecontroleerde onderzoek dat er is toont geen voordeel, dus ze is nu een keuze die standaard uit staat. Het intakegewicht (een werkgewicht voor ongeveer vijf herhalingen) werd ook bij sets van acht of meer ingevuld; nu alleen bij zes of minder. En bij spiergroei bleef de voorkant van het bovenbeen onder de weekdrempel terwijl de achterkant ruim erboven zat; het sjabloon is daarop bijgestuurd. De regels en hun bronnen staan in `docs/strength_programs.md`. De getallen blijven startpunten: er is geen data van sporters waarop ze getoetst zijn.

## Wat ik niet heb gedaan of niet kon controleren

De actuele uitrol op Render en GitHub Pages, de Supabase-instellingen en de e-mailconfiguratie heb ik niet kunnen inzien; daar is geen toegang toe vanuit deze omgeving. De Strava-integratie en de eval-, coach-, doel- en programmamotor in de backend zijn niet regel voor regel nagelopen. Toegankelijkheid en mobiele layout zijn niet op een toestel getest. De code in `wip/phase3-6/` is niet beoordeeld. Zie `TEST_RESULTS.md` voor wat wel is uitgevoerd.

## Voorgestelde volgorde voor het vervolg

Eerst het opslagformaat uitbreiden met starttijd en snelheidsmetadata (DATA-06), dan de engine via één route aan het scherm "Vandaag" koppelen met de uitvoer zoals ze nu is. Daarna DATA-04 en DATA-05, en pas dan de programmagenerator en de koppelingen. Het oude model kan in `research/` blijven voor het voorspelonderzoek, maar hoort niet in het productie-image.
