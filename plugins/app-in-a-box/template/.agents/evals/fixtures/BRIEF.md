# Streak Club: product brief

**One-liner:** A daily check-in app that helps busy adults keep a small habit going.
**Target user:** Adults with a habit they keep dropping. **Problem (their words):** "I do great for a week, then miss one day and give up."

## Core loop
- Trigger: a 7pm reminder.
- Action: tap "Done today" on the habit.
- Feedback: the streak counter ticks up with a small celebration.
- Return reason: not wanting to break the streak.

## Screens (v1)
Onboarding (pick one habit) · Today (one big check-in button + streak) · History (calendar of check-ins) · Settings (reminder time, account).

## Data model (v1)
- `habits`: id, user_id, name, reminder_time, created_at
- `check_ins`: id, user_id, habit_id, day, created_at (unique per habit per day)
Every table has `user_id` and RLS.

## North-star metric + the 5 analytics events that measure it
North star: weekly active check-in users (checked in on 4+ days in the last 7).
Events: `onboarding_completed`, `habit_created`, `check_in_completed`, `streak_milestone_reached`, `reminder_opened`.

## Out of scope for v1
Social features, multiple habits, paid plans.

## Open questions
Whether a missed day should get one "freeze" per week.
