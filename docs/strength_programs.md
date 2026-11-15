# Krachtprogramma's en programmagenerator

Stand 14 november 2026. Dit document beschrijft `webapp/src/domain/generator.ts` en de bijhorende instelkaart. Het vult `docs/strength_program_2026_10.md` aan; dat document beschrijft het oorspronkelijke startschema A/B, dat blijft bestaan voor accounts zonder programma-instellingen.

Niets hier is een individueel gemeten optimum. De getallen zijn startpunten uit groepsonderzoek die de sporter zelf kan aanpassen. Het programma is niet op echte sporters getest.

## Wat de sporter instelt

| Instelling | Waarden | Effect |
|---|---|---|
| Doel | Algemene kracht, powerlifting, spiergroei, atletische power, kracht naast duursport | Bepaalt sets, herhalingen, doel-RPE, rust en welke blokken in de sessie zitten |
| Ervaring | Beginner, gevorderd, ervaren | Eén set minder of meer op hoofdoefeningen; doel-RPE voor beginners begrensd op 8 |
| Materiaal | Tien soorten materiaal, met vijf voorkeuzes (volledige gym, thuisgym, dumbbells/kettlebell, machines, alleen lichaamsgewicht) | Alleen oefeningen die met dat materiaal kunnen worden gekozen |
| Herstart na onderbreking | Aan/uit | Twee weken één set minder op hoofdoefeningen en één RPE-punt lager |
| Elke vierde week lichter | Aan/uit, standaard uit | Ongeveer 40 % minder sets en 1,5 RPE-punt lager in week 4, 8, … |

Het aantal krachttrainingen per week volgt uit de bestaande keuzes voor dagen en prioriteit (`strengthSlots`). Nieuw: wie "duur" als prioriteit heeft en twee dagen traint, krijgt met programma-instellingen één krachttraining in plaats van nul. De techniekverklaring voor olympische varianten (`olympicExperience`) blijft de bestaande profielvraag.

## Opbouw van een sessie

1. Sjabloon volgens het aantal krachttrainingen per week: één (squat, bankdrukken en deadlift in één sessie), twee of drie (volledig lichaam), vier of meer (onder-/bovenlichaam).
2. Volgorde: explosief werk eerst, dan de zwaarste meergewrichtsoefeningen, dan secundair en ondersteunend werk.
3. Per plaats in het sjabloon wordt de eerste oefening gekozen die het juiste bewegingspatroon heeft, met het materiaal kan, binnen het techniekniveau valt en nog niet in de sessie zit. Voorkeursoefeningen (bijvoorbeeld back squat) gaan voor; daarna gaan extern belaste oefeningen voor op lichaamsgewicht, omdat die in kleine stappen kunnen stijgen.
4. Is er voor een plaats niets beschikbaar, dan blijft ze leeg en staat dat in de toelichting. Er wordt geen oefening uit een ander patroon in de plaats gezet.
5. Past de sessie niet in de beschikbare tijd, dan vervallen eerst ondersteunende oefeningen, dan secundaire, dan sets (nooit onder twee op een hoofdoefening). Rusttijden worden niet ingekort. Wat vervalt staat met naam in de toelichting.

| Doel | Hoofdoefening | Secundair | Ondersteunend | Explosief | Bijzonderheden |
|---|---|---|---|---|---|
| Powerlifting | 4 × 4, RPE 7,5, 3,5 min | 3 × 5 | 2 × 8 | 3 × 2 | Wedstrijdoefening eerst |
| Algemeen | 3 × 6, RPE 7,5, 3 min | 3 × 8 | 2 × 10 | 3 × 3 | |
| Spiergroei | 3 × 8, RPE 8, 2,5 min | 3 × 10 | 3 × 12 | geen | Twee extra ondersteunende plaatsen; resterende tijd wordt gevuld tot hoogstens vier sets per oefening |
| Power | 3 × 4, RPE 7 | 2 × 5 | 2 × 8 | 4 × 3, RPE ≤ 6,5, 3 min | Twee explosieve oefeningen per sessie |
| Naast duursport | 3 × 4, RPE 7,5 | 2 × 6 | 2 × 8 | 3 × 3 | Ondersteunend beenwerk vervalt, hoofdoefeningen voor de benen blijven |

## Gewicht en progressie

- Een werkgewicht komt uit de laatst gelogde werkset van **dezelfde** oefening. Bestaat die niet, dan wordt voor de zes oefeningen uit de intake het daar ingevulde werkgewicht gebruikt, maar alleen bij sets van zes herhalingen of minder (de intake vraagt een gewicht voor ongeveer vijf). In alle andere gevallen blijft het gewicht leeg. Er wordt nooit een gewicht afgeleid uit een andere oefening of uit een geschatte 1RM.
- Progressie is een suggestie in de notitie bij de oefening, geen automatische wijziging: na twee opeenvolgende trainingen op hetzelfde gewicht waarin alle herhalingen zijn gehaald met een gelogde RPE van 8 of lager. Zonder gelogde RPE komt er geen suggestie.
- Een gemiste training wordt niet ingehaald: het schema voegt nooit sets toe om een gat te compenseren.

## Onderbouwing en grenzen

| Keuze | Bron | Wat de bron zegt | Wat de bron niet zegt |
|---|---|---|---|
| Zware hoofdoefeningen (lage herhalingen), 2 of meer sets, vroeg in de sessie, minstens tweemaal per week voor kracht; ongeveer tien of meer sets per spiergroep per week voor spiergroei; matige last, snel bewogen en weinig volume voor power | ACSM Position Stand 2026, Med Sci Sports Exerc 58(4):851–872, doi:10.1249/mss.0000000000003897 | Overzicht van systematische reviews bij gezonde volwassenen. Weinig voorschriftvariabelen veranderen de uitkomst consistent; tot falen trainen, het soort materiaal en ingewikkelde periodisering deden dat niet. | Geen individuele dosis. De percentages 1RM zijn hier niet overgenomen als voorschrift, omdat de app geen gemeten 1RM heeft; de zwaarte volgt uit herhalingen en RPE. |
| Lichtere week is een keuze en staat standaard uit | Coleman et al. 2024, PeerJ 12:e16777, doi:10.7717/peerj.16777 | Eén gerandomiseerde studie: een week volledige rust halverwege gaf iets minder krachtwinst en verder geen verschil. | Het ging om een week zonder training, niet om een week met minder sets. Over de lichtere week zoals de app ze invult bestaat geen direct bewijs. |
| Rust van 1,5 tot 3,5 minuut, nooit ingekort om tijd te winnen | Singer et al. 2024, Front Sports Act Living, doi:10.3389/fspor.2024.1429789 | Meta-analyse voor spiergroei: klein voordeel van meer dan 60 s rust, geen aantoonbaar verschil boven 90 s. | Niets over maximale kracht; de langere rust bij zware sets is praktijkgebruik. |
| Trekken en sprongen als volwaardig explosief werk voor wie geen opvangtechniek heeft | Morris et al. 2022, Sports Med 52:1533–1554, doi:10.1007/s40279-021-01627-2 | Gewichthefoefeningen gaven meer sprongwinst dan traditionele krachttraining en ongeveer evenveel als plyometrie. | Geen vergelijking tussen trekken zonder opvang en volledige varianten binnen dezelfde studie. |
| Beenwerk beperken naast duursport, explosief werk gescheiden van duurtraining | Schumann et al. 2022, Petré et al. 2021 (zie `MODEL_REGISTER.md`) | Geen gemiddeld nadeel voor maximale kracht en spiergroei; wel voor explosieve kracht wanneer beide vormen in dezelfde sessie vallen. | Hoeveel ondersteunend beenwerk een individuele duursporter verdraagt. Het schrappen ervan is een voorzichtige keuze, geen bewezen optimum. |
| Directe set = 1, indirecte = 0,5 bij de weektelling | Pelland et al. (zie `docs/strength_program_2026_10.md`) | Deze telwijze beschreef de dosis-responsrelatie het best. | — |

Zonder bron en dus vuistregel: de exacte set- en herhalingsgetallen per doel, de regel voor progressie, de twee herstartweken, de vermindering van 40 % in de lichtere week, de tijdsschatting per sessie en de indeling van oefeningen in techniekniveaus.

## Bestaande accounts en gegevens

- Het programma is een optioneel veld `program` in het profiel. Een profiel zonder dat veld krijgt exact het oorspronkelijke schema. Er is geen databasemigratie: het profiel wordt al als één geheel bij het account bewaard.
- "Terug naar het oorspronkelijke startschema" verwijdert alleen dat veld.
- Gelogde trainingen worden niet gelezen om ze te wijzigen en niet herschreven. Dagen die de sporter zelf heeft aangepast, blijven zoals ze zijn.
- De 16 nieuwe oefeningen hebben nieuwe identiteiten; bestaande identiteiten zijn ongewijzigd.

## Tests

`webapp/tests/generator.test.tsx` (15 tests) toetst onder meer: ruim 3000 combinaties van doel, ervaring, materiaal, dagen en duur op geldigheid, materiaal en techniekniveau; tijdsinpassing met benoemde inkorting; expliciete melding bij ontbrekend materiaal; herkomst van het gewicht; progressie als suggestie; geen inhaalvolume; weekregels; weektekort bij spiergroei; ongewijzigd gedrag voor profielen zonder programma; en het bewaren en terugdraaien via de kaart.

## Open

- De eenheid per kant bij dumbbells en de last bij kettlebells is niet apart gemodelleerd; het gewichtsveld is vrij.
- Er is geen keuze voor blessures of bewegingsbeperkingen; vervangen gebeurt met de hand in de planeditor, die oefeningen met hetzelfde patroon en passend materiaal bovenaan zet.
- De rekenmotor (weekplanner) krijgt de gegenereerde sessies als geplande trainingen, maar kiest zelf geen doel of oefeningen.
