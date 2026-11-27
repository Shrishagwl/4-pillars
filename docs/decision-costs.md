# The cost of each decision (task #8)

The engine picks the action with the lowest expected cost (`services/engine/src/engine/decision.py`).
These are the dollar values it uses, where each one comes from, and the working. The dashboard
uses the same numbers (`apps/dashboard/src/utils/costs.ts`). Change both together.

All values are in Australian dollars, excluding GST, at 2026 prices. Researched 28 Nov 2026.

## The numbers

| Cost | Was | Now | Working | Source |
|---|---|---|---|---|
| `truck_roll`: one technician visit | $300 | **$650** | Jemena's regulated fee for a site visit where no work gets done ("wasted site attendance", business hours) is $654.21. A visit to the wrong place is exactly that. | [Jemena 2026-27 schedule of services](https://www.jemena.com.au/contentassets/a440c960e37a4eca8497cf44990ebe0b/jen-2026-27-schedule-of-services---alternative-control-and-public-lighting.pdf) |
| `power_crew`: one power crew call-out | $800 | **$1,200** | 2 field workers for 2 hours. Jemena's field worker rate is $222.20/h in business hours and $388.22/h after hours. Outages happen at any time, so we use the average ($305/h). 2 x 2 x $305 = $1,221. | same |
| `late_power_per_meter`: a power cut we did not act on, per customer | $10 | **$28** | The AER's value of customer reliability for suburban Melbourne (climate zone 6) is $55.10 per kWh of lost supply. We assume an average home draws 0.5 kW (**guess**) and that missing the cut delays the fix by 1 hour (**guess**). $55.10 x 0.5 x 1 = $27.55. | [AER 2024 VCR fact sheet](https://aer.gov.au/system/files/2024-12/2024-12-18%20AER%20-%20Fact%20sheet%20-%202024%20VCR%20review.pdf) |
| `meter_left_broken`: a faulty meter nobody was sent to | $100 | **$125** | Until it is fixed, the meter has to be read by hand. Jemena's field special read costs $62.02. We assume two reads (**guess**). | Jemena schedule (above) |
| `missed_tamper`: tampering nobody investigated | $500 | **$600** | Power used but not paid for. About 6 months of an average home's power at Victorian retail prices (**guess**, no public figure for Victoria). | none |
| `manual_review`: an operator checks one incident | $8 | **$20** | 10 minutes at Jemena's administrative officer rate ($117.90/h). | Jemena schedule (above) |
| `review_delay_share` | 0.1 | 0.1 | Unchanged **guess**: a review delays the real fix by 10% of the cost of doing nothing. | none |

## Why not Victoria's guaranteed service level payments?

The task asked us to check them. In Victoria, distributors pay customers when service falls
below set levels. For unplanned outages, the payments start at $130 for more than 18 hours off
supply in a year, and go up to $380 for more than 60 hours or 20 interruptions.

A single outage noticed a little late almost never pushes a customer over those yearly
thresholds, so a per-incident cost would be close to zero. The AER's value of customer
reliability is the better measure of what a late response costs. GSL payments are still worth
mentioning in the write-up as the regulator's own price on long outages.

Sources: [Essential Services Commission, GSL payments](https://www.esc.vic.gov.au/electricity-and-gas/information-for-electricity-and-gas-consumers/guaranteed-service-level-payments-energy-outages-and-voltage-claims), [Jemena GSL summary](https://jemena.com.au/link/c5875c880c3d4c9abe06ac043b749122.aspx).

## What changed in the engine's decisions

Real costs make a visit more expensive compared with doing nothing, so the engine is now more
careful about sending people out:

- **One quiet meter:** at the rules' usual confidence (about 75% meter fault), waiting is now
  cheaper on average than a technician visit ($150 against $165). The engine waits instead of
  sending someone. Single meters often come back by themselves, so this is reasonable, but the
  engine owner should confirm it. One pipeline test was updated to match.
- **Big network outages:** a 415-meter network outage needs the chance of a power cut to be
  below about 9% before holding crews beats sending one. Below that, the engine waits for
  Telstra; above it, it sends a crew just in case. This is the cost model doing its job and is
  a good point for the write-up.
- **Confident verdicts are unchanged:** at 90% confidence every cause still gets its matching
  action (new test `test_real_costs_still_pick_the_matching_action_when_confident`).

## Loading different costs

The engine can read costs from a JSON file without code changes, for example
`{"truck_roll": 700, "power_crew": 1500}`, through `load_costs()` in `decision.py`. Any cost
not in the file keeps the default above.
