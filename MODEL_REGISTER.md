> Herzien op 15 november 2026. Zie `REVIEW_2026_11_15.md` voor correcties na deze aangeleverde audit. Simulatieresultaten hieronder zijn geen externe validatie of bewijs van causaliteit.

# Modellenregister

Stand 14 november 2026, engineversie `ct-engine-3.2.0`, concurrent model `ct-concurrent-1.0.0`, contractversie `1`.

Dit register beschrijft per deelmodel wat het voorstelt, waarop het steunt, wat er mis mee was, wat er is gekozen en wat er nog ontbreekt. "Gekoppeld" betekent: de gebruiker van de webapp ziet er vandaag een uitkomst van. Geen enkel model hier is empirisch gevalideerd op echte atleten.

De bronnen staan onderaan. Een bron met ✔ heb ik op 13 november 2026 opnieuw opgezocht en de kernbevinding nagelezen in samenvatting of volledige tekst. Bronnen zonder ✔ komen uit de bestaande documentatie en zijn niet opnieuw nagelezen.

## A. Webapp (gekoppeld)

| Model | Construct, invoer en uitvoer | Onderbouwing | Probleem | Keuze | Nodig | Status |
|---|---|---|---|---|---|---|
| Setstelling per spiergroep (`webapp/src/domain/volume.ts`) | Trainingsdosis als aantal werksets per week. Directe set = 1, indirecte = 0,5; opwarmsets en explosieve reps apart; sets onder RPE 6 tellen niet als spierset. | De fractionele telwijze voorspelde hypertrofie en kracht het best in meta-regressies over 67 studies [Pelland]. Kracht hangt nauwelijks af van de afstand tot falen, hypertrofie wel [Robinson]. | Geen fout gevonden. De RPE-6-grens en de signaalgrens van 16 sets zijn vuistregels. | Behouden. | Gelogde sets; RPE voor de lichte-setregel. | Beschrijvend; geen individuele herstelgrens. |
| Startschema A/B (`domain/program.ts`) | Vaste oefenkeuze en setaantallen binnen gekozen dagen en tijd; werkgewicht = laatst gelogde van dezelfde oefening. | Praktijkschema, toegelicht in `docs/strength_program_2026_10.md`. | Bij prioriteit "duur" en minder dan drie dagen plant het nul krachtsessies. Geen progressie- of deloadregel. | Niet gewijzigd; hoort bij de programmagenerator. | — | Sjabloon, geen gepersonaliseerd programma. |
| Programmagenerator (`domain/generator.ts`) | Krachtsessies volgens doel, ervaring en materiaal; uitvoer: oefeningen, sets, herhalingen, doel-RPE, rust en een toelichting met alles wat is ingekort of ontbreekt. | ACSM 2026, Coleman 2024, Singer 2024, Morris 2022, Schumann 2022, Petré 2021; zie `docs/strength_programs.md`. De exacte getallen zijn vuistregels. | Was een aanzet in `wip/` die niet bouwde en een verplichte lichtere week oplegde. | Herwerkt: vast schema als standaard, lichtere week facultatief, gewicht alleen uit dezelfde oefening of de intake, niets stil weggelaten. Alleen actief na een keuze van de sporter. | Vergelijking met wat sporters werkelijk volhouden; individuele aanpassing op gelogde respons. | Ongevalideerd; 15 tests op de regels. |
| Tijdsschatting (`estimatedMinutes`) | 8 min opstart, 4–6 s per rep, geplande rust. | Geen bron; vuistregel. | — | Behouden als indicatie. | — | Ongevalideerd. |
| Trend (`measuredTrend`) | Zwaarste gelogde set per dag. | Het is een meting, geen model. | — | Behouden. | — | n.v.t. |

## B. Rekenkern `app/science` (niet gekoppeld, bedoeld voor fase 3)

| Model | Construct, invoer en uitvoer | Onderbouwing | Gevonden probleem | Correctie of keuze | Minimaal nodig | Status |
|---|---|---|---|---|---|---|
| Load–velocity-profiel (`load_velocity.py`) | Verwachte snelheid bij een last, per oefening, apparaat en meetgrootheid. Lineair, alleen binnen het gemeten lastbereik. Invoer: snelste gemeten rep van de eerste set per last. | Extrapolatie naar 1RM overschat en complexere modellen zijn niet nauwkeuriger; snelheid bij een vaste last volgen wordt als alternatief genoemd [Greig]. Apparaten verschillen in validiteit, lineaire transducers scoren het best [Weakley]. | Geen fout in de fit. Drempels (4 punten, 3 lasten, 25 % bereik, R² ≥ 0,90) zijn keuzes. | Behouden. Geen 1RM uit snelheid. | Vier punten over drie lasten, één apparaat, één meetgrootheid, binnen 56 dagen. | Software getoetst; niet gevalideerd. |
| Afwijking laatste sessie (`service._velocity_group`) | Gemeten min verwachte snelheid, gestandaardiseerd met de voorspelfout van een profiel uit uitsluitend eerdere sessies. | Gewone regressietheorie. | SCI-02: vaste grens z = 2 bij twee vrijheidsgraden. | Student-t-grens; grens in de uitvoer. | Geldig eerder profiel en lasten binnen bereik. | Software getoetst met simulatie; de betekenis van een afwijking is een prestatieverschil, geen vermoeidheidsmeting. |
| Snelheidsverlies (`velocity_loss`) | Verlies van de laatste rep tegenover de snelste. Ontbreekt de laatste meting, dan geen waarde. | Hogere drempels gaan samen met meer hypertrofie, lagere met betere sprong, sprint en snelheid bij submaximale last; kracht verschilt niet [Jukic a]. Als voorspeller van het aandeel gedane herhalingen is het onnauwkeurig en instabiel tussen sessies [Jukic b]. | Geen. | Alleen rapporteren, geen reserve of vermoeidheid afleiden. | Laatste rep en minstens één eerdere gemeten. | Beschrijvend. |
| 1RM-schatting uit reps en RPE (`strength_estimates.py`) | Geschat maximum uit last, herhalingen en gerapporteerde reserve, met band. | Mensen onderschatten hun resterende herhalingen gemiddeld met 0,95, nauwkeuriger dicht bij falen en bij ≤ 12 herhalingen [Halperin]. Formules verliezen nauwkeurigheid boven circa tien herhalingen [Macarilla]. | SCI-04 (sprong bij één herhaling); SCI-06 (maximum over sets, open). | Brzycki; alleen bij RPE ≥ 7 en ≤ 12 herhalingen tot falen; altijd "schatting". | Eén werkset met RPE ≥ 7 in de laatste 42 dagen. | Niet gevalideerd voor sets die voor falen stoppen. |
| Critical power, tweeparameter (`critical_power.py`) | CP (W) en W′ (J) uit lineaire arbeid–tijdregressie op aangemerkte maximale inspanningen van 2–20 min. | Protocol is niet gestandaardiseerd; aantal, duur en model beïnvloeden de uitkomst [Muniz-Pumares]. Zonder inspanningen boven 10–12 min wordt CP overschat; twee inspanningen van 12–20 min geven goede overeenkomst [Mattioni Maturana]. Aannames en grenzen van het model [Chorley 2020]. | SCI-03. | Beste per duur, waarschuwingen, afwijzing bij standaardfout > 5 % (CP) of > 10 % (W′) of niet-dalend vermogen. | Drie maximale inspanningen van verschillende duur, bij voorkeur binnen zes weken en één van ≥ 10 min. | Software getoetst; de drempels voor de standaardfout zijn gangbaar maar hier niet opnieuw onderbouwd. |
| W′-balans (`w_prime_balance`) | Resterende arbeidscapaciteit boven CP tijdens een rit, differentiaalvorm. | Differentiaalvorm [Skiba 2015]. Herstel vertraagt bij herhaalde uitputting en het model paste slecht op een herhaalde ramptest [Chorley 2019]. Mono-exponentiële modellen onderschatten herstel onder circa 2 min en overschatten het boven 5 min; een bi-exponentieel model past beter [Chorley 2023]. De differentiaalvorm kan niet per persoon worden afgesteld [EJAP 2025]. | Geen implementatiefout. | Behouden als benadering; niet gebruikt voor uitspraken in `service.py`. Kandidaat voor de workoutspeler, met de beperking zichtbaar. | Geldige CP en W′; 1 Hz-vermogen. | Benadering; geen meting. |
| Duurbelasting (`service._endurance_session_load`) | Minuut-equivalenten ∫(P/P_ref)² dt; terugval op sessie-RPE × minuten of alleen duur. | Geen directe bron voor de exponent. | SCI-01 (sport); SCI-07 (heuristiek, open). | Sportgebonden referentie; methodes niet optellen; geen verhouding acuut/chronisch. | Vermogen én een referentie voor dezelfde sport. | Heuristiek. |
| Weektotalen (`service._load`) | Laatste 7 dagen naast de 28 dagen daarvoor, zonder ratio. | De acute:chronische ratio heeft statistische artefacten en geen voorspellende meerwaarde [Impellizzeri a, b]. | Geen. | Bewust geen ratio en geen blessureclaim. | — | Beschrijvend. |
| Concurrent signaal (`service._concurrent`) | Vlag bij kracht en duur op dezelfde dag; aparte code bij explosief onderlichaamwerk binnen 3 uur. | Maximale kracht (SMD −0,06) en hypertrofie (−0,01) niet aangetast, explosieve kracht wel (−0,28), vooral in dezelfde sessie en niet bij ≥ 3 uur ertussen; onafhankelijk van type duurtraining, frequentie, trainingsstatus en leeftijd [Schumann]. | SCI-05. | Volgorde en regio toegevoegd; bronverwijzing alleen waar het bewijs past. | Starttijden van beide sessies; regio en "explosief" per oefening. | Contextsignaal op groepsniveau; geen individuele schatting. |
| Eigen voorspeltoets (`reference_model.py`, `_forecast_check`) | Vergelijkt per atleet M0/M1 met vaste parameters tegen "vast profiel", "laatste waarneming" en "gemiddelde van drie", vooruitlopend in de tijd. | Opzet volgt `docs/research_protocol.md`. | Geen lekkage gevonden. De dosis is genormaliseerd op de hoogste kalibratielast, een willekeurige schaal. | Behouden als eerlijkheidscontrole; geen afgestelde voorspelling. | Acht testsessies na een bevroren kalibratie. | Op de synthetische fixture wint "laatste waarneming". |

## C. Oud driecompartimentenmodel `app/domain` (niet gekoppeld; vervangen door D)

| Model | Construct | Onderbouwing | Probleem | Keuze | Status |
|---|---|---|---|---|---|
| Repmodel (`rep_engine.py`) | Snelheid = referentie × lokale × systemische × metabole beschikbaarheid. | Geen directe meting van een van de drie; zie `docs/audit_2026_09.md`. | Instantaan niet te onderscheiden; LEG-01 (gecorrigeerd), LEG-02, LEG-06. | Alleen de programmeerfout hersteld. | Onderzoekscode. |
| Dagmodel (`day_engine.py`, `day_transition.py`) | Zeven toestanden per dag, waaronder "mitochondriale herstelcapaciteit" en "structurele beenbelasting". | Fitness-fatiguemodellen zijn slecht geconditioneerd, parameters hangen af van startwaarden en invoer, en de vermoeidheidsterm verbeterde de voorspelling niet [Vermeire, Marchal]. | LEG-03, LEG-04, LEG-05; tientallen vaste coëfficiënten zonder kalibratiedata. | Niet afgestemd; gebreken als tests vastgelegd. | Onderzoekscode; ongeschikt als basis voor advies. |
| Duurimpuls (`endurance_engine.py`) | Zelfde kwadratische maat als in B, plus een verdeling "laag/hoog" rond 85–95 % van de drempel. | Geen bron voor de verdeling. | De grenzen zijn compatibiliteitsbakken, geen gemeten drempels (zo staat het ook in de code). | Niet gewijzigd. | Onderzoekscode. |
| Interferentieterm | HIIT-impuls × sportfactor (lopen 1,3; fietsen 1,0; zwemmen 0,6) × tijdsfactor. | Het type duurtraining was geen significante moderator [Schumann]; de sportfactoren hebben geen bron. | Presenteert een niet-gevalideerde koppeling als mechanisme. | Niet gebruiken. | Onderzoekscode. |

## D. Concurrent model `app/science/concurrent.py` (nieuw, niet gekoppeld)

Dit model vervangt het oude driecompartimentenmodel als kandidaat. Het is gebouwd om kalibreerbaar te zijn op een trainingslog en om eerlijk te melden wanneer het dat niet is.

### Vergelijkingen

Prestatie wordt per domein in logeenheden gemodelleerd, zodat een coëfficiënt van 0,01 ongeveer één procent is.

    kracht, regio r:   y = niveau + a·G_r − b·F_r − k·E_r − i·X_r + ruis
    duur:              y = niveau + a·G_e − b·F_e − k·S_o + t·T   + ruis

`G` is een traag spoor van de eigen dosis ("fitness", tijdconstante 42 dagen), `F` een snel spoor ("vermoeidheid", 2 dagen voor kracht, 1 dag voor duur). De wisselwerking zit in drie termen. `E_r` is het vermoeidheidsspoor van duurtraining die dezelfde regio belast (lopen en fietsen de benen, zwemmen het bovenlichaam) en `S_o` dat van onderlichaamkracht: acute kruisvermoeidheid in beide richtingen. `X_r` is het fitnessspoor van onderlichaamkracht die binnen drie uur van duurtraining werd gedaan: afgezwakte adaptatie. `T` is een fitnessspoor van onderlichaamkracht dat positief bijdraagt aan duurprestatie: transfer.

Elk spoor is een som van dosisimpulsen die exponentieel vervallen, exact berekend tussen de werkelijke sessietijdstippen. De dosis is relatief en dimensieloos: tien werksets voor een regio of zestig minuten op het referentievermogen zijn elk één eenheid; minuten worden gewogen met (vermogen/referentie)².

### Onderbouwing van de structuur

| Term | Bewijs | Wat het bewijs niet geeft |
|---|---|---|
| Afgezwakte krachtadaptatie bij kracht en duur in één sessie (`i`) | Explosieve kracht: SMD −0,28, vooral in dezelfde sessie en niet bij ≥ 3 uur ertussen [Schumann]. Maximale onderlichaamkracht bij getrainden: ES −0,35, in dezelfde sessie −0,66, niet bij gescheiden sessies [Petré]. | Een omrekening van die groepseffecten naar een coëfficiënt per dosis. De prior is een orde van grootte. |
| Kracht → duur, acuut (`k` in de duurvergelijking) | Een krachtsessie kan duurprestatie 24 tot 72 uur verlagen [Doma]. | De grootte per set, en het verschil tussen oefeningen. |
| Duur → kracht, acuut (`k` in de krachtvergelijking) | Geen gepoolde schatting gevonden in deze ronde. De term is een aanname: restvermoeidheid van de benen als verklaring voor het effect in dezelfde sessie. | Alles; dit is de zwakst onderbouwde term en moet zich in de eigen data bewijzen. |
| Kortere tijdconstante voor duurvermoeidheid | Een gewone duursessie is binnen ongeveer een dag verwerkt, een krachtsessie niet [Doma]. | De precieze waarden. In de gekoppelde dienst blijven de tijdconstanten vast vóór de voorspeltoets. De zoekfunctie blijft alleen beschikbaar voor afzonderlijke onderzoeksanalyses. |
| Kracht → duur, chronisch (`t`) | Zware krachttraining verbetert loopeconomie (ES −0,27) en tijdritprestatie (ES −0,47) bij lopers [Llanos-Lagos a, b]. | Hetzelfde voor fietsen binnen deze bronnen; de tijdsschaal. |
| Fitness en vermoeidheid van het eigen domein (`a`, `b`) | Klassieke impuls-responsopzet. | Identificeerbaarheid: die is zwak [Marchal, Vermeire] en wordt daarom gemeten in plaats van aangenomen. |

### Schatting

Bij vaste tijdconstanten is het model lineair in zijn coëfficiënten. Die worden per atleet geschat met Bayesiaanse lineaire regressie: zwak informatieve normale priors in absolute eenheden, en een ruisniveau dat uit de residuen wordt geschat. Dat levert zonder simulatie:

- een posterior en een voorspelinterval voor elke uitspraak;
- per coëfficiënt het aandeel dat door de eigen data is bepaald (`informed_by_data`, 0 = alleen prior, 1 = volledig data);
- de marginale waarschijnlijkheid voor de geneste vergelijking *alleen niveau* → *eigen dynamiek* → *met wisselwerking*.

De wisselwerking wordt voor een atleet alleen als verkennende modelsamenhang beschreven wanneer twee dingen tegelijk gelden: een Bayes-factor boven 3 tegenover het model zonder, en een lagere fout bij vooruitlopend voorspellen (elke waarneming voorspeld uit strikt eerdere). Anders blijven de coëfficiënten gelabeld als prior op groepsniveau. Met minder dan zes prestatiewaarnemingen werkt het model uitsluitend met priors en zegt het dat.

Waarnemingen zijn afgeleid en worden niet opgeslagen. Kracht: de afwijking van de snelste rep ten opzichte van een bevroren load–velocity-profiel, of bij gebrek daaraan de logaritme van de 1RM-schatting; per oefening één soort. Duur: gedateerde maximale inspanningen ten opzichte van de vermogen–duurcurve. Is die curve op dezelfde inspanningen gefit, dan staat dat als circulair in de uitvoer en worden die inspanningen niet gebruikt om de wisselwerking te kalibreren.

### Wat de simulaties laten zien

Gesimuleerde atleten volgen per constructie het model; deze cijfers zeggen dus iets over de schatter, niet over echte mensen. Veertig reeksen per rij.

| Werkelijke kruisvermoeidheid | Meetruis | Krachtsessies met meting | Wisselwerking gemeld | Interval dekt de waarheid |
|---|---|---|---|---|
| 0,05 | 1,5 % | 113 | 100 % | 100 % |
| 0 | 1,5 % | 113 | 0 % | 100 % |
| 0,02 | 3 % | 40 | 23 % | 100 % |
| 0,02 | 3 % | 80 | 60 % | 100 % |
| 0,02 | 3 % | 172 | 82 % | 95 % |
| 0 | 3 % | 172 | 3 % | 93 % |
| 0,04 | 3 % | 40 | 88 % | 97 % |
| 0,04 | 3 % | 80 | 100 % | 97 % |

De praktische les: een bescheiden wisselwerking (2 % per dosiseenheid) bij realistische meetruis vraagt ruim 150 gemeten krachtsessies voor ze betrouwbaar zichtbaar wordt. Dat is ongeveer een jaar. Een sterke wisselwerking is na veertig sessies meestal te zien. Vals alarm blijft op 0 tot 3 %. Met verkeerd aangenomen tijdconstanten (waarheid 3 en 2 dagen, model 2 en 1) bleef de detectie 100 % en het vals alarm 0 % in dertig reeksen. Op één lange reeks was de vooruitlopende fout 0,013 voor het volledige model tegen 0,020 zonder wisselwerking, 0,026 voor alleen niveau en 0,030 voor "laatste waarneming"; 96 % van de waarnemingen viel binnen het 95 %-interval.

### Planning

`plan_week` neemt een lijst sessies (werksets of minuten met relatieve intensiteit, eventueel als sleutelsessie gemarkeerd), de vrije dagen en de tijdsloten, en rangschikt indelingen. De score is de gewogen verwachte frisheid bij de start van elke sessie (sleutelsessies dubbel), plus de verwachte adaptatie en restvermoeidheid aan het eind van de periode, gewogen naar de gekozen prioriteit. Tot 20.000 indelingen wordt alles doorgerekend; daarboven een deterministische zoektocht vanuit twaalf startpunten, die in de gecontroleerde gevallen het optimum van de volledige zoektocht vond. `evaluate_schedule` beoordeelt een zelf opgegeven schema met tijdstippen, inclusief het geval "binnen drie uur".

Een voorbeeld met alleen priors, vijf sessies over vijf vrije dagen: intervallen op de eerste ochtend, zware benen de ochtend erna (verwacht effect van restvermoeidheid −0,7 %, interval −2,5 tot +1,2 %), bovenlichaam dezelfde avond, rustige duur en lichte benen later in de week. Het interval omvat nul. Zonder eigen data is de rangschikking dus een ordening volgens aannames op groepsniveau en geen gemeten voordeel; de uitvoer zegt dat in `basis` en `limitations`.

### Antwoord op de gebreken van het oude model

| Gebrek | Oplossing |
|---|---|
| LEG-02, onstetigheid bij ontbrekende rust | Continue tijd met echte tijdstippen. Zonder starttijd telt een sessie op de middag van haar datum en wordt ze nooit als "binnen drie uur" gemarkeerd; het aantal zulke gevallen staat in de uitvoer. |
| LEG-03, vermoeidheid verlaagt capaciteit blijvend | Vermoeidheid is een tijdelijke term; na rust is haar bijdrage nul (getest). |
| LEG-04, impuls schaalt met absolute last | Relatieve dosis; dezelfde sessie geeft bij dubbele last dezelfde dosis (getest). |
| Niet te onderscheiden compartimenten | Eén vergelijking per domein, lineair, met gemeten identificeerbaarheid. Bij nauwelijks variërende training meldt het model dat de fitnessterm niet te bepalen is (getest). |
| Geen onzekerheid | Elk getal heeft een interval; een uitspraak op priors is als zodanig gelabeld. |

### Beperkingen

Het model is niet gevalideerd op echte atleten. De priors zijn ordes van grootte. De dosis voor duurtraining zonder vermogen berust op een aangenomen schaal (sessie-RPE 7 als referentie-intensiteit, of het opgegeven type training); de bron staat per sessie geteld in de uitvoer. Werksets zijn een grove krachtdosis die geen onderscheid maakt tussen vijf en vijftien herhalingen. Het niveau is constant binnen het venster van 400 waarnemingen, zodat trage veranderingen buiten training (lichaamsgewicht, techniek) in de fitnessterm of de ruis terechtkomen. De duurkant heeft in de praktijk weinig waarnemingen en zal lang op priors draaien. Er is geen uitspraak over blessurerisico of gezondheid.

## Mogelijke wetenschappelijke nieuwheid

Het combineren van een load–velocity-profiel, critical power en een concurrente koppelterm is op zichzelf niet nieuw, en de gelijkenis met commerciële systemen is geen argument. Voor impuls-responsmodellen met meerdere energiesystemen bestaat intussen een voorstel in preprint [Kontro]; ook daar gaat het om een modelvoorstel, niet om een onafhankelijke validatie.

Waar wel een bijdrage kan liggen is een scherp, toetsbaar voorspelvraagstuk dat voor zover ik kon nagaan niet zo is onderzocht: voorspelt de duurbelasting van de voorgaande 24 tot 72 uur de afwijking van de staafsnelheid bij een gestandaardiseerde submaximale last, bovenop wat de eigen krachttrainingshistorie al voorspelt? De hypothese en de vergelijking zijn dan:

1. Uitkomst: gemiddelde concentrische snelheid van de snelste rep bij een vaste last (bijvoorbeeld de eerste set op 60–70 % van het recente werkgewicht), één apparaat, één oefening.
2. Modellen, genest: vast profiel; laatste waarneming; M0 (traag niveau); M1 (plus krachtdosis); M2 (plus duurdosis, per sport).
3. Toets: vooruitlopende voorspelling per atleet, parameters bevroren voor de testperiode, MAE in m/s met betrouwbaarheidsinterval over atleten. M2 moet M1 verslaan met een vooraf vastgelegde marge.
4. Wat ontbreekt: echte data. Nodig zijn enkele tientallen getrainde atleten over minstens 12 weken met gestandaardiseerde snelheidsmetingen, starttijden van alle sessies en vermogen bij de duurtraining; daarnaast ethische goedkeuring en preregistratie.

Zonder dat onderzoek is er geen nieuwheidsclaim te maken. Een negatief resultaat (M2 voegt niets toe) is even publiceerbaar en zou de koppelterm definitief uit de app houden.

## Onderzoeks- en validatieplan

Het bestaande `docs/research_protocol.md` en `docs/real_world_shadow_protocol.md` blijven de basis. Aanvullingen uit deze audit:

1. Opslag eerst: starttijd per sessie, meetgrootheid en apparaat per snelheidsmeting (DATA-06). Zonder die velden is geen van de onderstaande stappen uitvoerbaar.
2. Schaduwfase: de engine rekent mee zonder dat de uitkomst advies stuurt. Bewaar per uitvoer `engine_version`, `contract_version` en `input_digest`, zodat herberekening controleerbaar is en metingen nooit worden herschreven.
3. Kalibratie van het ruisniveau: toets op echte data of het aandeel "trager/sneller" bij onveranderde omstandigheden rond de nominale 5 % ligt.
4. CP: vergelijk de fit met een onafhankelijke inspanning die niet in de fit zat (bijvoorbeeld een tijdrit van 8–12 minuten) en rapporteer de fout in watt.
5. Pas daarna de geneste vergelijking uit de vorige paragraaf.

Reproduceren: `python -m research.evaluate --manifest research/example_manifest.json --events research/example_events.csv --output uit.json` voor de synthetische vergelijking, `python tools/regenerate_contract_fixtures.py` voor de enginefixtures (alleen bij een bewuste engine- of contractwijziging, met versieverhoging).

## Bronnen

| Sleutel | Verwijzing | Soort bewijs, populatie en beperking |
|---|---|---|
| ACSM 2026 ✔ (14 nov) | American College of Sports Medicine Position Stand: resistance training prescription for muscle function, hypertrophy and physical performance in healthy adults. Med Sci Sports Exerc 2026;58(4):851–872. doi:10.1249/mss.0000000000003897 | Overzicht van systematische reviews bij gezonde volwassenen; geen individuele dosis. Alleen de samenvatting en bespreking nagelezen. |
| Coleman 2024 ✔ (14 nov) | Coleman M e.a. Gaining more from doing less? The effects of a one-week deload period during supervised resistance training on muscular adaptations. PeerJ 2024;12:e16777. doi:10.7717/peerj.16777 | Eén gerandomiseerde studie bij getrainde jongvolwassenen; week volledige rust, geen week met minder sets. |
| Singer 2024 ✔ (14 nov) | Singer A e.a. Give it a rest: a systematic review with Bayesian meta-analysis on the effect of inter-set rest interval duration on muscle hypertrophy. Front Sports Act Living 2024;6:1429789. doi:10.3389/fspor.2024.1429789 | Meta-analyse voor spiergroei; zegt niets over maximale kracht. |
| Morris 2022 ✔ (14 nov) | Morris SJ e.a. Comparison of weightlifting, traditional resistance training and plyometrics on strength, power and speed: a systematic review with meta-analysis. Sports Med 2022;52:1533–1554. doi:10.1007/s40279-021-01627-2 | Meta-analyse; vooral jonge, getrainde mannen. |
| Schumann ✔ | Schumann M e.a. Compatibility of concurrent aerobic and strength training for skeletal muscle size and function: an updated systematic review and meta-analysis. Sports Med 2022;52:601–612. doi:10.1007/s40279-021-01587-7 | Meta-analyse, 43 studies, gezonde volwassenen, ≥ 4 weken. Groepsgemiddelden; explosieve kracht vooral onderlichaam; fietsen en lopen. |
| Halperin ✔ | Halperin I e.a. Accuracy in predicting repetitions to task failure in resistance exercise: a scoping review and exploratory meta-analysis. Sports Med 2022;52:377–390. doi:10.1007/s40279-021-01559-x | Verkennende meta-analyse, 12 studies, 414 deelnemers. Grote heterogeniteit tussen studies. |
| Greig ✔ | Greig L e.a. The predictive validity of individualised load–velocity relationships for predicting 1RM: a systematic review and individual participant data meta-analysis. Sports Med 2023;53:1693–1708. doi:10.1007/s40279-023-01854-9 | IPD-meta-analyse, 26 studies, 434 deelnemers in de analyse. Vooral getrainde jonge mannen, squat en bankdrukken. |
| Weakley ✔ | Weakley J e.a. The validity and reliability of commercially available resistance training monitoring devices: a systematic review. Sports Med 2021;51:443–502. doi:10.1007/s40279-020-01382-w | Systematische review. Veel studies zonder gouden standaard als criterium. |
| Jukic a ✔ | Jukic I e.a. The acute and chronic effects of implementing velocity loss thresholds during resistance training: a systematic review, meta-analysis, and critical evaluation of the literature. Sports Med 2023;53:177–214. doi:10.1007/s40279-022-01754-4 | Meta-analyse met meta-regressie. Volume meestal niet gelijkgetrokken tussen drempels. |
| Jukic b ✔ | Jukic I e.a. Velocity loss is a flawed method for monitoring and prescribing resistance training volume with a free-weight back squat exercise. Eur J Appl Physiol 2023;123:1343–1357. doi:10.1007/s00421-023-05155-x | Primaire studie, getrainde deelnemers, back squat. |
| Pelland ✔ | Pelland JC e.a. The resistance training dose response: meta-regressions exploring the effects of weekly volume and frequency on muscle hypertrophy and strength gains. Sports Med 2026;56:481–505 (online december 2025). doi:10.1007/s40279-025-02344-w | Meta-regressies, 67 studies, 2.058 deelnemers. Groepsniveau; geen individuele grenzen. |
| Robinson ✔ | Robinson ZP e.a. Exploring the dose–response relationship between estimated resistance training proximity to failure, strength gain, and muscle hypertrophy: a series of meta-regressions. Sports Med 2024;54:2209–2231. | Verkennende meta-regressies; afstand tot falen in veel studies geschat. DOI niet nagekeken. |
| Muniz-Pumares ✔ | Muniz-Pumares D e.a. Methodological approaches and related challenges associated with the determination of critical power and curvature constant. J Strength Cond Res 2019;33:584–596. | Narratieve review. DOI niet nagekeken. |
| Mattioni Maturana ✔ | Mattioni Maturana F e.a. Critical power: how different protocols and models affect its determination. J Sci Med Sport 2018. | Primaire studie, 13 jonge getrainde fietsers, vijf inspanningen van circa 1–20 min. Kleine steekproef. Jaargang, pagina's en DOI niet nagekeken. |
| Chorley 2020 ✔ | Chorley A, Lamb KL. The application of critical power, the work capacity above critical power (W′), and its reconstitution: a narrative review. Sports 2020;8:123. doi:10.3390/sports8090123 | Narratieve review, fietsen. |
| Chorley 2019 ✔ | Chorley A e.a. Slowing the reconstitution of W′ in recovery with repeated bouts of maximal exercise. Int J Sports Physiol Perform 2019;14:149–155. | Primaire studie, 20 volwassenen, herhaalde ramptest. |
| Chorley 2023 ✔ | Chorley A, Marwood S, Lamb KL. A dynamic model of the bi-exponential reconstitution and expenditure of W′ in trained cyclists. Eur J Sport Sci 2023. | Primaire modelstudie, getrainde fietsers. Deel en pagina's niet nagekeken. |
| Skiba 2015 ✔ | Skiba PF e.a. Intramuscular determinants of the ability to recover work capacity above critical power. Eur J Appl Physiol 2015;115:703–713. doi:10.1007/s00421-014-3050-3 | Primaire studie, tien recreatief getrainde deelnemers, eenbenige knie-extensie. |
| EJAP 2025 ✔ | Eur J Appl Physiol 2025, doi:10.1007/s00421-025-05912-0 (vergelijking van tijdconstanten voor W′-herstel bij intermitterende inspanning). | Primaire studie. Auteurs en titel niet nagekeken. |
| Vermeire ✔ | Vermeire K e.a. The fitness–fatigue model: what's in the numbers? Int J Sports Physiol Perform 2022;17:810–813. doi:10.1123/ijspp.2021-0494 | Commentaar. |
| Marchal ✔ | Marchal A e.a. Statistical flaws of the fitness-fatigue sports performance prediction model. Sci Rep 2025. doi:10.1038/s41598-025-88153-7 | Bayesiaanse analyse met kruisvalidatie, bevestigd op twee onafhankelijke datasets. |
| Impellizzeri a ✔ | Impellizzeri FM e.a. Acute:chronic workload ratio: conceptual issues and fundamental pitfalls. Int J Sports Physiol Perform 2020;15:907–913. doi:10.1123/ijspp.2019-0864 | Conceptueel artikel. |
| Impellizzeri b ✔ | Impellizzeri FM e.a. What role do chronic workloads play in the acute to chronic workload ratio? Time to dismiss ACWR and its underlying theory. Sports Med 2021;51:581–592. doi:10.1007/s40279-020-01378-6 | Heranalyse van eerder gepubliceerde blessure- en belastingsdata. |
| Macarilla ✔ | Macarilla CT e.a. J Hum Kinet 2022;82 (voorspelling van 1RM uit submaximale snelheid bij squat en bankdrukken; PMC9465738). | Primaire studie; de inleiding vat de nauwkeurigheid van Epley en Brzycki bij 3–5RM samen en het verlies bij hogere herhalingsaantallen. Exacte titel en pagina's niet nagekeken. |
| Petré ✔ | Petré H e.a. Development of maximal dynamic strength during concurrent resistance and endurance training in untrained, moderately trained, and trained individuals: a systematic review and meta-analysis. Sports Med 2021;51:991–1010. doi:10.1007/s40279-021-01426-9 | Meta-analyse, 27 studies, 1RM squat en legpress. De auteurs noemen de meeste studies klein. |
| Doma ✔ | Doma K, Deakin GB, Bentley DJ. Implications of impaired endurance performance following single bouts of resistance training: an alternate concurrent training perspective. Sports Med 2017;47(11). doi:10.1007/s40279-017-0758-3 | Narratieve review van acute studies. |
| Llanos-Lagos a ✔ | Llanos-Lagos C e.a. Effect of strength training programs in middle- and long-distance runners' economy at different running speeds. Sports Med 2024;54:895–932. doi:10.1007/s40279-023-01978-y | Meta-analyse bij lopers; zekerheid matig voor zware lasten. |
| Llanos-Lagos b ✔ | Llanos-Lagos C e.a. The effect of strength training methods on middle-distance and long-distance runners' athletic performance. Sports Med 2024;54:1801–1833. doi:10.1007/s40279-024-02018-z | Meta-analyse bij lopers; zekerheid zeer laag tot matig. |
| Kontro ✔ | Kontro H e.a. The three-dimensional impulse-response model. arXiv:2503.14841 (2025). | Preprint, modelvoorstel; niet peer-reviewed in de gevonden versie. |
| Skiba & Clarke | Skiba PF, Clarke DC. Int J Sports Physiol Perform 2021. doi:10.1123/ijspp.2021-0205 | Uit bestaande documentatie; niet opnieuw nagelezen. |
| Brzycki | Brzycki M. Strength testing: predicting a one-rep max from reps-to-fatigue. J Phys Educ Recreat Dance 1993;64:88–90. | Oorspronkelijke formule; niet opnieuw nagelezen. |

De literatuurcontrole was gericht, geen systematische review: per modelkeuze is naar de recentste meta-analyse of het meest geciteerde primaire werk gezocht. Een uitputtende zoekstrategie met vastgelegde zoektermen en selectiecriteria hoort bij het onderzoeksprotocol.
