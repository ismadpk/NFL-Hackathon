# Trench Partners

Find which NFL pass rushers and offensive linemen win together, as duos and trios.
Built on the NFL Big Data Bowl 2023 data (2021 season, weeks 1–8).

Four pages:
- **How it works**: what the tool does and how a match is scored
- **Teammate Matchmaker**: pick a player, see his best duos and trios, and charts that explain why
- **League Leaderboard**: the best duos and trios in the league
- **Player Directory**: every player with photo, size, college and draft slot, plus a shortlist

You can find it at https://trench-partners.vercel.app/

## Run it locally

From the project folder:

```
python3 -m http.server 8000 -d app
```

Open http://localhost:8000. Stop it with `Ctrl+C`.

If you see `Address already in use`, free the port with `lsof -ti:8000 | xargs kill`, or use another port (`8001`).

## Deploy on Vercel

The app is a static site in `app/`, with no build step.

- **From GitHub:** import the repo on vercel.com, set Framework Preset to **Other** and Root Directory to **`app`**, then click Deploy.
- **From the terminal:** `cd app && npx vercel --prod`

## Rebuild the data (optional)

Only needed if the CSVs change. Put the Big Data Bowl files in `data/` (they are git-ignored), then run:

```
python3 scripts/build_data.py
```

This writes `app/data.js` and `app/photos.js`. Headshots and draft details come from the public nflverse roster, stored in `data/external/`.
