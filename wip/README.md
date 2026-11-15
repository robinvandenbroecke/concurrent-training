# Onaf werk voor fase 3 tot 6

Deze map bevatte zestien bestanden die in de aangeleverde ZIP van 13 november 2026 zaten maar niet in commit `8bcc3e2` staan. Ze zijn afkomstig van een afgebroken eerdere uitvoering van de auditopdracht. Ze staan hier met hun oorspronkelijke pad onder `phase3-6/`, zodat er niets verloren is.

Ze horen bewust niet bij de build. De TypeScript-bestanden verwijzen naar types en velden die nog niet bestaan (`ProgramSettings`, `velocityMeta`, `startTime`, `powerSummary`, `pattern`, `needs`), de Python-bestanden naar instellingen en modellen die ontbreken (`settings.supabase_url`, `models.ProviderConnection`) en naar pakketten die niet in `requirements.txt` staan (`PyJWT`, `fitdecode`, `defusedxml`). Teruggezet op hun plaats breken ze `npm run build`, `pytest` en de `/ready`-controle.

Op 14 november 2026 zijn de engine-API, de tokencontrole, de engineclient en de kaart nagekeken, afgewerkt en naar de build verplaatst (`app/api_v3.py`, `app/auth_supabase.py`, `webapp/src/engine/`, `webapp/src/components/EngineCard.tsx`). Later die dag is ook de programmagenerator nagekeken, herwerkt en verplaatst (`webapp/src/domain/generator.ts`). Wat hier nog staat is niet beoordeeld. Behandel het als een ruwe aanzet:

| Pad | Bedoeld voor |
|---|---|
| `webapp/src/data/labels.ts` | Weergavenamen (niet nodig gebleken) |
| `app/integrations/providers.py`, `alembic/versions/007_provider_connections.py` | Garmin/Wahoo-koppeling (fase 5) |
| `app/science/activity_files.py` | Import van FIT, TCX en GPX (fase 5) |
| `webapp/src/trainer/` | Workouts, speler, FTMS-sturing en export (fase 6) |
| `tests/` | Tests bij de providers, de bestandsimport en de migratie |

Migratie 007 mag pas terug naar `alembic/versions/` samen met de modellen en na review: de gehoste app voert bij elke start `alembic upgrade head` uit.
