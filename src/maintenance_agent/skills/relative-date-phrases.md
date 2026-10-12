---
name: relative-date-phrases
description: How to turn vague Spanish/English date phrases ("mañana temprano", "inicio de la semana próxima", "fin de semana", "por la tarde") into date_from/date_to and part_of_day. Read it when the phrase names a part of a week or a part of a day.
---

Call `resolve_relative_range` for the period (today, tomorrow, this_week, next_week, weekend). It
returns the whole period with each day and weekday; you narrow it using the rules below.

Position inside a week (Monday-first):
- inicio / principio / start of the week: Monday and Tuesday.
- mitad / mediados / middle: Wednesday (Wednesday and Thursday if the message says "mid-week").
- final / fin de la semana laboral / end of the week: Thursday and Friday.
- "fin de semana" / weekend: Saturday and Sunday (use kind `weekend`).
- no position named: the whole period.

Part of the day (set part_of_day; the system filters slots with fixed rules):
- temprano, por la mañana, morning: morning (slots that end by 12:00).
- por la tarde, afternoon: afternoon (slots starting from 12:00).
- por la noche, evening: evening (slots starting from 18:00).
- "temprano" with no other cue means morning.

Never guess a single date for a range; set date_from and date_to to the first and last day kept.
These choices are suggestions shown to the tenant, never availability evidence, so when a phrase
is close to a rule above, apply the rule instead of asking.
