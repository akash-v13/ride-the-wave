# config/calendars

Dates that strategies and studies need and that are public record.

- `fomc_scheduled.csv`: every scheduled Federal Reserve (FOMC) announcement date from 1994, with the
  meetings already announced for the coming year. Built from the Fed's own pages by
  `scripts/build_fomc_dates.py`; what is kept and why is in `src/ridethewave/data/fomc.py`.
  Conference calls, unscheduled meetings and cancelled meetings are left out. Rebuild once a year.
