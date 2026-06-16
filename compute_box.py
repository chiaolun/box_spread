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
