from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone, date, datetime, timedelta
from statistics import mean
import math
import os
import re
import threading
from typing import Any

import pytz

UTC = timezone.utc

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, redirect, render_template, request


app = Flask(__name__)
PARIS_TZ = pytz.timezone("Europe/Paris")

MAREE_URL = "https://maree.info/3"
WINDGURU_SPOT_ID = "85184"
WINDGURU_API = "https://www.windguru.net/int/iapi.php"
UA = {"User-Agent": "Mozilla/5.0"}

# ── Tidal current model — Dunkirk calibration ─────────────────────────────
# Based on ADCP measurements (offshore wind project) + SHOM interpolation.
# Tune V_MORTE_EAU / V_VIVE_EAU after a few validation dives.
V_MORTE_EAU         = 0.55   # m/s  max surface current at amplitude RANGE_MORTE_EAU
V_VIVE_EAU          = 1.00   # m/s  max surface current at amplitude RANGE_VIVE_EAU
RANGE_MORTE_EAU     = 2.5    # m    tidal range (PM-BM) at morte-eau (coeff ~45)
RANGE_VIVE_EAU      = 5.9    # m    tidal range (PM-BM) at vive-eau  (coeff ~95)
V_SEUIL             = 0.30   # m/s  dive-comfort current threshold
K_SLACK_TO_PM       = 2.5    # tidal-hours before PM  (Dunkirk asymmetric rule)
K_SLACK_TO_BM       = 3.0    # tidal-hours before BM  (Dunkirk asymmetric rule)
T_PREP_MIN          = 15     # min  descent + positioning allowance before slack
_T_SEMI_DIURNAL_MIN = 745.0  # mean semi-diurnal period  (12 h 25 m) in minutes
_OMEGA              = 2.0 * math.pi / _T_SEMI_DIURNAL_MIN  # rad / min
RISING_TIDE_BONUS   = 5      # points added to slot score on marée montante (flot)

CACHE_TTL_SECONDS = 60 * 60
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {
    "conditions": None,
    "fetched_at": None,
}


@dataclass
class DailyDiveConditions:
    day: date
    tide_coefficient: float | None
    wind_speed_kn: float | None
    wind_direction_deg: float | None
    wave_height_m: float | None
    score: int
    label: str
    css_class: str
    day_label_fr: str
    dive_slots: list[str]
    meteo_hours_used: int
    slot_scores: list[int]
    reliability_pct: int
    score_explanation: str
    coef_quality: int
    wind_quality: int
    wave_quality: int
    dir_quality: int
    dive_slot_items: list[dict[str, Any]]       # modèle actif (simple par défaut)
    dive_slot_items_sci: list[dict[str, Any]]   # modèle scientifique
    tide_events: list[dict[str, Any]]           # [{time_str, height_m, is_pm}, ...]


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def angular_distance_deg(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def score_day(coef: float | None, wind_kn: float | None, wave_m: float | None, wind_dir: float | None) -> int:
    coef_score = 0.5 if coef is None else 1 - clamp((coef - 20) / 100, 0, 1)
    wind_score = 0.5 if wind_kn is None else 1 - clamp(wind_kn / 25, 0, 1)
    # <0.5m good, 0.5m medium (~50%), 1m bad (~33%)
    wave_score = 0.5 if wave_m is None else 1 - clamp(wave_m / 1.5, 0, 1)
    dir_score = 0.5 if wind_dir is None else 1 - clamp(angular_distance_deg(wind_dir, 180) / 180, 0, 1)
    effective_dir_score = effective_direction_score(dir_score, wind_kn)

    weighted = (coef_score * 0.30) + (wind_score * 0.30) + (wave_score * 0.30) + (effective_dir_score * 0.10)
    return round(weighted * 100)


def effective_direction_score(dir_score: float, wind_kn: float | None) -> float:
    # Strong attenuation at low wind:
    # <=3 kn: almost neutral direction impact, >=15 kn: full direction impact.
    if wind_kn is None:
        return dir_score
    influence = clamp((wind_kn - 3) / 12, 0, 1)
    return (dir_score * influence) + ((1 - influence) * 0.5)


def criterion_quality_scores(
    coef: float | None, wind_kn: float | None, wave_m: float | None, wind_dir: float | None
) -> tuple[int, int, int, int]:
    coef_score = 0.5 if coef is None else 1 - clamp((coef - 20) / 100, 0, 1)
    wind_score = 0.5 if wind_kn is None else 1 - clamp(wind_kn / 25, 0, 1)
    wave_score = 0.5 if wave_m is None else 1 - clamp(wave_m / 1.5, 0, 1)
    dir_score = 0.5 if wind_dir is None else 1 - clamp(angular_distance_deg(wind_dir, 180) / 180, 0, 1)
    effective_dir_score = effective_direction_score(dir_score, wind_kn)
    return (
        round(coef_score * 100),
        round(wind_score * 100),
        round(wave_score * 100),
        round(effective_dir_score * 100),
    )


def reliability_for_day(days_ahead: int) -> int:
    # J+0 ~ 100%, J+6 ~ 58% (linear decay)
    return round(clamp(100 - (days_ahead * 7), 58, 100))


def build_score_explanation(
    score: int,
    coef: float | None,
    wind_kn: float | None,
    wave_m: float | None,
    wind_dir: float | None,
    reliability_pct: int,
) -> str:
    if score >= 75:
        positives: list[str] = []
        if coef is not None and coef <= 60:
            positives.append("coefficient favorable")
        if wind_kn is not None and wind_kn <= 9:
            positives.append("vent faible")
        if wave_m is not None and wave_m <= 0.4:
            positives.append("vagues basses")
        if wind_dir is not None and angular_distance_deg(wind_dir, 180) <= 55:
            positives.append("direction de vent proche sud")
        if positives:
            return "Très bon: " + ", ".join(positives) + "."
        return "Très bon: paramètres globalement favorables."

    if score <= 54:
        negatives: list[str] = []
        if coef is not None and coef >= 85:
            negatives.append("coefficient élevé")
        if wind_kn is not None and wind_kn >= 14:
            negatives.append("vent fort")
        if wave_m is not None and wave_m >= 0.9:
            negatives.append("vagues marquées")
        if wind_dir is not None and angular_distance_deg(wind_dir, 180) >= 95:
            negatives.append("direction de vent peu favorable")
        if reliability_pct <= 65:
            negatives.append("prévision encore éloignée")
        if negatives:
            return "Moins bon: " + ", ".join(negatives) + "."
        return "Moins bon: conditions globales peu favorables."

    return "Intermédiaire: conditions praticables mais pas optimales."


def score_label(score: int) -> tuple[str, str]:
    if score >= 75:
        return "Idéal", "ideal"
    if score >= 55:
        return "Correct", "correct"
    return "Mauvais", "mauvais"


def parse_french_month_name(month_name: str) -> int:
    month_map = {
        "janvier": 1,
        "fevrier": 2,
        "février": 2,
        "mars": 3,
        "avril": 4,
        "mai": 5,
        "juin": 6,
        "juillet": 7,
        "aout": 8,
        "août": 8,
        "septembre": 9,
        "octobre": 10,
        "novembre": 11,
        "decembre": 12,
        "décembre": 12,
    }
    return month_map[month_name.strip().lower()]


def parse_main_page_reference_date(soup: BeautifulSoup) -> date | None:
    header_table = soup.find("table", id="MareeEntete")
    if not header_table:
        return None
    header_text = header_table.get_text(" ", strip=True)
    m = re.search(r"(\d{1,2})\s+([A-Za-zéûôîùàçÉÛÔÎÙÀÇ]+)\s+(\d{4})", header_text)
    if not m:
        return None
    return date(int(m.group(3)), parse_french_month_name(m.group(2)), int(m.group(1)))


def parse_h_m(token: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"(\d{1,2})h(\d{2})", token.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _tidal_v_max_from_range(tidal_range: float) -> float:
    """Interpolate max current speed from actual tidal range (PM height - BM height)."""
    t = (tidal_range - RANGE_MORTE_EAU) / (RANGE_VIVE_EAU - RANGE_MORTE_EAU)
    t = max(0.0, min(1.0, t))  # clamp to [0, 1]
    return V_MORTE_EAU + t * (V_VIVE_EAU - V_MORTE_EAU)


def _slack_window_minutes(tidal_range: float) -> float:
    """Duration (min) where current ≤ V_SEUIL, sinusoidal NOAA model.
    Uses the actual tidal range of the individual half-cycle."""
    vmax = _tidal_v_max_from_range(tidal_range)
    if V_SEUIL >= vmax:
        return _T_SEMI_DIURNAL_MIN / 2.0  # effectively unlimited
    ratio = min(V_SEUIL / vmax, 1.0)
    return (2.0 / _OMEGA) * math.asin(ratio)


SlotList  = list[tuple[datetime, datetime, bool]]
SlotsByDay = dict[date, SlotList]


def _build_slots_simple(events: list[tuple[datetime, float]]) -> SlotsByDay:
    """±3h absolute model (Dr Carter): window = abs(E1+3h ↔ E2-3h)."""
    OFFSET = timedelta(hours=3)
    slots: SlotsByDay = {}
    for i in range(len(events) - 1):
        e1_dt, e1_h = events[i]
        e2_dt, e2_h = events[i + 1]
        if e2_dt <= e1_dt:
            continue
        is_rising = e2_h > e1_h
        b1, b2 = e1_dt + OFFSET, e2_dt - OFFSET
        start, end = min(b1, b2), max(b1, b2)
        if (end - start).total_seconds() < 600:
            continue
        mid_day = (start + (end - start) / 2).date()
        slots.setdefault(mid_day, []).append((start, end, is_rising))
    return slots


def _build_slots_scientific(events: list[tuple[datetime, float]]) -> SlotsByDay:
    """Scientific model: tidal-hour offsets (K=2.5/3.0) + NOAA sinusoid window."""
    slots: SlotsByDay = {}
    for i in range(len(events) - 1):
        e1_dt, e1_h = events[i]
        e2_dt, e2_h = events[i + 1]
        if e2_dt <= e1_dt:
            continue
        half_cycle_min = (e2_dt - e1_dt).total_seconds() / 60.0
        hm_min = half_cycle_min / 6.0
        e2_is_pm = e2_h > e1_h
        is_rising = e2_is_pm
        k = K_SLACK_TO_PM if e2_is_pm else K_SLACK_TO_BM
        t_slack = e2_dt - timedelta(minutes=k * hm_min)
        tidal_range = abs(e2_h - e1_h)
        dur_min = _slack_window_minutes(tidal_range)
        half_dur = timedelta(minutes=dur_min / 2.0)
        start, end = t_slack - half_dur, t_slack + half_dur
        slots.setdefault(t_slack.date(), []).append((start, end, is_rising))
    return slots


def fetch_dive_slots_by_day(
    coefficients: dict[date, float],
) -> tuple[SlotsByDay, SlotsByDay, dict[date, list[dict]]]:
    """
    Compute dive windows using the Dunkirk tidal-current model:
      - slack centre = E2 - k * HM  (k=2.5 before PM, k=3.0 before BM)
      - window width = f(coefficient) via SHOM interpolation + NOAA sinusoid
      - returns (start, end, is_rising) tuples — is_rising=True on marée montante
    """
    html = requests.get(MAREE_URL, headers=UA, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")
    ref_date = parse_main_page_reference_date(soup)
    table = soup.find("table", id="MareeJours")
    if not table or not ref_date:
        return {}

    # ── Parse all tide events (datetime, height_m) ─────────────────
    events: list[tuple[datetime, float]] = []
    cursor = ref_date
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue
        day_cell    = cells[0].get_text(" ", strip=True)
        times_cell  = cells[1].get_text(" ", strip=True)
        heights_cell = cells[2].get_text(" ", strip=True)

        day_match = re.search(r"(\d{1,2})$", day_cell)
        if not day_match:
            continue
        day_num = int(day_match.group(1))
        year, month = cursor.year, cursor.month
        if day_num < cursor.day:
            month += 1
            if month > 12:
                month, year = 1, year + 1
        cursor = date(year, month, day_num)

        time_tokens  = re.findall(r"\d{1,2}h\d{2}", times_cell)
        height_tokens = [h.replace(",", ".") for h in re.findall(r"\d+,\d+m", heights_cell)]
        heights = [float(h[:-1]) for h in height_tokens]
        for tkn, h in zip(time_tokens, heights):
            hm = parse_h_m(tkn)
            if hm is None:
                continue
            dt = PARIS_TZ.localize(
                datetime(cursor.year, cursor.month, cursor.day, hm[0], hm[1])
            )
            events.append((dt, h))

    events.sort(key=lambda x: x[0])

    # ── Index tide events by day ───────────────────────────────────
    events_by_day: dict[date, list[dict]] = {}
    for i in range(len(events)):
        dt, h = events[i]
        # Determine PM or BM by comparing with neighbours
        prev_h = events[i - 1][1] if i > 0 else None
        next_h = events[i + 1][1] if i < len(events) - 1 else None
        if prev_h is not None and next_h is not None:
            is_pm = h > prev_h and h > next_h
        elif next_h is not None:
            is_pm = h > next_h
        elif prev_h is not None:
            is_pm = h > prev_h
        else:
            is_pm = False
        events_by_day.setdefault(dt.date(), []).append({
            "time_str": dt.strftime("%H:%M"),
            "height_m": round(h, 2),
            "is_pm": is_pm,
        })

    slots_simple     = _build_slots_simple(events)
    slots_scientific = _build_slots_scientific(events)

    return slots_simple, slots_scientific, events_by_day


def fetch_tide_coefficients() -> dict[date, float]:
    html = requests.get(f"{MAREE_URL}/calendrier", headers=UA, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")
    result: dict[date, float] = {}

    for month_table in soup.find_all("table", class_="CalendrierMois"):
        title_cell = month_table.find("th")
        if not title_cell:
            continue

        title_match = re.search(r"([A-Za-zéûôîùàçÉÛÔÎÙÀÇ]+)\s+(\d{4})", title_cell.get_text(" ", strip=True))
        if not title_match:
            continue
        month = parse_french_month_name(title_match.group(1))
        year = int(title_match.group(2))

        for row in month_table.find_all("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            if len(cells) < 3:
                continue

            day_match = re.search(r"^\s*(\d{1,2})\b", cells[1] if len(cells) > 1 else "")
            if not day_match:
                continue
            day_num = int(day_match.group(1))

            numeric_tail = []
            for cell in cells:
                if re.fullmatch(r"\d{1,3}", cell):
                    numeric_tail.append(int(cell))
            if not numeric_tail:
                continue

            result[date(year, month, day_num)] = min(numeric_tail[-2:])

    return result


def fetch_windguru_hourly() -> tuple[dict[datetime, dict], dict[datetime, dict]]:
    meta = requests.get(
        WINDGURU_API,
        params={"q": "forecast_spot", "id_spot": WINDGURU_SPOT_ID},
        headers={**UA, "Referer": f"https://www.windguru.cz/{WINDGURU_SPOT_ID}"},
        timeout=20,
    ).json()

    def find_model(model_id: int) -> dict:
        for tab in meta.get("tabs", []):
            if tab.get("id_model") == model_id and tab.get("id_model_arr"):
                return tab["id_model_arr"][0]
        raise RuntimeError(f"Model {model_id} not found in Windguru response.")

    wind_model_local = find_model(52)  # AROME-FR wind near Dunkerque
    wind_model_global = find_model(3)  # GFS fallback when local horizon ends
    wave_model = find_model(84)  # GFS wave

    def fetch_model(model_ref: dict) -> dict:
        params = {
            "q": "forecast",
            "id_spot": WINDGURU_SPOT_ID,
            "id_model": model_ref["id_model"],
            "initstr": model_ref["initstr"],
            "rundef": model_ref["rundef"],
        }
        if model_ref.get("cachefix"):
            params["cachefix"] = model_ref["cachefix"]

        return requests.get(
            WINDGURU_API,
            params=params,
            headers={**UA, "Referer": f"https://www.windguru.cz/{WINDGURU_SPOT_ID}"},
            timeout=20,
        ).json()["fcst"]

    wind_fcst_local = fetch_model(wind_model_local)
    wind_fcst_global = fetch_model(wind_model_global)
    wave_fcst = fetch_model(wave_model)

    def to_hourly(fcst: dict, speed_key: str, dir_key: str | None = None) -> dict[datetime, dict]:
        hourly: dict[datetime, dict] = {}
        initstamp = int(fcst["initstamp"])
        hours = fcst.get("hours", [])
        speeds = fcst.get(speed_key, [])
        dirs = fcst.get(dir_key, []) if dir_key else []

        for idx, hour in enumerate(hours):
            if idx >= len(speeds):
                continue
            speed = speeds[idx]
            if speed is None:
                continue

            ts = initstamp + int(hour) * 3600
            dt = datetime.fromtimestamp(ts, tz=UTC).astimezone(PARIS_TZ).replace(minute=0, second=0, microsecond=0)

            hourly[dt] = {
                "speed": float(speed),
                "dir": float(dirs[idx]) if (dir_key and idx < len(dirs) and dirs[idx] is not None) else None,
            }
        return hourly

    wind_hourly_local = to_hourly(wind_fcst_local, "WINDSPD", "WINDDIR")
    wind_hourly_global = to_hourly(wind_fcst_global, "WINDSPD", "WINDDIR")
    wind_hourly = {**wind_hourly_global, **wind_hourly_local}
    wave_hourly = to_hourly(wave_fcst, "HTSGW")
    return wind_hourly, wave_hourly


def french_weekday_name(d: date) -> str:
    names = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    return names[d.weekday()]


def build_conditions(limit_days: int | None = 7) -> list[DailyDiveConditions]:
    tides = fetch_tide_coefficients()
    wind_hourly, wave_hourly = fetch_windguru_hourly()
    dive_slots_simple, dive_slots_sci, tide_events_by_day = fetch_dive_slots_by_day(tides)

    # Only keep days where both wind and wave forecasts exist.
    weather_days = sorted({dt.date() for dt in wind_hourly.keys()} & {dt.date() for dt in wave_hourly.keys()})
    all_days = sorted(set(tides.keys()) & set(weather_days) & (set(dive_slots_simple.keys()) | set(dive_slots_sci.keys())))
    all_days = [d for d in all_days if d >= datetime.now(PARIS_TZ).date()]
    if limit_days is not None:
        all_days = all_days[:limit_days]

    rows: list[DailyDiveConditions] = []
    today = datetime.now(PARIS_TZ).date()
    for day in all_days:
        coef = tides.get(day)
        slot_ranges = dive_slots_simple.get(day, [])
        slot_labels = [f"{s.strftime('%H:%M')} - {e.strftime('%H:%M')}" for s, e, _r in slot_ranges]

        day_wind_points = [(h_dt, w) for h_dt, w in wind_hourly.items() if h_dt.date() == day]
        day_wave_points = [(h_dt, wv) for h_dt, wv in wave_hourly.items() if h_dt.date() == day]

        slot_scores: list[int] = []
        slot_meteo: list[dict] = []
        meteo_hours = 0
        slot_wind_maxes: list[float] = []
        slot_dirs: list[float] = []
        slot_wave_maxes: list[float] = []

        for start, end, is_rising in slot_ranges:
            s_winds: list[float] = []
            s_dirs: list[float] = []
            s_waves: list[float] = []

            for h_dt, w in day_wind_points:
                if start <= h_dt <= end:
                    s_winds.append(float(w["speed"]))
                    if w.get("dir") is not None:
                        s_dirs.append(float(w["dir"]))

            for h_dt, wv in day_wave_points:
                if start <= h_dt <= end:
                    s_waves.append(float(wv["speed"]))

            # Fallback per slot: nearest point around slot midpoint, tolerance +/- 2h.
            mid = start + (end - start) / 2
            if not s_winds and day_wind_points:
                nearest_wind = min(day_wind_points, key=lambda p: abs((p[0] - mid).total_seconds()))
                if abs((nearest_wind[0] - mid).total_seconds()) <= 2 * 3600:
                    s_winds.append(float(nearest_wind[1]["speed"]))
                    if nearest_wind[1].get("dir") is not None:
                        s_dirs.append(float(nearest_wind[1]["dir"]))

            if not s_waves and day_wave_points:
                nearest_wave = min(day_wave_points, key=lambda p: abs((p[0] - mid).total_seconds()))
                if abs((nearest_wave[0] - mid).total_seconds()) <= 2 * 3600:
                    s_waves.append(float(nearest_wave[1]["speed"]))

            meteo_hours += min(len(s_winds), len(s_waves))
            slot_wind = max(s_winds) if s_winds else None
            slot_dir = mean(s_dirs) if s_dirs else None
            slot_wave = max(s_waves) if s_waves else None
            raw_score = score_day(coef, slot_wind, slot_wave, slot_dir)
            slot_score = min(100, raw_score + RISING_TIDE_BONUS) if is_rising else raw_score
            slot_scores.append(slot_score)
            slot_meteo.append({
                "wind": round(slot_wind, 1) if slot_wind is not None else None,
                "dir": round(slot_dir) if slot_dir is not None else None,
                "wave": round(slot_wave, 2) if slot_wave is not None else None,
                "is_rising": is_rising,
            })

            if slot_wind is not None:
                slot_wind_maxes.append(slot_wind)
            if slot_dir is not None:
                slot_dirs.append(slot_dir)
            if slot_wave is not None:
                slot_wave_maxes.append(slot_wave)

        wind_speed = max(slot_wind_maxes) if slot_wind_maxes else None
        wind_dir = mean(slot_dirs) if slot_dirs else None
        wave_height = max(slot_wave_maxes) if slot_wave_maxes else None
        score = round(mean(slot_scores)) if slot_scores else score_day(coef, wind_speed, wave_height, wind_dir)
        label, css_class = score_label(score)
        reliability_pct = reliability_for_day((day - today).days)
        score_explanation = build_score_explanation(score, coef, wind_speed, wave_height, wind_dir, reliability_pct)
        coef_q, wind_q, wave_q, dir_q = criterion_quality_scores(coef, wind_speed, wave_height, wind_dir)
        def make_slot_items(ranges: SlotList, meteo: list[dict], scores: list[int]) -> list[dict[str, Any]]:
            items = []
            for idx, (start, end, is_rising) in enumerate(ranges):
                duration_min = int(round((end - start).total_seconds() / 60))
                m = meteo[idx] if idx < len(meteo) else {}
                items.append({
                    "slot_index": idx + 1,
                    "range": f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}",
                    "duration_min": duration_min,
                    "score": scores[idx] if idx < len(scores) else None,
                    "is_rising": is_rising,
                    "wind_kn": m.get("wind"),
                    "wind_dir_deg": m.get("dir"),
                    "wave_m": m.get("wave"),
                })
            return items

        dive_slot_items = make_slot_items(slot_ranges, slot_meteo, slot_scores)

        # Scientific model slots — compute scores with same meteo lookup
        sci_ranges = dive_slots_sci.get(day, [])
        sci_scores: list[int] = []
        sci_meteo: list[dict] = []
        for start, end, is_rising in sci_ranges:
            s_winds, s_dirs, s_waves = [], [], []
            mid = start + (end - start) / 2
            for h_dt, w in day_wind_points:
                if start <= h_dt <= end:
                    s_winds.append(float(w["speed"]))
                    if w.get("dir") is not None:
                        s_dirs.append(float(w["dir"]))
            for h_dt, wv in day_wave_points:
                if start <= h_dt <= end:
                    s_waves.append(float(wv["speed"]))
            if not s_winds and day_wind_points:
                nw = min(day_wind_points, key=lambda p: abs((p[0] - mid).total_seconds()))
                if abs((nw[0] - mid).total_seconds()) <= 2 * 3600:
                    s_winds.append(float(nw[1]["speed"]))
                    if nw[1].get("dir") is not None:
                        s_dirs.append(float(nw[1]["dir"]))
            if not s_waves and day_wave_points:
                nwv = min(day_wave_points, key=lambda p: abs((p[0] - mid).total_seconds()))
                if abs((nwv[0] - mid).total_seconds()) <= 2 * 3600:
                    s_waves.append(float(nwv[1]["speed"]))
            sw = max(s_winds) if s_winds else None
            sd = mean(s_dirs) if s_dirs else None
            swv = max(s_waves) if s_waves else None
            raw = score_day(coef, sw, swv, sd)
            sci_scores.append(min(100, raw + RISING_TIDE_BONUS) if is_rising else raw)
            sci_meteo.append({
                "wind": round(sw, 1) if sw is not None else None,
                "dir": round(sd) if sd is not None else None,
                "wave": round(swv, 2) if swv is not None else None,
            })
        dive_slot_items_sci = make_slot_items(sci_ranges, sci_meteo, sci_scores)

        rows.append(
            DailyDiveConditions(
                day=day,
                tide_coefficient=coef,
                wind_speed_kn=round(wind_speed, 1) if wind_speed is not None else None,
                wind_direction_deg=round(wind_dir) if wind_dir is not None else None,
                wave_height_m=round(wave_height, 2) if wave_height is not None else None,
                score=score,
                label=label,
                css_class=css_class,
                day_label_fr=f"{french_weekday_name(day)} {day.strftime('%d/%m')}",
                dive_slots=slot_labels,
                meteo_hours_used=meteo_hours,
                slot_scores=slot_scores,
                reliability_pct=reliability_pct,
                score_explanation=score_explanation,
                coef_quality=coef_q,
                wind_quality=wind_q,
                wave_quality=wave_q,
                dir_quality=dir_q,
                dive_slot_items=dive_slot_items,
                dive_slot_items_sci=dive_slot_items_sci,
                tide_events=tide_events_by_day.get(day, []),
            )
        )

    rows.sort(key=lambda x: x.day)
    return rows


def get_cached_conditions(force_refresh: bool = False) -> tuple[list[DailyDiveConditions], datetime]:
    now = datetime.now(PARIS_TZ)
    with _CACHE_LOCK:
        fetched_at = _CACHE.get("fetched_at")
        has_cache = _CACHE.get("conditions") is not None and fetched_at is not None
        expired = (not has_cache) or ((now - fetched_at).total_seconds() >= CACHE_TTL_SECONDS)

        if force_refresh or expired:
            _CACHE["conditions"] = build_conditions(limit_days=7)
            _CACHE["fetched_at"] = datetime.now(PARIS_TZ)

        return _CACHE["conditions"], _CACHE["fetched_at"]


@app.route("/")
def home():
    try:
        force_refresh = request.args.get("force_refresh") == "1"
        conditions, last_refresh_dt = get_cached_conditions(force_refresh=force_refresh)
        if force_refresh:
            return redirect("/")
        now_dt = datetime.now(PARIS_TZ)
        return render_template(
            "index.html",
            conditions=conditions,
            error=None,
            now=last_refresh_dt,
            now_epoch_ms=int(last_refresh_dt.timestamp() * 1000),
        )
    except Exception as exc:
        now_dt = datetime.now(PARIS_TZ)
        return render_template(
            "index.html",
            conditions=[],
            error=str(exc),
            now=now_dt,
            now_epoch_ms=int(now_dt.timestamp() * 1000),
        )


@app.route("/api/conditions")
def api_conditions():
    force_refresh = request.args.get("force_refresh") == "1"
    conditions, _ = get_cached_conditions(force_refresh=force_refresh)
    return jsonify(
        [
            {
                "date": c.day.isoformat(),
                "tide_coefficient": c.tide_coefficient,
                "wind_speed_kn": c.wind_speed_kn,
                "wind_direction_deg": c.wind_direction_deg,
                "wave_height_m": c.wave_height_m,
                "score": c.score,
                "label": c.label,
                "dive_slots": c.dive_slots,
                "meteo_hours_used": c.meteo_hours_used,
                "slot_scores": c.slot_scores,
                "reliability_pct": c.reliability_pct,
                "score_explanation": c.score_explanation,
                "coef_quality": c.coef_quality,
                "wind_quality": c.wind_quality,
                "wave_quality": c.wave_quality,
                "dir_quality": c.dir_quality,
                "dive_slot_items": c.dive_slot_items,
            }
            for c in conditions
        ]
    )


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5055"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)
