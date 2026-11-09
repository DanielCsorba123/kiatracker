# 0007. Car-spec prior, ridge pull chosen by a time-ordered backtest

**Status:** Accepted, November 2026

## Context

With 15 to 30 drives, a free fit chases noise: one cold, slow, uphill trip can move the heating coefficient
anywhere. The car's data sheet already says roughly what each coefficient should be. The owner also asked for
the car's wind resistance to be part of the baseline.

## Decision

- **Specs model** (`forecast/specs.py`): drag (Cd 0.265, frontal area 2.45 m²), climbing and regeneration
  (1,950 kg, 60 % back) from the data sheet; the rolling base, time-based load, heating and cold penalty
  calibrated so that the model reproduces EV Database's real-world consumption for the EV3 Long Range in
  town and at 110 km/h, in mild and cold weather (11.6, 17.5, 18.6, 24.0 kWh/100 km). Pure data-sheet physics
  (the first version) predicted 900+ km in slow, warm driving; anchoring to measurements fixed that.
- **Best-case cap:** no flat-road prediction beats the best measured case (mild city, 672 km on the usable
  78 kWh). It holds for the fitted model too, so noisy early data can't promise an impossible range.
- **Ridge pull toward the specs:** the fit adds one pseudo-observation per coefficient, worth `strength`
  average drives, saying "this coefficient equals the specs". The strength is chosen from
  (0, 1, 3, 10, 30, 100) by the backtest. A coefficient the drives say nothing about (an input that never
  varies, such as climb without terrain data) keeps the specs value.
- **Evaluation:** a time-ordered, expanding-window backtest (5 folds; train only on earlier drives) scores the
  fitted model against three references: the mean of past drives, a straight line in temperature, and the
  specs model with nothing learned.
- **Which model the app uses:** the fitted one only if its backtest error beats both the mean and the specs;
  otherwise the specs model.
- **Intervals:** the 10th–90th percentile of the fitted model's out-of-sample errors.

## Consequences

- Sensible predictions from day one; the data takes over as it grows, without a hand-tuned switch.
- The baselines are deliberately simple, so the comparison is honest and part of what the project shows.
- With very few drives the backtest has no folds, and the strongest pull is used.

## Alternatives considered

- **Keep only the dumb baselines** (the first design): honest, but wastes what the data sheet knows.
- **Replace the baselines with the specs model:** would hide whether learning helps at all; the specs model
  became an additional reference instead.
- **Full Bayesian model:** the ridge pull is its point-estimate equivalent for a Gaussian prior, without the
  extra machinery.
