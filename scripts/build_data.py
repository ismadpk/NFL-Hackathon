"""Build app/data.js and app/photos.js from the Big Data Bowl CSVs.

Run from the repo root: python3 scripts/build_data.py
Stdlib only, no pandas needed.
"""
import base64
import csv
import json
import os
from collections import Counter, defaultdict
from datetime import date
from itertools import combinations

DATA = "data"
OUT = "app"
MIN_DUO = 30      # snaps together before a duo can be ranked
MIN_TRIO = 30
PRIOR = 20        # shrinkage strength (snaps) toward the league rate
MIN_RADAR = 50    # role snaps needed to be in the percentile pool


def rows(name):
    with open(os.path.join(DATA, name), newline="") as f:
        yield from csv.DictReader(f)


def flag(v):
    return v == "1"


def down_bucket(down, ytg):
    if down == 1:
        return "1st down"
    if down == 2:
        return "2nd down"
    if down in (3, 4):
        return "3rd/4th & short" if ytg <= 3 else ("3rd/4th & medium" if ytg <= 7 else "3rd/4th & long")
    return "other"


BUCKETS = ["1st down", "2nd down", "3rd/4th & short", "3rd/4th & medium", "3rd/4th & long"]

# ---- plays -----------------------------------------------------------------
plays = {}
for r in rows("plays.csv"):
    plays[(r["gameId"], r["playId"])] = {
        "off": r["possessionTeam"],
        "def": r["defensiveTeam"],
        "bucket": down_bucket(int(r["down"]), int(r["yardsToGo"])),
    }

# ---- scouting, grouped by play ---------------------------------------------
by_play = defaultdict(list)
for r in rows("pffScoutingData.csv"):
    by_play[(r["gameId"], r["playId"])].append(r)

stats = defaultdict(Counter)
teams = defaultdict(Counter)
combo = {"rush": defaultdict(Counter), "block": defaultdict(Counter)}
solo = {"rush": defaultdict(Counter), "block": defaultdict(Counter)}
league = {"rush": Counter(), "block": Counter()}

for key, prs in by_play.items():
    p = plays.get(key)
    if not p:
        continue
    rushers, blockers = [], []
    pressured = False
    align, credit = {}, {}  # nflId -> alignment, nflId -> made/allowed the pressure
    for r in prs:
        pid, role = r["nflId"], r["pff_role"]
        align[pid] = r["pff_positionLinedUp"]
        s = stats[pid]
        s["snaps"] += 1
        s["role:" + role] += 1
        if role == "Pass Rush":
            rushers.append(pid)
            teams[pid][p["def"]] += 1
            hit, hur, sack = flag(r["pff_hit"]), flag(r["pff_hurry"]), flag(r["pff_sack"])
            s["hits"] += hit
            s["hurries"] += hur
            s["sacks"] += sack
            s["pressures"] += hit or hur or sack
            credit[pid] = hit or hur or sack
            pressured = pressured or hit or hur or sack
        elif role == "Pass Block":
            blockers.append(pid)
            teams[pid][p["off"]] += 1
            ha, hua, sa = flag(r["pff_hitAllowed"]), flag(r["pff_hurryAllowed"]), flag(r["pff_sackAllowed"])
            s["hitsAllowed"] += ha
            s["hurriesAllowed"] += hua
            s["sacksAllowed"] += sa
            s["pressuresAllowed"] += ha or hua or sa
            credit[pid] = ha or hua or sa
            s["beaten"] += flag(r["pff_beatenByDefender"])
        elif role in ("Pass", "Pass Route"):
            teams[pid][p["off"]] += 1
        else:
            teams[pid][p["def"]] += 1

    # "success" for the side: rushers want pressure, blockers want a clean pocket
    for side, group, win in (("rush", rushers, pressured), ("block", blockers, not pressured)):
        league[side]["n"] += 1
        league[side]["win"] += win
        for pid in group:
            solo[side][pid]["n"] += 1
            solo[side][pid]["win"] += win
        g = sorted(group)
        for k in (2, 3):
            for c in combinations(g, k):
                cc = combo[side][c]
                cc["n"] += 1
                cc["win"] += win
                cc["n:" + p["bucket"]] += 1
                cc["win:" + p["bucket"]] += win
                for m in c:
                    cc["at:" + m + ":" + align[m]] += 1
                if pressured:
                    # who made it (rush) or who gave it up (block) among this group
                    who = [m for m in c if credit.get(m)]
                    cc["cr:" + (who[0] if len(who) == 1 else "multi" if who else "other")] += 1

league_rate = {s: league[s]["win"] / league[s]["n"] for s in league}

# ---- players + nflverse enrichment -----------------------------------------
nv = {}
for r in csv.DictReader(open(os.path.join(DATA, "external", "nflverse_players.csv"), newline="")):
    if r["nfl_id"]:
        nv[r["nfl_id"]] = r


def height_in(h):
    try:
        ft, inch = h.split("-")
        return int(ft) * 12 + int(inch)
    except ValueError:
        return int(h) if h.isdigit() else None


SEASON_START = date(2021, 9, 9)
players = {}
for r in rows("players.csv"):
    pid = r["nflId"]
    s = stats[pid]
    extra = nv.get(pid, {})
    age = None
    if r["birthDate"] and r["birthDate"] != "NA":
        try:
            b = date.fromisoformat(r["birthDate"][:10])
            age = SEASON_START.year - b.year - ((SEASON_START.month, SEASON_START.day) < (b.month, b.day))
        except ValueError:
            pass
    roles = {k[5:]: v for k, v in s.items() if k.startswith("role:")}
    primary = max(roles, key=roles.get) if roles else None
    players[pid] = {
        "id": pid,
        "name": r["displayName"],
        "pos": r["officialPosition"],
        "team": teams[pid].most_common(1)[0][0] if teams[pid] else None,
        "college": r["collegeName"] if r["collegeName"] != "NA" else None,
        "conf": extra.get("college_conference") or None,
        "ht": height_in(r["height"]),
        "wt": int(r["weight"]) if r["weight"].isdigit() else None,
        "age": age,
        "draft": [extra.get("draft_year"), extra.get("draft_round"), extra.get("draft_pick"), extra.get("draft_team")]
        if extra.get("draft_year") else None,
        "exp": extra.get("years_of_experience") or None,
        "role": primary,
        "roles": roles,
        "snaps": s["snaps"],
        "s": {k: s[k] for k in ("hits", "hurries", "sacks", "pressures", "hitsAllowed",
                                "hurriesAllowed", "sacksAllowed", "pressuresAllowed", "beaten")},
    }

# ---- percentiles (radar) ---------------------------------------------------
RADAR = {
    "Pass Rush": [("Pressure rate", "pressures", 1), ("Hurry rate", "hurries", 1),
                  ("Hit rate", "hits", 1), ("Sack rate", "sacks", 1)],
    "Pass Block": [("Pressure avoided", "pressuresAllowed", -1), ("Hurries avoided", "hurriesAllowed", -1),
                   ("Hits avoided", "hitsAllowed", -1), ("Sacks avoided", "sacksAllowed", -1),
                   ("Wins rep", "beaten", -1)],
}
for role, axes in RADAR.items():
    pool = [p for p in players.values() if p["roles"].get(role, 0) >= MIN_RADAR]
    for label, stat, sign in axes:
        vals = sorted(sign * p["s"][stat] / p["roles"][role] for p in pool)
        for p in players.values():
            n = p["roles"].get(role, 0)
            if n < MIN_RADAR:
                continue
            v = sign * p["s"][stat] / n
            below = sum(1 for x in vals if x < v)
            p.setdefault("pct", {}).setdefault(role, []).append([label, round(100 * below / max(1, len(vals) - 1))])

# ---- best duos / trios -----------------------------------------------------
def shrunk(win, n, mu):
    return (win + PRIOR * mu) / (n + PRIOR)


def export_combo(side, c, score):
    cid = side + ":" + "-".join(c)
    if cid in combos_out:
        return cid
    cc = combo[side][c]
    apart = {}
    for m in c:
        sm = solo[side][m]
        apart[m] = [sm["win"] - cc["win"], sm["n"] - cc["n"]]
    spots = {}
    for m in c:
        at = Counter({k.split(":", 2)[2]: v for k, v in cc.items() if k.startswith("at:" + m + ":")})
        spots[m] = [[a, n] for a, n in at.most_common(3)]
    combos_out[cid] = {
        "side": side,
        "ids": list(c),
        "team": players[c[0]]["team"],
        "n": cc["n"],
        "win": cc["win"],
        "score": round(score, 4),
        "apart": apart,
        "spots": spots,
        "credit": {k[3:]: v for k, v in cc.items() if k.startswith("cr:")},
        "buckets": [[b, cc["win:" + b], cc["n:" + b]] for b in BUCKETS if cc["n:" + b]],
    }
    return cid


combos_out = {}
leaders = {}
for side, role in (("rush", "Pass Rush"), ("block", "Pass Block")):
    mu = league_rate[side]
    ranked = defaultdict(lambda: {2: [], 3: []})
    every = {2: [], 3: []}
    for c, cc in combo[side].items():
        k = len(c)
        if cc["n"] < (MIN_DUO if k == 2 else MIN_TRIO):
            continue
        score = shrunk(cc["win"], cc["n"], mu)
        every[k].append((score, c))
        for pid in c:
            ranked[pid][k].append((score, c))
    leaders[side] = {
        "duo": [export_combo(side, c, s) for s, c in sorted(every[2], reverse=True)[:10]],
        "trio": [export_combo(side, c, s) for s, c in sorted(every[3], reverse=True)[:10]],
    }
    for pid, by_k in ranked.items():
        p = players.get(pid)
        if not p or p["role"] != role:
            continue
        p["side"] = side
        p["matches"] = {}
        for k, top in ((2, 3), (3, 2)):
            best = sorted(by_k[k], reverse=True)[:top]
            ids = []
            for score, c in best:
                ids.append(export_combo(side, c, score))
            p["matches"]["duo" if k == 2 else "trio"] = ids

out = {
    "league": {s: round(v, 4) for s, v in league_rate.items()},
    "minDuo": MIN_DUO,
    "minTrio": MIN_TRIO,
    "players": list(players.values()),
    "combos": combos_out,
    "leaders": leaders,
}
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "data.js"), "w") as f:
    f.write("window.DATA=" + json.dumps(out, separators=(",", ":")) + ";\n")

# ---- headshots as data URIs (artifact pages can't load external images) ----
shots = {}
hdir = os.path.join(DATA, "external", "headshots")
for fn in os.listdir(hdir):
    with open(os.path.join(hdir, fn), "rb") as f:
        shots[fn.split(".")[0]] = "data:image/webp;base64," + base64.b64encode(f.read()).decode()
with open(os.path.join(OUT, "photos.js"), "w") as f:
    f.write("window.PHOTOS=" + json.dumps(shots, separators=(",", ":")) + ";\n")

print("league", league_rate)
print("players with matches", sum(1 for p in players.values() if p.get("matches", {}).get("duo")))
print("players with trios", sum(1 for p in players.values() if p.get("matches", {}).get("trio")))
print("combos", len(combos_out))
print("data.js", os.path.getsize(os.path.join(OUT, "data.js")) // 1024, "KB; photos.js",
      os.path.getsize(os.path.join(OUT, "photos.js")) // 1024, "KB")
