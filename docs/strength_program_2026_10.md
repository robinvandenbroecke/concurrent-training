# Krachtprogramma, oefeningencatalogus en volumefeedback

Literatuur gecontroleerd op 21 oktober 2026. Dit document gaat over de gepubliceerde frontend. De fysiologische backend is hiermee niet opnieuw gevalideerd of aangesloten.

## Keuzes en bewijskracht

| Bron | Wat de bron ondersteunt | Vertaling naar deze app |
|---|---|---|
| Currier et al., ACSM Position Stand (2026), [PMID 41843416](https://pubmed.ncbi.nlm.nih.gov/41843416/), DOI 10.1249/MSS.0000000000003897 | Krachttraining werkt; zwaardere belasting en herhaalde blootstelling zijn relevant voor kracht, korte snelle sets voor power. De populatie bestaat uit gezonde volwassenen, niet uitsluitend wedstrijdatleten. | Specifieke powerlifts, kleine explosieve blokken, voldoende rust. Geen claim dat een algemeen schema optimaal is voor een individuele atleet. |
| Comfort et al., NSCA (2023), [PMID 36952649](https://pubmed.ncbi.nlm.nih.gov/36952649/) | Gewichthefvarianten kunnen sportprestaties ondersteunen. Techniek, trainingsdoel en fase bepalen de variant en dosering; pulls zonder opvang zijn minder complex dan opvangvarianten. | Zonder expliciete ervaring: clean pull. Met bevestigde power-clean-techniek: power clean. Andere varianten zijn handmatig beschikbaar. Techniekverlies is een reden om het blok te stoppen. |
| Pelland et al. (2026; online 2025), [PMID 41343037](https://pubmed.ncbi.nlm.nih.gov/41343037/), DOI 10.1007/s40279-025-02344-w | Volume en frequentie hebben verschillende dosis-responsrelaties voor kracht en hypertrofie, met afnemende meeropbrengst. Onderscheid tussen directe en indirecte sets is relevant. | Directe SBD-sets blijven apart van een grove spiergroeptelling (direct + 0,5 indirect). Die weging is geen persoonlijk gevalideerde voorspelling. |
| Androulakis-Korakakis et al. (2021), [PMID 34527944](https://pubmed.ncbi.nlm.nih.gov/34527944/), DOI 10.3389/fspor.2021.713655 | Kleine studies bij powerlifters laten zien dat circa 3–6 werksets van 1–5 reps per lift per week bij hoge belasting/inspanning vooruitgang kunnen geven. Een minimale effectieve dosis is geen optimale dosis; de interventies waren kort. | Tijdsefficiënte startvolumes zijn verdedigbaar. Deze studie bewijst de gekozen doelbanden of lagere start-RPE niet. |
| Held et al. (2026), [Sports Medicine](https://doi.org/10.1007/s40279-026-02401-y) | Concurrent training kan beide doelen verbeteren. Gegevens over zeer goed getrainde/elite atleten blijven beperkt. | Duurtraining blijft zichtbaar als herstelcontext. Geen berekende individuele interferentiefactor, hersteltijd of blessurescore. |

Dit is een gerichte literatuurtoets voor deze functie, geen volledige systematische review. PubMed-abstracten en de NSCA-volledige tekst zijn geraadpleegd; de volledige ACSM-tekst was via PMC niet toegankelijk. De afzonderlijke deelmodellen van het onderzoeksproject vragen nog de afgesproken volledige audit.

## Startprogramma en progressie

Bij krachtprioriteit en twee beschikbare dagen:

- A: kort explosief blok, back squat, bench, trekaccessoire.
- B: kort explosief blok, deadlift, bench, lichte squat en trekaccessoire als de tijd het toelaat.
- Minder dan 45 minuten: de twee hoofdbewegingen krijgen voorrang. De volumefeedback meldt de beperkte ruimte voor het atletische doel. Met slechts één lange krachtsessie worden de drie powerlifts opgenomen.
- Hoofdlifts doorgaans 2–3 sets van 3–5 reps, doel-RPE rond 7; lichte squat rond 6. Explosief doorgaans 3 × 2, doel-RPE rond 6. Rust meestal 180 sec bij kracht en 120 sec bij power. Dit zijn coachingskeuzes, geen integraal empirisch getest protocol.

Power staat standaard eerst om kwaliteit te ondersteunen. Bij prioriteit voor wedstrijdspecifieke kracht kan de gebruiker de hoofdbeweging naar voren zetten. Gebruik uitsluitend een bekend recent werkgewicht van dezelfde oefening of kies het zelf. Er wordt geen actuele 1RM verzonnen en geen percentage van een andere oefening toegepast.

Progressie is een handmatige beslissing: overweeg na twee blootstellingen met alle doelreps, beheerste techniek en maximaal de gekozen doel-RPE de kleinste beschikbare gewichtsprong. Houd bij slechtere uitvoering de belasting gelijk of verlaag deze; voeg niet automatisch sets toe. Dit is een praktische regel, geen bewezen persoonlijke optimalisator.

## Wat de volumefeedback betekent

De weekprojectie bevat geregistreerd werk plus deze sessie en nog komende geplande dagen. Uitgevoerde sets vervangen hun geplande set; ze worden niet dubbel opgeteld. Een extra sessie op een dag met al geregistreerd werk telt als extra. Gemiste dagen voegen geen inhaalvolume toe.

Startdoelen voor directe powerliftwerksets per week: squat 3–8, bench 4–10, deadlift 2–6. De gebruiker kan deze wijzigen. De spiergroepsignaalgrens start op 16 en is eveneens instelbaar. Deze getallen zijn software-/coachingsreferenties, **geen gepubliceerde grenzen voor minimale of maximaal herstelbare dosis**. Lage RPE blijft meetellen als specifieke liftpraktijk. Voor de aanvullende spiergroepschatting is RPE ≥6 een expliciete appconventie; ontbrekende RPE telt voorlopig mee en wordt gemeld. Opwarmsets tellen niet mee. Gewicht, bewegingsuitslag en andere sport worden niet gereduceerd tot één equivalente dosis.

Explosieve herhalingen worden afzonderlijk geteld. Meer dan 24 geplande explosieve reps in één sessie geeft een signaal, geen verbod of universele veilige bovengrens. Tijd wordt grof geraamd uit sets, reps, rust, opwarming en wissels. De app voorspelt geen overtraining, letsel of individuele herstelbaarheid.

## Integriteit en controle

Elke oefeningsinstantie heeft een vaste ID. Toevoegen en herschikken kan vóór of tijdens een training. Verwijderen/vervangen van een oefening met bevestigde sets is geblokkeerd; aangepaste groepsvelden veranderen uitsluitend toekomstige sets. Oude index-gebaseerde drafts worden gemigreerd. Lichaamsgewichtsoefeningen ondersteunen 0 kg extra gewicht; ondersteuning wordt positief genoteerd. Historie/export bewaren de catalogus-ID, werkelijk uitgevoerde reps, RPE, opwarmmarkering, opmerkingen en ontbrekende snelheidsmetingen.

Automatische tests controleren programmering, telregels, tijd-/volumesignalen, migratie, opslagfouten en een volledige editorcyclus met herladen en opslaan. Zie ook [DEPLOYMENT.md](../DEPLOYMENT.md). Browseropslag blijft toestelgebonden; account- en Android-synchronisatie staan los van deze uitbreiding.
