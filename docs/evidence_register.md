# Evidence and prior-art register

Targeted checks on 6 September 2026. This is not a systematic review or a guarantee
that every competing model has been found. Entries separate evidence for a general
principle from support for this repository's specific equations. No cited study
validates the repository's exact coefficients.

## E01 — concurrent adaptation

Schumann et al. (2022), *Compatibility of Concurrent Aerobic and Strength Training
for Skeletal Muscle Size and Function: An Updated Systematic Review and Meta-Analysis*.
43 studies; no overall compromise of maximal strength or hypertrophy was detected,
whereas explosive-strength adaptation was more vulnerable, particularly with
same-session scheduling. This qualifies universal “HIIT impairs strength” claims;
it does not prove no interference in every athlete or quantify an individual
24-hour exponential coupling. [Publisher](https://link.springer.com/article/10.1007/s40279-021-01587-7),
[PubMed](https://pubmed.ncbi.nlm.nih.gov/34757594/).

## E02 — load–velocity validity

Greig et al. (2023), *The Predictive Validity of Individualised Load–Velocity
Relationships for Predicting 1RM: A Systematic Review and Individual Participant
Data Meta-analysis*. Predictive errors were material and 1RM tended to be
overestimated. A personalized line is therefore not sufficient evidence of accurate
1RM or day-to-day readiness. Prefer direct standardized velocity targets and retain
measurement uncertainty. [Publisher](https://link.springer.com/article/10.1007/s40279-023-01854-9),
[PubMed](https://pubmed.ncbi.nlm.nih.gov/37493929/).

## E03 — fitness–fatigue estimation problems

Marchal et al. (2025), *Statistical flaws of the fitness-fatigue sports performance
prediction model*, Scientific Reports 15:3706. This study examines estimability and
predictive limitations, including antagonistic parameter behavior. It supports
explicit identifiability assessment and held-out comparisons, not the blanket
assertion that every fitness–fatigue model is useless. Indexed article information
and the author preprint were accessible; the publisher full-text page was not
reliably accessible in this session. [Published DOI](https://doi.org/10.1038/s41598-025-88153-7),
[PubMed](https://pubmed.ncbi.nlm.nih.gov/39881202/),
[Author preprint](https://assets-eu.researchsquare.com/files/rs-4827266/v1_covered_32c2122f-0130-4074-9a78-c13f70f6173c.pdf).

## E04 — state-space precedent

Kolossa et al. (2017), *Performance Estimation using the Fitness-Fatigue Model with
Kalman Filter Feedback*, International Journal of Computer Science in Sport
16(2):117–129. The existing application of state-space/Kalman methods to a
fitness–fatigue formulation means that adding a filter is not itself a new research
contribution. Publication metadata/abstract found; a complete detailed equation
comparison still needs the full paper. [DOI](https://doi.org/10.1515/ijcss-2017-0010).

## E05 — closely related VBT preprint

Paul Swinton (2025), *From Discrete Testing to Continuous Monitoring in Strength and
Conditioning: A Kalman Filter Tutorial with Simulated Velocity-Based Training Data*.
SportRxiv preprint, DOI 10.51224/SRXIV.678. Author-uploaded abstract and metadata were
found. Treat this as relevant preliminary prior art, not peer-reviewed efficacy
evidence. The repository must not claim the first VBT/state-space model without
reading and comparing this work. [Preprint DOI](https://doi.org/10.51224/SRXIV.678),
[Author-posted record](https://www.researchgate.net/publication/398612755_From_Discrete_Testing_to_Continuous_Monitoring_in_Strength_and_Conditioning_A_Kalman_Filter_Tutorial_with_Simulated_Velocity-Based_Training_Data).

## E06 — velocity loss

Sánchez-Medina and González-Badillo (2011), *Velocity loss as an indicator of
neuromuscular fatigue during resistance training*. This primary experiment supports
velocity loss as an informative exercise-response measure under its study conditions.
It does not identify three independent fatigue compartments or establish fixed
universal RIR thresholds. [PubMed](https://pubmed.ncbi.nlm.nih.gov/21311352/),
[DOI](https://doi.org/10.1249/MSS.0b013e318213f880).

Jukic et al. (2023), *Velocity loss is a flawed method for monitoring and prescribing
resistance training volume with a free-weight back squat exercise*. A relevant
counterpoint to treating velocity loss as a universal prescriptive quantity; the
exact intended application and protocol matter.
[Publisher](https://link.springer.com/article/10.1007/s00421-023-05155-x).

## E07 — endurance model boundaries

Skiba and Clarke (2021), *The W′ Balance Model: Mathematical and Methodological
Considerations*. CP/W′ modelling has its own equations, units and methodological
conditions. A threshold-relative minute score is not that model.
[DOI](https://doi.org/10.1123/ijspp.2021-0205).

Welburn et al. (online 2025; volume 2026), *W′ reconstitution modelling during
intermittent exercise performed to task failure*. In 13 cyclists, existing recovery
time-constant formulations did not reliably predict exhaustion across the tested
protocols; individualization was important. This cautions against presenting an
unvalidated default W′ recovery constant as athlete-specific truth.
[Full paper](https://link.springer.com/article/10.1007/s00421-025-05912-0).

## E08 — power calculation naming

TrainingPeaks, *Normalized Power, Intensity Factor and Training Stress*. Provider
explanation of the metric and its physiological/time-response motivation.
The repository previously computed a raw fourth-power mean without temporal
smoothing and removed zeros. This audit avoids claiming that result as NP and uses
an explicitly named time-integrated relative-power-squared dose instead.
[Original metric provider](https://www.trainingpeaks.com/learn/articles/normalized-power-intensity-factor-training-stress/).

## Evidence gaps not resolved by citations

No source located establishes the repository's 15% Z2 priming gain, 21-day leg
structural proxy, exact local/systemic/metabolic split, 1.3 running factor, universal
capacity ceilings, 0.35 structural threshold, or fixed near-term personalized
readiness scale. Some may be useful heuristics or candidate features; usefulness
must be tested separately. Absence of a located source is not proof that no
relevant study exists.
