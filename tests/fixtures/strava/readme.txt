Strava Fixture: activities.csv
================================

This fixture contains 8 activities for testing the Strava export adapter.

Expected parsing results:
-------------------------
Total activities: 8

By sport:
- Cycling (Ride): 5 activities (IDs: 1234567890, 1234567891, 1234567894, 1234567896, 1234567897)
- Running (Run): 2 activities (IDs: 1234567892, 1234567895)
- Swimming (Swim): 1 activity (ID: 1234567893)

HIIT detection (based on keywords or power thresholds):
- Interval Training (ID: 1234567891) -> HIIT=True (keyword "Interval")
- Crit Race (ID: 1234567896) -> HIIT=True (keyword "Race")
- All others -> HIIT=False (Z2 by default)

Date range: 2024-01-15 to 2024-01-23

Duration parsing tests:
- 3600 seconds = 60 minutes
- 2700 seconds = 45 minutes
- 7200 seconds = 120 minutes
- etc.

Distance parsing:
- Values in meters, converted to km
- 25000 = 25.0 km
- Missing distance handled gracefully (empty column)

Power/HR:
- Average watts used for intensity detection if > 200W
- HR data included but not used for intensity in V1
