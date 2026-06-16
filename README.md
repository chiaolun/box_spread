# SPX Box-Spread Funding-Squeeze Report

**Live report: https://chiaolun.github.io/box_spread/**

Generates `index.html` — a single-page report that measures the
implied financing rate embedded in SPX options (via box spreads) and frames a
trade to **capture** it by lending into the equity-funding squeeze.

The report is built from live-ish public data:

| Input | Source |
|---|---|
| SPX option chain (bid/ask/OI per strike) | CBOE delayed quotes — `https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json` |
| Treasury par yield curve (benchmark) | U.S. Treasury daily CSV — `home.treasury.gov` |
| SOFR (secured-funding benchmark) | `sofrrate.com` (manual, one number) |

> The numbers in the committed HTML are a snapshot from **15 Jun 2026**
> (SPX 7,554.29). Re-running the steps below on another day reproduces the same
> report with current prices.

---

## Requirements

- `python3` (standard library only — no pip installs)
- `curl`
- A web browser to view the output

---

## How a box spread reveals the financing rate

A **long box spread** = a bull call spread + a bear put spread on the same two
strikes (`K_lo`, `K_hi`) and expiry. Its payoff at expiration is **fixed at the
strike width**, no matter where the index settles:

```
Long box = [buy call K_lo, sell call K_hi] + [buy put K_hi, sell put K_lo]
Cost today = (K_hi - K_lo) * e^(-r*T)      <- the spot price S cancels out
```

Because the index level cancels, the only thing the price reveals is `r`, the
implied financing rate. Buying the box for less than the width and collecting
the full width at expiry means **you are lending at `r`**. When leveraged longs
bid up equity financing, boxes trade cheap and `r` rises above Treasuries — that
gap is what the report quantifies.

Annualized implied yield (money-market convention):

```
y = (width / box_cost - 1) / T
```

---

## Step 1 — Pull the SPX option chain from CBOE

```bash
curl -s -A "Mozilla/5.0" \
  "https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json" \
  -o spx_raw.json
```

This is a ~13 MB JSON. Each entry is an OCC-symboled option, e.g.
`SPX261218C00700000` = SPX, expiry **26-12-18**, **C**all, strike **7000.000**,
with `bid` / `ask` / `open_interest` / `volume` fields. The underlying spot is
`data.current_price`.

## Step 2 — Pull the Treasury par yield curve

```bash
curl -s -A "Mozilla/5.0" \
  "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv" \
  -o ust2026.csv
```

The CSV is newest-first; the top data row is the latest date. Columns of
interest: `6 Mo`, `1 Yr`, `2 Yr`, `3 Yr`. Look up the current **SOFR** manually
(e.g. sofrrate.com) — it's a single number used only for the SOFR-spread column.

## Step 3 — Compute the box-spread yields

Run the script below. It parses the chain, builds the box for the chosen strikes
across several expiries, and prints the implied yield and spreads over the
matched Treasury and SOFR.

```bash
python3 compute_box.py
```

<details>
<summary><code>compute_box.py</code></summary>

```python
import json, re
from datetime import date

# ---- config -------------------------------------------------------------
ASOF   = date(2026, 6, 15)          # match the data date
K_LO, K_HI = 7000, 8000             # box strikes (width = 1000 pts = $100k)
EXPIRIES = [date(2026,12,18), date(2027,6,17),
            date(2027,12,17), date(2028,12,15)]
SOFR   = 3.60                       # %, looked up manually
# Treasury par curve (year-fraction, %) from the top row of ust2026.csv:
UST    = [(0.5,3.81),(1.0,3.84),(2.0,4.07),(3.0,4.10)]
# -------------------------------------------------------------------------

d = json.load(open("spx_raw.json"))
spot = d["data"]["current_price"]
chain = {}
for o in d["data"]["options"]:
    m = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})", o["option"])
    if not m: continue
    _, dt, cp, strk = m.groups()
    exp = date(2000+int(dt[:2]), int(dt[2:4]), int(dt[4:6]))
    chain.setdefault((exp, int(strk)/1000.0), {})[cp] = o

mid = lambda o: (o["bid"] + o["ask"]) / 2

def treas(T):                       # linear-interpolate the par curve
    if T <= UST[0][0]: return UST[0][1]
    for (t0,y0),(t1,y1) in zip(UST, UST[1:]):
        if t0 <= T <= t1: return y0 + (y1-y0)*(T-t0)/(t1-t0)
    return UST[-1][1]

print(f"SPX {spot}  as-of {ASOF}  box {K_LO}/{K_HI}\n")
print(f"{'expiry':12}{'days':>5}{'cost':>9}{'yield%':>8}{'UST%':>7}{'+UST':>6}{'+SOFR':>7}")
for exp in EXPIRIES:
    a, b = chain.get((exp,K_LO)), chain.get((exp,K_HI))
    if not (a and b and len(a)==2 and len(b)==2): continue
    cost = mid(a["C"]) - mid(b["C"]) + mid(b["P"]) - mid(a["P"])
    width = K_HI - K_LO
    T = (exp - ASOF).days / 365.0
    y = (width/cost - 1) / T * 100
    ut = treas(T)
    print(f"{str(exp):12}{(exp-ASOF).days:>5}{cost:>9.2f}{y:>8.3f}"
          f"{ut:>7.2f}{(y-ut)*100:>6.0f}{(y-SOFR)*100:>7.0f}")
```

</details>

Expected output (15 Jun 2026 snapshot):

```
expiry        days     cost  yield%   UST%  +UST  +SOFR
2026-12-18     186   978.65   4.281   3.81    47     68
2027-06-17     367   957.15   4.452   3.84    61     85
2027-12-17     550   936.65   4.488   3.96    53     89
2028-12-15     914   897.25   4.573   4.09    49     97
```

The featured trade is the most-liquid 6-month box (18 Dec 2026): pay **~$97,865**,
receive a guaranteed **$100,000** at expiry → **4.28%**, about **+47 bp** over the
6-mo T-bill and **+68 bp** over SOFR.

## Step 4 — Assemble the HTML

`index.html` is a self-contained file (inline CSS, no JS/build step).
Paste the computed figures from Step 3 into the hero stat, the trade ticket, and
the term-structure table, then open it:

```bash
open index.html        # macOS  (use xdg-open on Linux)
```

It is published via GitHub Pages at **https://chiaolun.github.io/box_spread/**.

---

## Caveats baked into the report

- **Delayed, indicative prices.** CBOE quotes are delayed; real fills differ.
- **Use a near-mid fill.** The 4.28% headline assumes the 4-leg package fills
  near mid. Crossing the *full* bid/ask on all legs is the conservative worst
  case (~3.39% for the Dec-2026 box). Always send a single **net-debit limit**.
- **Ignore stale LEAPS.** Far-dated boxes (2029+) can show double-digit
  "yields" — these are stale-quote artifacts on tiny open interest, not real.
  Stick to expiries whose legs carry meaningful OI (thousands+).
- **The box isolates the secured cash-funding rate** (SOFR + balance-sheet
  premium). It is the cleanest *tradeable* expression of the squeeze, but does
  not capture the entire futures equity-repo basis (part of which lives in the
  dividend/forward leg).

## Adapting it

- **Different strikes/width:** change `K_LO`/`K_HI`. Width × $100 = guaranteed
  payoff per contract. Pick strikes whose four legs all have high open interest.
- **Different date:** re-pull both files (Step 1–2), update `ASOF`, `UST`, and
  `SOFR`, and re-run.

---

*Educational analysis, not investment advice. Options involve risk.*
