# Accounts en trainingsopslag

Status: 6 november 2026. De React-webapp gebruikt de aparte Supabase-omgeving `dvwbkbohdgfuzjenrete` voor login en gebruikersdata. De Python-beheer-API blijft apart in schema `ct_backend`; de frontend krijgt geen beheersleutel en dit werk koppelt geen fysiologisch model.

## Gebruikersgedrag

- Login met e-mailadres en wachtwoord, registratie met e-mailbevestiging, uitloggen op dit toestel, wachtwoordherstel en wijzigen van wachtwoord.
- Trainingen, profiel, weekwijzigingen, volumedoelen en de bevestigde sets in de open krachttraining worden per account opgeslagen. Onbevestigde invoervelden en een nog niet bewaard duurformulier worden niet als draft bewaard.
- De app meldt pas serveropslag na bevestiging door de database. Bij verbindingsproblemen blijft de invoer in de cache van dit account, met een expliciete fout/pending-status. Een volgende poging gebruikt dezelfde sessie-ID en dezelfde afgeronde invoer. Wissen van browsergegevens voordat de database opslag heeft bevestigd kan deze lokale invoer alsnog verwijderen.
- Op een tweede toestel: met hetzelfde account inloggen. Bij een reeds geopende app: **Account → Opslaan en vernieuwen**. Er is geen realtime-update van een open scherm op een ander toestel.
- Gelijktijdige profiel-/planningswijzigingen gebruiken een revisiecontrole. Een verouderde versie overschrijft de database niet. De gebruiker kan de lokale kopie exporteren en expliciet de databaseversie kiezen; er blijft een downloadbare lokale herstelkopie.
- Bij de eerste login op een bestaande origin kan de gebruiker eerdere lokale gegevens expliciet overnemen. De bron blijft intact. Een ander account neemt die gegevens niet automatisch over. Voor een andere origin, bijvoorbeeld van Pages naar Render: exporteer de oude gegevens en importeer ze onder Historie.
- JSON-import voegt sessies zonder dubbele IDs toe en behoudt het huidige profiel. Export bevat zowel bevestigde als lokaal wachtende sessies, planning, profiel en draft. Behandel exports als persoonlijke gegevens.

## Database en toegangscontrole

De migratie staat onder `supabase/migrations/`. De versie komt overeen met de toegepaste Supabase-migratiegeschiedenis.

| Tabel | Inhoud | Toegang |
| --- | --- | --- |
| `public.ct_training_accounts` | JSON-profiel, planning, volumedoelen, open training; database-revisie | Eigen rij lezen, aanmaken en wijzigen |
| `public.ct_training_sessions` | Eén JSON-record per afgeronde kracht-/duursessie, inclusief echte repmetingen, RPE en opmerkingen | Eigen rijen lezen en toevoegen; afgeronde records zijn onveranderlijk |

Beide tabellen verwijzen naar `auth.users` en hebben RLS. `anon` heeft geen tabelrechten. `authenticated` krijgt alleen de vereiste rechten en een eigendomsvoorwaarde `(select auth.uid()) = user_id`; account-UPDATE heeft ook `WITH CHECK`. Een gefingeerde `user_id` geeft dus geen toegang. Sessie-identiteit is de samengestelde sleutel `(user_id, id)`. Herhaalde inserts gebruiken `ON CONFLICT DO NOTHING` en lezen de bestaande bevestigde rij terug. De client controleert dat de inhoud bij dezelfde sessie hoort.

Een trigger beheert revisie en wijzigingsdatum van de accountstatus. De frontend gebruikt een conditionele UPDATE op de vorige revisie. De trigger is `SECURITY INVOKER` met een vaste lege zoekroute. Er zijn geen publiek uitvoerbare functies met verhoogde rechten. De JSON-tabellen zijn een duurzaam frontendcontract, geen vervanging van de bestaande tabellen of een gevalideerde invoer naar de rekenmotor.

Supabase bewaart wachtwoordhashes en beheert tokens. De webapp bevat uitsluitend de publiceerbare projectsleutel. Tokens blijven in de accountopslag van de browser. Gebruik uitloggen op gedeelde toestellen; de lokale herstelcache is geen versleutelde gegevenskluis. Een gestolen access token kan volgens het normale Supabase-model geldig blijven tot zijn vervaltijd; uitloggen is geen onmiddellijke intrekking van elke al uitgegeven JWT.

## E-mail en uitrol

De Site URL is `https://concurrent-training.onrender.com/concurrent-training/`. De exacte Pages-URL is toegevoegd als toegelaten redirect, zonder wildcards. E-mailbevestiging blijft aan; anonieme login is uitgeschakeld. De registratiepagina vraagt minimaal acht tekens.

**Nog vereist voor publieke registratie:** eigen SMTP instellen. In het dashboard staat custom SMTP uit. Supabase's standaard e-maildienst is beperkt tot toegelaten/teamadressen en een lage verzendlimiet. Login met een bestaand bevestigd account werkt; registratie en wachtwoordherstel voor willekeurige bezoekers zijn hiermee nog geen volwaardige productievoorziening. Er zijn geen e-mails namens de eigenaar verstuurd en er is geen persoonlijk gebruikerswachtwoord aangemaakt.

Gratis hosting houdt de eerder beschreven slaap-, pauze- en back-upbeperkingen. Voordat waardevolle cloudgegevens worden verzameld, moeten back-ups en herstel worden ingericht. Garmin/Wahoo/Strava-import, Android-integratie en wetenschappelijke validatie worden door deze wijziging niet geactiveerd.

## Verificatie

- 43 frontendtests en TypeScript/Vite-productiebuild geslaagd. Nieuwe controles omvatten loginfouten, registratie-/herstelgedrag, uitloggen en wisselen van account, herstel op een tweede toestel, verbindingsverlies, verloren HTTP-bevestiging, dubbele sessies, behoud van ontbrekende VBT-metingen, revisieconflicten en expliciete lokale migratie.
- `supabase/tests/ownership.sql` is uitgevoerd tegen de echte Supabase-database: eigen lees-/schrijfrechten, geen toegang als andere gebruiker of `anon`, geen overdracht van eigendom, geen UPDATE van afgeronde sessies en geen verouderde UPDATE. Alle fixtures binnen deze SQL-test worden teruggedraaid.
- Afzonderlijke echte Auth/Data API-controle met twee willekeurige testaccounts: wachtwoordlogin, onjuist wachtwoord geweigerd, sessies opslaan/teruglezen na een nieuwe login, ontbrekende VBT-samples, duurvermogen, idempotente retry, RLS en tokenvernieuwing/uitloggen. De twee testaccounts zijn na de controle geblokkeerd; ze bevatten uitsluitend herkenbare testgegevens.
- PostgreSQL-CI voert dezelfde ownership-test uit met een minimale `auth.uid()`-stub. Dit vervangt de echte Supabase-controle niet.
- Supabase security advisors melden geen nieuwe problemen op de gebruikerstabellen. De bestaande INFO-meldingen over RLS zonder policies op `ct_backend` zijn daar bewust: de browserrollen hebben geen schematoegang.
- `npm audit --omit=dev`: geen gemelde kwetsbaarheden op 6 november 2026. Dit is een momentopname.

Bronnen: [Supabase password auth](https://supabase.com/docs/guides/auth/passwords), [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security), [SMTP](https://supabase.com/docs/guides/auth/auth-smtp), [redirects](https://supabase.com/docs/guides/auth/redirect-urls). Actuele documentatie en changelog zijn bij implementatie gecontroleerd.
