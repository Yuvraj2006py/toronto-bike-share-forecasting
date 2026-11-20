# Concrete walkthrough — one busy Monday morning

**Station:** 7006 — Bay St / College St (East Side)  
**When:** Monday 2024-09-23, 8:00–9:00am  
**What we predict:** bikes *leaving* this station in that hour  

## What actually happened
**7 bikes left.**

## Clues the models could see
| Clue | Value | Plain meaning |
|------|------:|---------------|
| Last week same hour (`lag_168h`) | 16 | Last Monday 8am was much busier |
| Yesterday 8am (`lag_24h`) | 3 | Yesterday’s commute was quiet |
| Last hour 7–8am (`lag_1h`) | 5 | Already some morning activity |
| Rolling mean last 24h | 6.25 | Station has been moderately busy lately |
| Temp / rain | 18.9°C / 1.5 mm | Mild, light rain |
| Calendar | Monday 8am, not a holiday | Normal commute slot |

## What each model guessed

| Model | Prediction | Error \|pred − 7\| | What it was thinking |
|-------|----------:|-------------------:|----------------------|
| Weekly naive | **16** | 9.00 | “Copy last Monday” — but last Monday was an outlier |
| Station × hour-of-week mean | **~5.8** | 1.17 | “Typical Monday 8am here is ~6” |
| Poisson + station | **~12.7** | 5.68 | Station is busy + last week was 16 → pulls high |
| GBM day-ahead | **~10.3** | 3.29 | Calendar/weather/lags without *last hour* |
| **GBM full (1-hour-ahead)** | **~7.3** | **0.29** | Saw recent level (~6) + last hour (5), didn’t trust 16 |

## The story in one paragraph
Last week’s Monday was unusually busy (16), so “copy last week” overshoots hard. The historical Monday-8am average (~6) is already close. Poisson still leans on that big weekly lag and overshoots. The full GBM wins because it can see **what this station has been doing in the last day/hour** — a moderate recent level — and mostly ignores the one loud weekly spike. That’s exactly why it’s a **1-hour-ahead** model: without `lag_1h` / recent rolling stats, you’re closer to the day-ahead GBM’s ~10.

## Second snapshot — same station, quiet night
**2024-09-24 02:00** at Bay/College: actual **0**.  
Weekly = 0, hist ≈ 0.2, Poisson ≈ 0.4, GBM full ≈ 0.5.  
Everyone roughly agrees “sleeping city” — the interesting disagreements show up at **peaks**, not empty nights.

## Interview one-liner
“On a real Monday 8am at Bay & College, last week said 16 but only 7 left; our GBM predicted 7.3 by using recent station activity, while weekly naive was off by 9.”
