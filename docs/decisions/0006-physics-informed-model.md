# 0006. A physics-informed regression, not a generic ML model

**Status:** Accepted, November 2026 (climb and regeneration terms added 8 November 2026; air conditioning and a
time-based load added 9 November 2026, after slow, hot conditions predicted impossible ranges)

## Context

The question is how consumption, and so range, depends on speed, temperature, wind and hills. A personal car
produces tens of usable drives a month, not millions, and the interesting predictions are exactly the
conditions not seen yet (the first frost, a motorway trip into a storm).

## Decision

A linear model in physically derived features, fitted per car:

```
kWh/100 km = c0                                            rolling resistance, drivetrain
           + c_aero  · (v + headwind)² · ρ(T)/ρ15        air drag on airspeed, denser when cold
           + c_heat  · max(0, 18 − T) / v                 heating power × time per km
           + c_cool  · max(0, T − 24) / v                 air conditioning × time per km
           + c_time  / v                                  electronics and stop-and-go losses × time per km
           + c_climb · metres climbed per 100 km
           − c_regen · metres descended per 100 km
```

- Distance-weighted least squares (longer drives are measured better).
- **Every coefficient non-negative**, the intercept included: cold never saves energy. Exact, by fitting every
  subset of free coefficients and keeping the best feasible one. A descent may not return more than the same
  climb costs (`c_regen ≤ c_climb`).
- At least 15 drives of 5 km or more with weather before a fit is attempted.

## Consequences

- Works with little data, extrapolates in physically sensible ways and explains itself in plain units
  ("a 20 km/h headwind at 60 km/h adds 2.4 kWh/100 km").
- Each coefficient has a value the car's specifications predict, which enables the prior in
  [0007](0007-specs-prior-and-backtest.md).
- It cannot learn effects that are not in the formula (traffic, driving style, pre-conditioning while
  plugged in). Those show up as residuals; a learner on the residuals is planned once there are enough drives
  (see the roadmap), and must beat the physics model in the same backtest to be kept.

## Alternatives considered

- **Gradient boosting / random forest on raw features:** needs far more data, extrapolates flat outside the
  training range (the first frost would look like the coldest drive so far) and cannot explain itself.
- **A neural network or an LLM:** same problems, larger; an LLM is a language model, not a regression engine.
- **Fixed specs only:** no learning from the actual car, tyres and driver; kept as a reference and prior.
