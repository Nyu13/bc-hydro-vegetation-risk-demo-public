# Manager demo walkthrough (~5 minutes)

**Total time:** ~5:00 · **Audience:** managers / sponsors · **App:** Streamlit demo (Overview tab first)

**Framing (repeat as needed):** This is a **proof-of-process** workflow using **public/proxy** data. It supports **review prioritization** and discovery—not outage prediction. Any operational use **requires internal validation** with BC Hydro data and governance.

---

## 1. Opening — 30 sec

**Goal:** Set expectations before clicking around.

**Talking points**

- Today we are showing **how signals could be combined** into a transparent review queue—not **when or where the next outage will occur**.
- The disclaimer on screen is intentional: **illustrative workflow and analytical logic only**; **not for operational decisions**.
- Think of this as a **discovery conversation**: Can we ingest, join, rank, and explain drivers with the data we can access today?
- We are **not** claiming validated BC Hydro outage prediction, production readiness, or official historical outage statistics.

**If asked:** “When will this predict outages?” → **No—it ranks corridors for review using proxies; calibration needs internal data.**

---

## 2. Overview — 45 sec

**Tab:** **Overview** → **Manager summary**

**Goal:** Mirror the in-app “shows / does not show” lists.

**Talking points**

- **What it shows**
  - A **concept workflow**: vegetation + weather + outage-proxy signals → a **review-oriented** dashboard.
  - **Dashboard structure**: summary metrics, ranking, top drivers, map, and a synthetic backtesting view for discussion.
  - **Public/proxy integration**: live BC Hydro public feeds, unofficial archive snapshots, open datasets—not a full internal stack.
  - **Illustrative scoring**: weighted demo score with visible drivers—not a calibrated production model.
- **What it does not show**
  - **Validated outage prediction** or forecast certainty.
  - **Real feeder/circuit topology** from BC Hydro systems.
  - **Internal vegetation treatment / patrol history** (placeholders where Planet is off).
  - **Operational readiness** (control room, GIS assets, crew dispatch, SLAs, model lifecycle).
- Maturity today: **working proof-of-process** with real open/free satellite layers for Surrey; **Planet is optional** to prove the workflow but would strengthen the remote-sensing layer.

**If asked:** “Is this production?” → **No—proof-of-process for prioritization and data discovery.**

---

## 3. Area selection — 45 sec

**Tab:** **Area selection**

**Goal:** Explain geography choice and outage-history limits.

**Talking points**

- **Pilot focus:** **Surrey** (highlighted row)—our PoC municipality in the Lower Mainland.
- **Two outage views**
  - **Historical archive (not live):** unofficial snapshot proxy with date range in the banner—**not BC Hydro–provided**, **not authoritative** for history.
  - **Current outages:** live public JSON/RSS on **Risk Dashboard** / **Risk Map**—reflect **recent visibility**, not a complete archive.
- **Unique outages** in tables = distinct outage IDs in the unofficial archive (**proxy metric**), not official BC Hydro historical reporting.
- Rankings help **compare public/proxy hotspots** for workshop discussion—not certify regional risk.
- Yellow-highlighted rows = **demo/synthetic** where applicable; read provenance badges.

**If asked:** “Is this BC Hydro’s official outage history?” → **No—public feeds plus unofficial archive proxy only.**

---

## 4. Surrey PoC Sample — 90 sec

**Tab:** **Surrey PoC Sample**

**Goal:** Show open/free layers reducing synthetic assumptions; position Planet as the next upgrade.

**Talking points**

- **WorldCover (static land cover):** corridor-level **exposure context**—what land cover types sit near demo transmission segments.
- **Sentinel-2 (NDVI / NDMI):** vegetation **greenness** and **moisture proxies** from open imagery; scene QA and cloud masking are visible—**coastal BC cloud gaps are expected**.
- **ECCC weather stress proxy:** temperature, wind gust, precipitation—**atmospheric stress only**; not soil water, land surface temperature, or canopy stress.
- Together, these **reduce reliance on synthetic vegetation scores** in **Public/proxy** mode—they are **proof-of-process**, suitable for discovery, **not operational decision-making**.
- **What this proves (in-app bullets):** focused corridor AOI, ingest public weather/outage/corridor/satellite data, transparent drivers, baseline before commercial imagery.
- **Planet improvements (when purchased):** higher-resolution canopy structure, more frequent condition updates, commercial SWC/LST, better change detection, clearer licensing for internal/client **proof-of-process** demos.
- **AOI context for procurement:** preferred sample = **Surrey transmission corridor 200 m buffer, ~3,580 ha** (balances exposure, cost, and testable corridor ranking vs. full municipal boundary ~36k ha).

**If asked:** “Can we ship on Sentinel-2 alone?” → **Not for ops—good baseline; Planet (or similar) is the commercial path for decision-grade vegetation stress.**

---

## 5. Risk Dashboard — 60 sec

**Tab:** **Risk Dashboard**

**Goal:** Demonstrate decision-support *style* without overclaiming outcomes.

**Talking points**

- **Ranking table:** demo corridors sorted by illustrative risk score—use for **review prioritization**, not dispatch orders.
- **Top risk drivers** chart: which signal dominated (vegetation exposure proxy, weather stress, public outage density proxy, etc.)—supports **explainability**.
- **Suggested review actions** (example language in app): e.g. “Review corridor exposure before storm window,” “Consider crew/material pre-staging,” “Prioritize patrol if forecast severity increases”—**decision-support examples**, not automated work orders.
- **Storm risk summary** cards: tie weather + outage visibility + data mode badge (Public/proxy vs Planet sample vs synthetic fallback).
- **Live outages section:** Surrey-filtered map JSON when available; empty feed ≠ zero risk—data visibility limitation.
- Close with: **Any change to patrol, staging, or investment still requires internal validation** against BC Hydro systems and subject-matter review.

**If asked:** “Will High always mean an outage?” → **No—High means higher proxy score for discussion in the queue.**

---

## 6. Data Sources & Assumptions — 45 sec

**Tab:** **Data Sources & Assumptions**

**Goal:** Draw the public/proxy vs internal boundary and show layer inventory.

**Talking points**

- **Source catalog:** what each layer is, where it comes from, and demo use (live JSON, unofficial archive, ECCC, WorldCover, Sentinel-2, transmission demo segments, optional Planet sample CSV).
- **Public/proxy vs internal boundary (read verbatim if needed)**
  - Public/proxy → **concept demonstration and proxy-based ranking only**.
  - Internal BC Hydro data → **formal PoC calibration, validation, operational use**.
  - **No production claim** without validated internal data and governance.
- **Assumptions & limitations:** prototype only; incomplete historical archive; unofficial snapshots **not authoritative**; corridor markers are **demo segments**, not distribution feeders; vegetation scores are **proxies** without Planet/LiDAR/patrol records.
- Point to docs linked in-app (`data_sources.md`, open/free pipeline runbooks) for technical follow-up.

**If asked:** “What do we need from BC Hydro?” → **Internal outage history, topology, vegetation treatments, asset condition—listed under internal data boundary.**

---

## 7. Recommended next decision — 30 sec

**Tab:** **Data Sources & Assumptions** → **Planet commercial data (Surrey PoC)** (or end on Overview recommended step)

**Goal:** One clear ask to leave the room with.

**Talking points**

- **Recommended next action:** Request a **Planet quote** for the **Surrey 200 m transmission corridor buffer (~3,580 ha)**—the in-app AOI comparison shows why 200 m is the balanced first purchase vs. 100 m / 300 m / full municipality.
- Sample products in scope: **Forest Carbon Monitoring** (canopy), **SWC**, **LST**, **ARPS / PlanetScope-derived** greenness/dryness and change indicators—summarized by corridor AOI.
- Planet **strengthens the vegetation/environment layer**; it does **not** replace internal outage history, feeder topology, treatment records, or SAIDI/SAIFI.
- Parallel non-commercial path: continue **open/free baseline** (WorldCover + Sentinel-2 + ECCC) while internal data owners confirm **pilot success criteria** and joinability.
- **Decision for this meeting:** Approve **quote request + discovery workshop** (data owners, validation plan)—not production rollout.

**Closing line:** “We have a repeatable proof-of-process; the next gate is **commercial imagery quote** and **internal validation**, not turning the demo dial to ‘prediction.’”

---

## Quick reference — language to use / avoid

| Use | Avoid |
|-----|--------|
| Proof-of-process | Predicts outages |
| Review prioritization | Operational dispatch |
| Public/proxy data | Official BC Hydro historical outage claims |
| Requires internal validation | Production-ready / calibrated model |
| Decision-support examples | Automated decisions |
| Illustrative / proxy scoring | Forecast certainty |

---

## Pre-demo checklist (30 sec before start)

- [ ] Sidebar: **Surrey** region; data mode **Public/proxy only** (unless showing Planet sample intentionally).
- [ ] Note whether live outage JSON returns rows (network/TLS); if empty, mention **demo fallback** toggle without implying zero outages.
- [ ] Open **Overview → Manager summary** as landing tab.
- [ ] Have `docs/planet_surrey_data_request.md` ready if Planet pricing questions go deep.
