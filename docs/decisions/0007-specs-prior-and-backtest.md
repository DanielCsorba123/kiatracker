# 0007. Car-spec prior, ridge pull chosen by a time-ordered backtest

**Status:** Accepted, November 2026

## Context

With 15 to 30 drives, a free fit chases noise: one cold, slow, uphill trip can move the heating coefficient
anywhere. The car's data sheet already says roughly what each coefficient should be. The owner also asked for
the car's wind resistance to be part of the baseline.

## Decision

- **Specs model** (`forecast/specs.py`): coefficients computed from the EV3's specifications: mass 1,950 kg,
  drag coefficient 0.265, frontal area 2.45 m², rolling resistance 0.009, drivetrain efficiency 0.90,
  auxiliaries 0.4 kW, heating 0.15 kW per °C below 18 °C, 60 % of descent energy regenerated. That gives about
  c0 = 6.0 kWh/100 km, c_aero = 0.00095, c_heat = 15, c_climb = 0.0059 kWh/m, c_regen = 0.0032 kWh/m, and about
  17.5 kWh/100 km at 110 km/h in still, mild air.
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
