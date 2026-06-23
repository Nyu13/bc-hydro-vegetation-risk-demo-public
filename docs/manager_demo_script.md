# Manager demo walkthrough (~5 minutes)

**Total time:** ~5:00 · **Audience:** managers / sponsors · **App:** Streamlit Okanagan demo (Overview tab first)

**Framing (repeat as needed):** This is a **proof-of-process** workflow using **public/proxy** data for **vegetation-wildfire planning** in Okanagan / Kootenay transmission corridors—not outage prediction. Any operational use **requires internal validation** with BC Hydro data and governance.

---

## 1. Opening — 30 sec

**Goal:** Set expectations before clicking around.

**Talking points**

- Today we are showing **how public layers could support corridor planning** in wildfire-relevant terrain—not **when or where the next outage will occur**.
- The disclaimer on screen is intentional: **proof-of-process only**; **not for operational decisions**.
- Think of this as a **discovery conversation**: Can we ingest, join, rank, and explain drivers with the data we can access today?

**If asked:** “When will this predict outages?” → **No—it ranks corridor segments for planning review using proxies.**

---

## 2. Overview — 45 sec

**Tab:** **Overview**

**Goal:** Mirror the in-app “shows / does not show” lists.

**Talking points**

- **What it shows**
  - **Vegetation-wildfire planning workflow** — corridor segments ranked by composite exposure
  - **Public layer stack** — WorldCover, Sentinel-2, CWFIS, ECCC weather stress, outage archive proxy
  - **Treatment gap placeholder** — where BC Hydro work-management data would plug in
  - **Transparent proxy scoring** — component breakdown per segment
- **What it does not show**
  - **Outage prediction** or storm-risk forecasting
  - **Validated wildfire or vegetation treatment prioritization**
  - **Internal GIS, SAIDI/SAIFI, or patrol records**
  - **Operational dispatch** or control-room tooling

**If asked:** “Is this production?” → **No—proof-of-process for planning prioritization and data discovery.**

---

## 3. Kelowna / Okanagan Planning — 2 min

**Tab:** **Kelowna / Okanagan Planning**

**Goal:** Walk through the main map, ranking table, and score breakdown.

**Talking points**

- **Vegetation & satellite context** — WorldCover mean tree cover (~35%) and built-up (~13%); Sentinel-2 NDVI/NDMI; dryness proxy from NDMI (moisture stress, not field soil moisture).
- **Planning map** — pick a **2026 date**; toggle CWFIS **FWI raster**, **fires**, and **archive outages** for that day; BC transmission lines; corridor segments (planning priority vs dated FWI).
- **Segment popups** — click a corridor line for full score breakdown plus satellite fields (NDVI, NDMI, dryness, tree/built cover).
- **Top corridor segments** — ranked table with vegetation dryness, tree/built %, and component scores.
- **Score breakdown + Vegetation drivers** — composite components plus WorldCover composition and Sentinel-2 moisture/greenness charts.

**If asked:** “Does High mean an outage?” → **No—Higher proxy score for planning discussion, not dispatch.**

**If asked:** “Why is dryness 100?” → **NDMI is negative/low in this imagery window; dryness is a proxy from satellite moisture index, not a field measurement. Planet SWC or patrol data would validate.**

---

## 4. Data Sources & Assumptions — 45 sec

**Tab:** **Data Sources & Assumptions**

**Goal:** Draw the public/proxy vs internal boundary.

**Talking points**

- **Layer inventory** — Okanagan pipeline artifacts and load status.
- **BC Hydro replacement table** — internal data needed for validation.
- **Assumptions** — unofficial outage archive proxy, ECCC weather near Kelowna, synthetic treatment gap, public transmission geometry (not distribution feeders).

**If asked:** “What do we need from BC Hydro?” → **Internal outage history, topology, vegetation treatments, asset condition—listed in the replacement table.**

---

## 5. Recommended next decision — 30 sec

**Goal:** One clear ask to leave the room with.

**Talking points**

- **Recommended next action:** Review top corridor segments with BC Hydro stakeholders; confirm data owners and success criteria for a formal PoC.
- Run `python TMP/scripts/build_okanagan_demo_pipeline.py` if any layers show as missing.
- **Decision for this meeting:** Approve **discovery workshop** (data owners, validation plan)—not production rollout.

**Closing line:** “We have a repeatable proof-of-process for Okanagan corridor planning; the next gate is **internal validation**, not turning the demo into prediction.”

---

## Pre-demo checklist (30 sec before start)

- [ ] Sidebar: **Light** or **Dark** theme as preferred.
- [ ] Open **Overview** as landing tab.
- [ ] Confirm Okanagan pipeline artifacts exist (Planning tab loads without “run pipeline” warning).
