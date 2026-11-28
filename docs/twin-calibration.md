# Twin calibration (#23)

What the digital twin uses for each setting, where the number comes from, and how sure we are.
Builds on the research in [twin-settings.md](twin-settings.md). Checked 28 Nov 2026.
`services/twin/tests/test_calibration.py` fails if the twin drifts from this table.

**Sourced** means we read it on the page linked. **Estimate** means we couldn't find a public
figure; the reason and the range we picked are given instead. We use ranges, not single
numbers, where we're unsure.

| Setting | Twin value | Status | Basis |
|---|---|---|---|
| Reason codes by network | ~90% of SIMs give 4G codes (0 last gasp, 2 timeout), ~10% 5G codes (6, 7), none 3G (1, 3, 5) | Sourced codes, estimated split | Telstra's LoC docs list the codes by core: MME (4G), SGSN (2G/3G), AMF (5G) [1]. Telstra switched 3G off from 28 Oct 2024 [2], so no SGSN codes. Telstra IoT SIMs run on its 4G network incl. Cat-M1 and NB-IoT [3]. The 90/10 split is an estimate: no public figure for how many meter SIMs are on 5G standalone. |
| Last-gasp share in a power cut | 70% send a "detached" code, the rest time out | Estimate | Victorian distributors already use smart meter last gasps for outages (see twin-settings.md), but nobody publishes what share gets through. 70% sits between "most" and "all"; the engine is also tested from 0% to 100% in the sensitivity sweep. |
| Detection delay (timeout codes) | 2 to 4 min after a meter goes quiet | Estimate | Set by the "maximum detection time" in the LoC subscription [1]. Telstra doesn't publish its value; the 3GPP default timer is much longer (see twin-settings.md). This is the setting we're least sure of, so the sensitivity sweep covers it. To be measured with the eSIM (#17). |
| Meter reporting interval | "alive" heartbeat every 15 min | Sourced interval, twin choice | Victorian smart meters record usage every 30 minutes [4]. The twin's 15-minute heartbeat is just its internal "still alive" tick; the fast signal is the SIM dropping off the network, not meter data. |
| Meters per transformer | 50 to 150 | Estimate (in a published range) | Distributor business cases describe pole transformers supplying from 1 to a few hundred customers (see twin-settings.md). We keep 50-150 so a transformer fault is big enough to show a pattern. |
| Power outage length | restored 60 to 180 min after it starts | Estimate | The AER reports average minutes off supply every year [5]. We couldn't re-read the exact 2025 figure (the PDF wouldn't render here), so we use a 1-3 hour range rather than one number. The engine decides in the first minutes, so this mostly affects how long incidents stay open. |
| Network outage size | 60-90% of a suburb's meters | Estimate | No public figure. Partial coverage loss is the realistic case (neighbouring cells pick some SIMs up). |
| Outage API delay | Telstra lists an outage 10-30 min after it starts | Estimate | Telstra describes the API as near real time but publishes no delay. To be measured with sandbox access (#36). |
| Background dropouts | 2 per hour across the twin (0-60 in the sweep) | Estimate | No public figure for how often healthy meter SIMs briefly drop off. The sensitivity sweep runs 0-60/hour. |

## What changed in the twin

- Reason codes now follow the SIM's core network: mostly 4G (MME) codes, about 1 in 10 SIMs on
  5G (AMF) codes, never 3G (SGSN). Before, every report used the 5G codes 6 and 7. The engine
  groups codes the same way (0/1/6 detached, 2/3/7 timeout), so its verdicts don't change.
- Power cuts in `power-outage.yaml` are restored after 60-180 min (was 60-120), and the run is
  6 hours long so the longest repair fits.

## Sources

1. Telstra, IoT Loss of Connectivity API, Getting Started (lossOfConnectReason values):
   https://dev.telstra.com/apis/iot-loss-of-connectivity-api (read 28 Nov 2026)
2. Telstra, 3G service closure ("From 28 October 2024, the 3G network was switched off"):
   https://www.telstra.com.au/business-enterprise/support/3g-service-closure
3. Telstra, Internet of Things data SIM plans ("including 4G Cat-M1 and NB-IoT"):
   https://www.telstra.com.au/small-business/internet-of-things
4. Energy Victoria, Smart meters ("records electricity usage every 30 minutes"):
   https://www.energy.vic.gov.au/households/save-energy-and-money/smart-meters
5. AER, 2026 Electricity and gas networks performance report:
   https://www.aer.gov.au/publications/reports/performance/2026-electricity-and-gas-networks-performance-report
