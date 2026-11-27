# Realistic twin settings (task #3)

Research for the digital twin's calibration task (#23). For each setting: what the twin uses
now, what we found, where it came from, and what we suggest. Anything without a public source
is marked **guess**. Researched 28 Nov 2026.

## Summary

| Setting | Twin now | Realistic value | Source | Suggestion |
|---|---|---|---|---|
| Meter reporting interval | heartbeat every 15 min | records every 30 min (newer meters every 5 min), sends to the distributor once a day | [Energy Vic](https://www.energy.vic.gov.au/electricity/smart-meters), [AusNet](https://www.ausnetservices.com.au/electricity/your-electricity-meter/smart-meters) | Keep 15 min as the twin's "alive" tick. Note in the write-up that meter data itself only arrives daily, which is why the SIM dropping off the network is the fast signal. |
| Last-gasp support | 70% of meters send code 6 when power goes | Victorian distributors already use smart meter last gasps to tell customers about outages. No public figure for how many get through. | [CitiPower metering business case](https://aer.gov.au/system/files/2025-02/CP%20BUS%2011.01%20-%20Metering%20-%20Jan2025%20-%20Public.pdf) | Keep 70% (**guess**). |
| Meters per transformer | 50 to 150 | Jemena's pole transformers each supply between 1 and 370 customers. One of Jemena's urban feeders has 48 transformers for 3,181 customers, about 66 each. | [Jemena transformer business case](https://www.aer.gov.au/system/files/2025-12/JEN%20-%20RP%20-%20Support%20-%20Distribution%20Transformer%20Replacement%20-%20Business%20Case%20-%20December%202025%20-%20Public.pdf), [Victorian synthetic network study](https://imoveaustralia.com/wp-content/uploads/2026/08/Victoria-whole-distribution-network-architecture-via-synthetic-models.pdf) | Keep 50 to 150. It sits in the real range and gives clusters big enough to see. |
| Power outage length | restored after 60 to 120 min | In 2025 the average customer had about 1 unplanned interruption and 129 minutes off supply (national, outliers removed), so a typical outage is about 2 hours. | [AER network performance report 2026](https://www.aer.gov.au/system/files/2026-07/Electricity%20infographic%20-%20Network%20performance%20report%202026.pdf) | Widen to 60 to 180 min. |
| Code 7 detection delay | 2 to 4 min after the meter goes quiet | Depends on Telstra's setup. In the 3GPP standard, the LoC "maximum detection time" sets the SIM's periodic check-in timer, and the LTE default for that timer is 54 minutes. | [3GPP TS 24.301 timer table](https://3gpp.org/FTP/tsg_ct/WG1_mm-cc-sm_ex-CN1/TSGC1_135e/Inbox/draft-rev-C1-222791.docx) | **Open question, see below.** Keep 2 to 4 min for now. |
| Outage API delay | Telstra lists the outage 10 to 30 min after it starts | Telstra describes its IoT Outage API as near real time. No published delay. | [Telstra](https://www.telstra.com.au/business-enterprise/news-research/articles/helping-turn-network-visibility-into-operational-advantage) | Keep 10 to 30 min (**guess**). Measure it once we have sandbox access. |
| Network outage size | 60 to 90% of a suburb's meters | No public figure. | none | Keep (**guess**). |

## Open question: how long until a silent SIM is reported?

This matters more than any other setting. A meter that loses power usually sends a last gasp
(code 6) straight away. A meter that just goes quiet (network outage, dead meter) is only
reported as code 7 when the network's detection timer runs out.

Under the 3GPP standard, that timer comes from the "maximum detection time" in the LoC
subscription. If Telstra uses the LTE default, a code 7 could arrive up to about an hour
after the meter went quiet. That would break the engine's 15-minute clustering window and
make network outages look like a slow trickle.

What to do:

1. Ask Telstra (or the hackathon mentors) what maximum detection time the LoC subscription
   uses, and whether we can set it.
2. Measure it in the eSIM task: switch the eSIM phone off with and without a "clean" detach, and
   time how long until each callback arrives.
3. Update `detection_delay_s` in the twin and the engine's clustering window to match.

## Sources

- Energy Victoria, Smart meters: https://www.energy.vic.gov.au/electricity/smart-meters
- AusNet Services, Smart meters: https://www.ausnetservices.com.au/electricity/your-electricity-meter/smart-meters
- CitiPower, Metering business case 2026-31 (AER): https://aer.gov.au/system/files/2025-02/CP%20BUS%2011.01%20-%20Metering%20-%20Jan2025%20-%20Public.pdf
- Jemena, Distribution transformer replacement business case (AER, Dec 2025): https://www.aer.gov.au/system/files/2025-12/JEN%20-%20RP%20-%20Support%20-%20Distribution%20Transformer%20Replacement%20-%20Business%20Case%20-%20December%202025%20-%20Public.pdf
- Victoria whole distribution network architecture via synthetic models: https://imoveaustralia.com/wp-content/uploads/2026/08/Victoria-whole-distribution-network-architecture-via-synthetic-models.pdf
- AER, Network performance report 2026 infographic: https://www.aer.gov.au/system/files/2026-07/Electricity%20infographic%20-%20Network%20performance%20report%202026.pdf
- 3GPP CT1, EPS mobility management timers (T3412 default 54 min): https://3gpp.org/FTP/tsg_ct/WG1_mm-cc-sm_ex-CN1/TSGC1_135e/Inbox/draft-rev-C1-222791.docx
- Telstra, Turning network intelligence into action: https://www.telstra.com.au/business-enterprise/news-research/articles/helping-turn-network-visibility-into-operational-advantage
