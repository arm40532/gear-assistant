#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gear_assistant.py — ผู้ช่วยเลือกสินค้าส่วนตัว (Personal Gear Assistant)
 1) Auto-Categorization        คัดแยกหมวดหมู่อัตโนมัติจากชื่อ/รายละเอียด/รูปภาพ
 2) Inventory + Duplicate Rule สินค้าใหม่ → สกัดสเปก+บันทึกตามลำดับ | สินค้าซ้ำ → อ้างอิงลำดับเดิม
 3) Scenario Matching/Ranking  จัดอันดับสินค้าตามโจทย์การใช้งาน
 4) Compatibility & Red-Flag   ตรวจการจับคู่อุปกรณ์ + เตือนจุดเสี่ยง
 5) Master Inventory Summary   สรุปคลังแยกหมวดและลำดับ
ใช้งาน:  python gear_assistant.py          (โหมดโต้ตอบ)
         python gear_assistant.py --demo   (ดูตัวอย่างการทำงาน)
         python gear_assistant.py --vision (เปิดวิเคราะห์รูปผ่าน Claude API)
"""
from __future__ import annotations

import base64
import difflib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

DB_PATH = Path("inventory.json")
LV = {"danger": "🔴 อันตราย", "warn": "🟠 ระวัง", "info": "ℹ️ ข้อสังเกต", "ok": "🟢 ผ่าน"}
SEVERITY = {"danger": 0, "warn": 1, "info": 2, "ok": 3}

# ════════════════════════ 1) หมวดหมู่ & ฐานความรู้ ════════════════════════
CATEGORIES: dict[str, dict] = {
    "running_carbon": {"label": "รองเท้าวิ่งคาร์บอน", "domain": "running", "keywords": [
        "carbon", "คาร์บอน", "plate", "เพลท", "vaporfly", "alphafly", "adios pro", "metaspeed",
        "endorphin pro", "rocket x", "deviate elite", "sc elite", "cielo x", "super shoe", "รองเท้าแข่ง"]},
    "running_daily": {"label": "รองเท้าวิ่งซ้อม/เทมโป (ไม่มีคาร์บอน)", "domain": "running", "keywords": [
        "pegasus", "novablast", "clifton", "ghost", "kayano", "nimbus", "cumulus", "boston",
        "invincible", "vomero", "bondi", "1080", "daily", "trainer", "รองเท้าวิ่ง", "running shoe", "ซ้อม"]},
    "fishing_rod": {"label": "คันเบ็ด", "domain": "fishing", "keywords": [
        "คันเบ็ด", "คันตีเหยื่อ", "คันสปิน", "คันเบท", "rod", "blank", "ไกด์", "ft", "ฟุต"]},
    "fishing_reel": {"label": "รอกตกปลา", "domain": "fishing", "keywords": [
        "รอก", "reel", "หยดน้ำ", "stradic", "vanford", "twin power", "sedona", "curado", "slx",
        "metanium", "tatula", "steez", "exist", "certate", "fuego", "revros", "drag", "เบรก", "gear ratio"]},
    "fishing_line": {"label": "สายเบ็ด", "domain": "fishing", "keywords": [
        "สาย", "line", "pe", "x4", "x8", "ถัก", "braid", "fluorocarbon", "ฟลูออโร", "nylon",
        "ลีดเดอร์", "leader", "mono"]},
    "fishing_lure": {"label": "เหยื่อปลอม", "domain": "fishing", "keywords": [
        "เหยื่อ", "lure", "กบยาง", "frog", "สปินเนอร์เบท", "spinnerbait", "ปลั๊ก", "crank", "minnow",
        "หนอนยาง", "soft bait", "jig", "ป๊อปเปอร์", "popper", "กระดี่", "spoon"]},
}
DOMAIN_KEYWORDS = {
    "running": ["วิ่ง", "run", "running", "รองเท้า", "shoe", "shoes", "เพซ", "pace", "มาราธอน",
                "marathon", "drop", "stack", "foam", "โฟม"],
    "fishing": ["ตกปลา", "ปลา", "fishing", "เบ็ด", "รอก", "reel", "rod", "pe", "lb", "เหยื่อ", "lure", "ตีเหยื่อ"],
}
# ข้อมูลเชิงคุณภาพที่รู้กันทั่วไป — แก้/เพิ่มเองได้
KNOWN_MODELS = {
    "vaporfly": {"plate": "carbon", "toe_box": "narrow"},
    "alphafly": {"plate": "carbon"}, "metaspeed": {"plate": "carbon"}, "adios pro": {"plate": "carbon"},
    "endorphin speed": {"plate": "nylon"}, "kayano": {"stability": True},
}
POWER_ORDER = ["XUL", "UL", "L", "ML", "M", "MH", "H", "XH", "XXH"]
POWER_PE = {"XUL": (0.1, 0.4), "UL": (0.2, 0.8), "L": (0.4, 1.0), "ML": (0.6, 1.2), "M": (0.8, 1.5),
            "MH": (1.2, 2.5), "H": (2.0, 4.0), "XH": (3.0, 6.0), "XXH": (4.0, 8.0)}
POWER_REEL = {"XUL": (500, 1000), "UL": (500, 2000), "L": (1000, 2500), "ML": (2000, 3000), "M": (2500, 3000),
              "MH": (3000, 4000), "H": (4000, 5000), "XH": (5000, 8000), "XXH": (6000, 10000)}
PE_LB = [(0.4, 8), (0.6, 12), (0.8, 14), (1.0, 18), (1.2, 22), (1.5, 25), (2.0, 30),
         (2.5, 35), (3.0, 40), (4.0, 50), (5.0, 65), (6.0, 80)]
TYPE_TH = {"casting": "เบท(หยดน้ำ)", "spinning": "สปิน"}
LURE_TYPES = {  # เรียงลำดับสำคัญ: กบยางต้องมาก่อน "ยาง"
    "frog": ["กบ", "frog"], "spinnerbait": ["spinnerbait", "สปินเนอร์เบท"], "popper": ["popper", "ป๊อปเปอร์"],
    "plug": ["ปลั๊ก", "minnow", "มินนาว", "crank"], "spoon": ["spoon", "สปูน", "กระดี่"],
    "jig": ["jig", "จิ๊ก"], "soft": ["หนอนยาง", "soft", "ยาง"],
}
FISH_PROFILES = {
    "ช่อน": dict(aliases=["ช่อน", "snakehead"], power=("MH", "XH"), pe=(2.0, 4.0), lure_g=(8, 25),
                 reel="casting", lure_types=["frog", "spinnerbait", "soft"], drag_kg=5.0,
                 note="ช่อนข้างทางซุ่มใต้ผักตบ/หญ้า/สวะ กินแล้วมุดทันที ต้องคันแข็ง สายใหญ่ เบรกตึง แล้วงัดออกจากที่รกให้เร็ว"),
    "ชะโด": dict(aliases=["ชะโด"], power=("H", "XXH"), pe=(3.0, 6.0), lure_g=(15, 50), reel="casting",
                 lure_types=["frog", "spinnerbait", "plug", "soft"], drag_kg=7.0,
                 note="ปลาแรงและฟันคม ใช้ลีดเดอร์หนาและเบรกสูง"),
    "กะพง": dict(aliases=["กะพง", "กระพง", "barramundi"], power=("M", "MH"), pe=(1.2, 2.5), lure_g=(7, 25),
                 reel="any", lure_types=["plug", "soft", "popper", "jig"], drag_kg=5.0,
                 note="เหงือกและปากคม ควรต่อลีดเดอร์ 30–50lb"),
    "ปลาเกล็ด": dict(aliases=["นิล", "ตะเพียน", "กระสูบ", "ปลาเกล็ด", "ปลาเล็ก"], power=("UL", "ML"), pe=(0.3, 1.0),
                     lure_g=(1, 7), reel="spinning", lure_types=["spoon", "plug", "soft", "jig"], drag_kg=2.0,
                     note="ตีเหยื่อเบา ต้องใช้คันอ่อน สายเล็ก และรอกสปินขนาดเล็ก"),
}
ZONE_TH = {"race": "เร็ว/แข่ง (Race)", "tempo": "เทมโป (Tempo)", "steady": "คุมเพซ (Steady)", "easy": "สบาย/สะสมระยะ (Easy)"}

# ════════════════════════ ตัวช่วยทั่วไป ════════════════════════
def _norm(text: str) -> str:
    t = text.lower()
    for a, b in (("–", "-"), ("—", "-"), ("~", "-"), ("’", "'"), ("”", '"')):
        t = t.replace(a, b)
    return f" {t} "

def _hit(text: str, kw: str) -> bool:
    kw = kw.lower()
    if kw.isascii():  # คำอังกฤษต้องไม่ติดตัวอักษรอื่น (กัน "pe" ใน "speed", "carbon" ใน "fluorocarbon")
        return re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", text) is not None
    return kw in text

def _fmt(v) -> str:
    if isinstance(v, bool):
        return "ใช่" if v else "ไม่"
    if isinstance(v, list):
        return "–".join(_fmt(x) for x in v)
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)

def parse_pace(s: str) -> float:
    if ":" in s:
        m, sec = s.split(":")
        return int(m) + int(sec) / 60
    return float(s)

def _fmt_pace(x: float) -> str:
    m, s = int(x), round((x - int(x)) * 60)
    return f"{m + 1}:00" if s == 60 else f"{m}:{s:02d}"

def pe_to_lb(pe: float) -> int:
    return min(PE_LB, key=lambda x: abs(x[0] - pe))[1]

def _known_hints(t: str) -> dict:
    out: dict = {}
    for key, hint in KNOWN_MODELS.items():
        if key in t:
            for k, v in hint.items():
                out.setdefault(k, v)
    return out

def detect_plate(t: str) -> Optional[str]:
    t2 = t.replace("fluorocarbon", "").replace("ฟลูออโรคาร์บอน", "")
    if re.search(r"(?<![a-z])carbon|คาร์บอน", t2):
        return "carbon"
    if re.search(r"nylon|pebax|ไนลอน|tpu plate", t2):
        return "nylon"
    return _known_hints(t2).get("plate")

# ════════════════════════ 1) Auto-Categorization ════════════════════════
def classify(text: str) -> str:
    t = _norm(text)
    head = t[:20]
    cat_scores: dict[str, int] = {}
    for c, meta in CATEGORIES.items():
        sc = sum(_hit(t, k) for k in meta["keywords"])
        if any(k in head for k in meta["keywords"] if not k.isascii()):
            sc += 2  # ชื่อสินค้าไทยมักขึ้นต้นด้วยประเภท เช่น "คันเบ็ด…", "รอก…"
        cat_scores[c] = sc
    dom_scores = {d: sum(_hit(t, k) for k in kws) for d, kws in DOMAIN_KEYWORDS.items()}
    for c, meta in CATEGORIES.items():
        dom_scores[meta["domain"]] += cat_scores[c]
    domain = max(dom_scores, key=dom_scores.get)
    if dom_scores[domain] == 0:
        return "uncategorized"
    pool = {c: s for c, s in cat_scores.items() if CATEGORIES[c]["domain"] == domain}
    best = max(pool, key=pool.get)
    if domain == "running":  # ตัดสินด้วยชนิดเพลทก่อนคีย์เวิร์ด
        plate = detect_plate(t)
        if plate == "carbon":
            return "running_carbon"
        if plate == "nylon":
            return "running_daily"
    return best if pool[best] > 0 else "uncategorized"

# ════════════════════════ สกัดสเปกเชิงลึก ════════════════════════
PRICE_RE = r"(?:฿\s*(\d[\d,]*)|(\d[\d,]*)\s*(?:บาท|thb|฿))"
NUM = r"(\d+(?:\.\d+)?)"

def _running_specs(t: str, category: str) -> dict:
    s: dict = {}
    if m := re.search(r"(\d{3})\s*(?:g|กรัม)(?![a-z])", t):
        s["weight_g"] = int(m.group(1))
    if m := re.search(rf"(?:drop|ดรอป)\s*[:=]?\s*{NUM}", t):
        s["drop_mm"] = float(m.group(1))
    if m := re.search(r"(?:stack|สแต็ก)[^\d]{0,12}(\d{2}(?:\.\d)?)(?:\s*/\s*(\d{2}(?:\.\d)?))?", t):
        s["stack_heel_mm"] = float(m.group(1))
        if m.group(2):
            s["stack_fore_mm"] = float(m.group(2))
    plate = detect_plate(t) or ("carbon" if category == "running_carbon" else None)
    if plate:
        s["plate"] = plate
    if re.search(r"หน้าเท้าแคบ|บีบหน้าเท้า|narrow|toe ?box แคบ", t):
        s["toe_box"] = "narrow"
    elif re.search(r"หน้าเท้ากว้าง|wide|(?<![a-z0-9])[24]e(?![a-z])", t):
        s["toe_box"] = "wide"
    if re.search(r"stability|support|กันล้ม|ซัพพอร์ต", t):
        s["stability"] = True
    return s

def _rod_specs(raw: str, t: str) -> dict:
    s: dict = {}
    m = (re.search(r"power\s*[:=]?\s*(XXH|XH|MH|ML|XUL|UL|M|L|H)(?![A-Za-z])", raw, re.I)
         or re.search(r"(?<![A-Za-z])(XXH|XH|MH|ML|XUL|UL|M|L|H)(?![A-Za-z])", raw))
    if m:
        s["power"] = m.group(1).upper()
    elif re.search(r"อัลตร้าไลท์|ultra ?light", t):
        s["power"] = "UL"
    if m := re.search(r"(\d)\s*'\s*(\d{1,2})", t):
        s["length_ft"] = round(int(m.group(1)) + int(m.group(2)) / 12, 2)
    elif m := re.search(rf"{NUM}\s*(?:ft|ฟุต)", t):
        s["length_ft"] = float(m.group(1))
    if m := re.search(rf"{NUM}\s*-\s*{NUM}\s*lb", t):
        s["line_lb"] = [float(m.group(1)), float(m.group(2))]
    if m := re.search(rf"pe\s*#?\s*{NUM}\s*-\s*{NUM}", t):
        s["pe_range"] = [float(m.group(1)), float(m.group(2))]
    if m := re.search(rf"{NUM}\s*-\s*{NUM}\s*(?:g|กรัม)(?![a-z])", t):
        s["lure_g"] = [float(m.group(1)), float(m.group(2))]
    if re.search(r"เบท|bait|casting|หยดน้ำ", t):
        s["type"] = "casting"
    elif re.search(r"สปิน|spin", t):
        s["type"] = "spinning"
    return s

def _reel_specs(t: str) -> dict:
    s: dict = {}
    if re.search(r"หยดน้ำ|เบท|bait|casting", t):
        s["type"] = "casting"
    elif re.search(r"สปิน|spin", t):
        s["type"] = "spinning"
    if m := re.search(r"(?<![\d.])c?(500|1000|2000|2500|3000|4000|5000|6000|8000)(?!\d)", t):
        s["size"] = int(m.group(1))
        s.setdefault("type", "spinning")
    if m := re.search(rf"(?:drag|เบรก)\D{{0,10}}{NUM}\s*kg", t):
        s["max_drag_kg"] = float(m.group(1))
    if m := re.search(rf"{NUM}\s*:\s*1", t):
        s["gear_ratio"] = float(m.group(1))
    return s

def _line_specs(t: str) -> dict:
    s: dict = {}
    if m := re.search(rf"pe\s*(?:x\d\s*)?#?\s*{NUM}", t):
        s["pe"] = float(m.group(1))
    if m := re.search(rf"{NUM}\s*lb", t):
        s["lb"] = float(m.group(1))
    elif "pe" in s:
        s["lb"], s["lb_estimated"] = pe_to_lb(s["pe"]), True
    if re.search(r"fluoro|ฟลูออโร", t):
        s["material"] = "fluorocarbon"
    elif re.search(r"nylon|mono|ไนลอน", t):
        s["material"] = "mono"
    elif "pe" in s or re.search(r"x4|x8|ถัก|braid", t):
        s["material"] = "braid"
    return s

def _lure_specs(t: str) -> dict:
    s: dict = {}
    if m := re.search(rf"{NUM}\s*(?:g|กรัม)(?![a-z])", t):
        s["weight_g"] = float(m.group(1))
    for typ, kws in LURE_TYPES.items():
        if any(k in t for k in kws):
            s["lure_type"] = typ
            break
    s["weedless"] = bool(re.search(r"weedless|กันสวะ|เบ็ดซ่อน", t)) or s.get("lure_type") in ("frog", "spinnerbait")
    s["treble_hook"] = bool(re.search(r"สามทาง|treble", t)) or (
        s.get("lure_type") in ("plug", "popper") and not s["weedless"])
    return s

def extract_specs(text: str, category: str) -> dict:
    t = _norm(text)
    s: dict = {}
    if m := re.search(PRICE_RE, t):
        s["price_thb"] = int((m.group(1) or m.group(2)).replace(",", ""))
        t = t.replace(m.group(0), " ")  # กันราคาไปปนกับเบอร์รอก
    dom = CATEGORIES.get(category, {}).get("domain")
    if dom == "running":
        s.update(_running_specs(t, category))
        for k, v in _known_hints(t).items():
            s.setdefault(k, v)
    elif category == "fishing_rod":
        s.update(_rod_specs(text, t))
    elif category == "fishing_reel":
        s.update(_reel_specs(t))
    elif category == "fishing_line":
        s.update(_line_specs(t))
    elif category == "fishing_lure":
        s.update(_lure_specs(t))
    return s

# ════════════════════════ 2) ระบบกันข้อมูลซ้ำ ════════════════════════
STOP_PATTERNS = [r"สี\S*", r"color\s*\S+", r"(?<![a-z])(men'?s|women'?s|unisex)(?![a-z])", r"ผู้ชาย|ผู้หญิง",
                 r"รองเท้าวิ่ง", r"running\s*shoes?", r"ไซส์\s*\S+|size\s*\S+"]

def _clean_name(name: str) -> str:
    t = name.lower()
    for p in STOP_PATTERNS:
        t = re.sub(p, " ", t)
    t = re.sub(r"\d+(?:\.\d+)?\s*(?:g|กรัม|mm|kg|บาท)(?![a-z])", " ", t)
    return re.sub(r"(?<![a-z])v(?=\d)", "", t)  # "v4" = "4"

def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9.\u0E00-\u0E7F]", "", _clean_name(name))

def _name_numbers(name: str) -> list[float]:
    return sorted(float(x) for x in re.findall(r"\d+(?:\.\d+)?", _clean_name(name)))

# ════════════════════════ โมเดลข้อมูล ════════════════════════
@dataclass
class Item:
    seq: int          # ลำดับรวมในคลัง
    cat_seq: int      # ลำดับในหมวด
    category: str
    name: str
    key: str
    specs: dict
    raw: str
    added_at: str
    image: Optional[str] = None

    @property
    def label(self) -> str:
        return CATEGORIES.get(self.category, {}).get("label", "ยังไม่ระบุหมวด")

    @property
    def domain(self) -> Optional[str]:
        return CATEGORIES.get(self.category, {}).get("domain")

    def short(self) -> str:
        sp = ", ".join(f"{k}={_fmt(v)}" for k, v in self.specs.items())
        return f"#{self.seq:03d} [{self.label} ลำดับ {self.cat_seq}] {self.name}" + (f"  ({sp})" if sp else "")

# ════════════════════════ 3) Scenario Matching ════════════════════════
def parse_scenario(text: str) -> Optional[dict]:
    t = _norm(text)
    if re.search(r"วิ่ง|(?<![a-z])run|เพซ|pace|มาราธอน|marathon|ฮาล์ฟ", t):
        if m := re.search(rf"{NUM}\s*(?:โล|กิโล|กม|km|k)(?![a-z])", t):
            dist = float(m.group(1))
        elif re.search(r"ฮาล์ฟ|half", t):
            dist = 21.1
        elif re.search(r"มาราธอน|marathon|ฟูล", t):
            dist = 42.2
        else:
            dist = 10.0
        pace = None
        P = r"(\d{1,2}(?::\d{2})?)"
        if m := re.search(rf"(?:เพซ|pace)\s*{P}\s*(?:-|ถึง)\s*{P}", t):
            pace = (parse_pace(m.group(1)), parse_pace(m.group(2)))
        elif m := re.search(rf"(?:เพซ|pace)\s*{P}", t):
            pace = (parse_pace(m.group(1)),) * 2
        avg = sum(pace) / 2 if pace else None
        zone = ("steady" if avg is None else "race" if avg <= 4.75 else
                "tempo" if avg <= 5.5 else "steady" if avg <= 6.25 else "easy")
        return {"domain": "running", "distance_km": dist, "pace": pace, "zone": zone}
    if re.search(r"ตกปลา|ปลา|fishing|ตีเหยื่อ", t):
        fish = next((k for k, p in FISH_PROFILES.items() if any(a in t for a in p["aliases"])), None)
        return {"domain": "fishing", "fish": fish, "profile": FISH_PROFILES.get(fish),
                "weedy": bool(re.search(r"ข้างทาง|สวะ|หญ้า|ผักตบ|บัว|รก|weed", t))}
    return None

def _pace_txt(sc: Optional[dict]) -> str:
    if not sc or not sc.get("pace"):
        return "ไม่ระบุ"
    a, b = sc["pace"]
    return f"{_fmt_pace(a)}–{_fmt_pace(b)} นาที/กม."

def _plate_of(it: Item) -> str:
    return it.specs.get("plate") or ("carbon" if it.category == "running_carbon" else "none")

def _shoe_flags(it: Item, sc: Optional[dict] = None) -> list[tuple[str, str]]:
    sp, plate, f = it.specs, _plate_of(it), []
    zone = sc["zone"] if sc else None
    dist = sc["distance_km"] if sc else None
    if sp.get("toe_box") == "narrow":
        lvl = "warn" if dist is None or dist >= 10 else "info"
        f.append((lvl, "ทรงหน้าเท้าแคบ/บีบหน้าเท้า — ถ้าเท้ากว้างหรือหน้าเท้าบาน เสี่ยงเล็บดำ ชาปลายนิ้ว ห้อเลือด "
                       "ยิ่งระยะ ≥10K ที่เท้าบวมยิ่งชัด → ลองเผื่อครึ่งไซซ์ หรือเลือกรุ่นหน้ากว้าง"))
    if plate == "carbon":
        if zone == "easy":
            f.append(("danger", f"เพซ {_pace_txt(sc)} ช้ากว่าย่านที่เพลทคาร์บอนออกแบบมา — เท้าแตะพื้นนาน "
                                "โฟมสูงนิ่ม+เพลทแข็งทำให้ข้อเท้าบิดง่าย เพิ่มภาระเอ็นร้อยหวาย/น่อง/ฝ่าเท้า "
                                "และเปลืองอายุรองเท้าโดยไม่ได้ประโยชน์ → ใช้ daily trainer แทน"))
        elif zone in ("race", "tempo"):
            f.append(("info", "ถ้ายังไม่เคยใส่คาร์บอน ควรใส่ซ้อมเทมโป 2–3 ครั้งก่อนวันแข่ง ให้น่อง/เอ็นร้อยหวายปรับตัว"))
        elif zone is None:
            f.append(("info", "รองเท้าคาร์บอนเหมาะกับวันแข่ง/เทมโป ไม่ควรใช้ซ้อมทุกวัน — โฟมเสื่อมเร็วกว่ารองเท้าซ้อม"))
    stack = sp.get("stack_heel_mm")
    if stack and stack >= 40:
        lvl = "warn" if plate == "carbon" and zone not in ("race", "tempo") else "info"
        msg = f"ส้นหนา {stack:g}mm — ความมั่นคงด้านข้างลดลง ระวังทางโค้ง/ทางลาด/พื้นไม่เรียบ"
        if stack > 40:
            msg += " (เกิน 40mm ใช้แข่งรายการถนนที่ World Athletics รับรองไม่ได้)"
        f.append((lvl, msg))
    drop = sp.get("drop_mm")
    if drop is not None and drop <= 4:
        f.append(("warn", f"drop ต่ำ {drop:g}mm เพิ่มภาระน่องและเอ็นร้อยหวาย ถ้าปกติใส่ drop 8–10mm ให้ค่อยๆ ปรับ"))
    return f

def _score_shoe(it: Item, sc: dict):
    sp, plate, zone, dist = it.specs, _plate_of(it), sc["zone"], sc["distance_km"]
    score, why = 50.0, []
    if zone in ("race", "tempo"):
        if plate == "carbon":
            score += 25; why.append("เพลทคาร์บอน + โฟมเด้ง คืนพลังงานได้ดีที่สุดในย่านความเร็วนี้")
        elif plate == "nylon":
            score += 12; why.append("เพลทไนลอน/พลาสติก ช่วยส่งแรงระดับหนึ่ง เหมาะเทมโป")
        else:
            score -= 5; why.append("ไม่มีเพลท — ใช้ได้แต่ไม่ช่วยดันความเร็ว")
    elif zone == "steady":
        if plate == "carbon":
            score += 8 if dist >= 21 else -3
            why.append("คาร์บอนช่วยประหยัดแรงช่วงท้ายระยะไกล" if dist >= 21
                       else "ใช้คาร์บอนได้ แต่ระยะ/เพซนี้ยังได้ประโยชน์ไม่เต็มที่")
        else:
            score += 10; why.append("รองเท้าซ้อมคุมเพซได้ดี ทนทาน คุ้มค่าการสึก")
    else:  # easy
        if plate == "carbon":
            score -= 20
        else:
            score += 15; why.append("โฟมนุ่ม ฐานมั่นคง ตรงย่านเพซซ้อม easy/สะสมระยะ")
        if sp.get("stability"):
            score += 3; why.append("มีระบบซัพพอร์ต — ดีถ้าเท้าล้มใน (overpronation)")
    if w := sp.get("weight_g"):
        k = {"race": 2.0, "tempo": 1.5, "steady": 0.8, "easy": 0.4}[zone]
        score += max(-15, min(15, (240 - w) / 10 * k))
        why.append(f"น้ำหนัก {w}g ({'เบา' if w < 220 else 'กลาง' if w <= 260 else 'ค่อนข้างหนัก'})")
    stack = sp.get("stack_heel_mm")
    if stack and dist >= 21:
        if stack >= 35:
            score += 5; why.append(f"ส้น {stack:g}mm cushion พอสำหรับระยะยาว")
        elif stack < 30:
            score -= 5; why.append(f"ส้น {stack:g}mm บางไปสำหรับระยะยาว ขาล้าเร็ว")
    flags = _shoe_flags(it, sc)
    score -= 4 * sum(l == "warn" for l, _ in flags)
    return max(0, min(100, score)), why, flags

def _score_fishing(it: Item, sc: dict):
    p, weedy, fish, sp = sc["profile"], sc["weedy"], sc["fish"], it.specs
    score, why, flags = 50.0, [], []
    if it.category == "fishing_rod":
        lo_i, hi_i = POWER_ORDER.index(p["power"][0]), POWER_ORDER.index(p["power"][1])
        if pw := sp.get("power"):
            i = POWER_ORDER.index(pw)
            if lo_i <= i <= hi_i:
                score += 30; why.append(f"power {pw} อยู่ในช่วงที่เหมาะกับปลา{fish} ({p['power'][0]}–{p['power'][1]})")
            elif i < lo_i:
                score -= 30; flags.append(("danger", f"คัน {pw} อ่อนเกินสำหรับปลา{fish} — งัดปลาออกจากที่รกไม่ขึ้น เสี่ยงคันหัก/ปลาหลุด"))
            else:
                score -= 5; why.append(f"คัน {pw} แข็งเกินโจทย์ ตีเหยื่อเบาไม่ค่อยออก")
        else:
            why.append("ไม่มีข้อมูล power — เพิ่มสเปกเพื่อจัดอันดับให้แม่นขึ้น")
        if lg := sp.get("lure_g"):
            if lg[0] <= p["lure_g"][1] and lg[1] >= p["lure_g"][0]:
                score += 10; why.append(f"ช่วงเหยื่อ {_fmt(lg)} g ครอบคลุมเหยื่อที่ใช้")
            else:
                score -= 10; flags.append(("warn", f"ช่วงเหยื่อของคัน {_fmt(lg)} g ไม่ตรงกับเหยื่อที่ใช้ ({_fmt(list(p['lure_g']))} g)"))
        if typ := sp.get("type"):
            if p["reel"] in ("any", typ):
                score += 10; why.append(f"คัน{TYPE_TH[typ]} ตรงกับสไตล์ที่แนะนำ")
            else:
                score -= 5; why.append(f"โจทย์นี้ระบบ{TYPE_TH[p['reel']]} เหมาะกว่า")
        if weedy and (L := sp.get("length_ft")) and L <= 7.0:
            score += 5; why.append(f"ยาว {L:g} ฟุต คล่องตัว ตีแม่นในที่แคบข้างทาง")
    elif it.category == "fishing_reel":
        typ = sp.get("type")
        if typ and p["reel"] in ("any", typ):
            score += 20; why.append(f"รอก{TYPE_TH[typ]} ตรงโจทย์")
        elif typ:
            score -= 10; why.append(f"ปลา{fish} ในที่รก รอก{TYPE_TH[p['reel']]} คุมเบรก/งัดได้ดีกว่า")
        if (d := sp.get("max_drag_kg")) is not None:
            if d >= p["drag_kg"]:
                score += 15; why.append(f"เบรกสูงสุด {d:g} kg พอสำหรับล็อกปลา")
            else:
                score -= 15; flags.append(("warn", f"เบรกสูงสุด {d:g} kg ต่ำกว่าที่ควร (≥{p['drag_kg']:g} kg) — ล็อกปลาไม่อยู่ ปลามุดสวะ"))
        if weedy and (g := sp.get("gear_ratio")) and g >= 7:
            score += 5; why.append(f"รอบ {g:g}:1 เก็บสายไว ลากปลาออกจากที่รกได้เร็ว")
        if (sz := sp.get("size")) and typ == "spinning":
            lo_sz, hi_sz = POWER_REEL[p["power"][0]][0], POWER_REEL[p["power"][1]][1]
            if lo_sz <= sz <= hi_sz:
                score += 10; why.append(f"เบอร์ {sz} ขนาดเหมาะกับงาน")
            else:
                score -= 10; why.append(f"เบอร์ {sz} ไม่ตรงงาน (ควร {lo_sz}–{hi_sz})")
    elif it.category == "fishing_line":
        lo, hi = p["pe"]
        if (pe := sp.get("pe")) is not None:
            if lo <= pe <= hi:
                score += 30; why.append(f"PE {pe:g} อยู่ในช่วงแนะนำ {lo:g}–{hi:g}")
            elif pe < lo:
                score -= 25; flags.append(("danger", f"PE {pe:g} เล็กเกินสำหรับปลา{fish}" + (" — ถูสวะ/ตอแล้วขาดง่าย" if weedy else "")))
            else:
                score -= 5; why.append(f"PE {pe:g} ใหญ่กว่าที่ต้องการ ระยะตีลดลง")
            if weedy and sp.get("material") == "braid":
                score += 5; why.append("สายถัก PE ตัดผ่านหญ้า/สวะได้ดี")
        elif lb := sp.get("lb"):
            if lb >= pe_to_lb(lo):
                score += 15; why.append(f"{lb:g} lb แรงพอ")
            else:
                score -= 15; flags.append(("warn", f"{lb:g} lb อ่อนเกินโจทย์"))
    elif it.category == "fishing_lure":
        lt = sp.get("lure_type")
        if lt in p["lure_types"]:
            score += 25; why.append(f"เหยื่อประเภท {lt} ได้ผลกับปลา{fish}")
        elif lt:
            score -= 5; why.append(f"เหยื่อประเภท {lt} ไม่ใช่ตัวหลักของโจทย์นี้")
        if (w := sp.get("weight_g")) is not None:
            if p["lure_g"][0] <= w <= p["lure_g"][1]:
                score += 10; why.append(f"น้ำหนัก {w:g} g อยู่ในช่วงเหมาะสม")
            else:
                score -= 5; why.append(f"น้ำหนัก {w:g} g นอกช่วงแนะนำ")
        if weedy:
            if sp.get("weedless"):
                score += 15; why.append("กันสวะ ลากผ่านผักตบ/หญ้าได้")
            elif sp.get("treble_hook"):
                score -= 15; flags.append(("warn", "ตัวเบ็ดสามทางติดสวะ/บัวแทบทุกครั้ง ใช้ข้างทางรกๆ ยาก"))
    return max(0, min(100, score)), why, flags

# ════════════════════════ 4) Compatibility & Red-Flag ════════════════════════
def rod_pe_range(sp: dict) -> Optional[tuple[float, float]]:
    if "pe_range" in sp:
        return tuple(sp["pe_range"])
    return POWER_PE.get(sp.get("power", ""))

def check_compat(items: list[Item], sc: Optional[dict] = None) -> list[tuple[str, str]]:
    f: list[tuple[str, str]] = []
    by = lambda c: [i for i in items if i.category == c]
    rods, reels, lines, lures = by("fishing_rod"), by("fishing_reel"), by("fishing_line"), by("fishing_lure")
    for r in rods:
        pw, rpe = r.specs.get("power", "?"), rod_pe_range(r.specs)
        for ln in lines:
            tag, pe, lb = f"[#{r.seq}×#{ln.seq}]", ln.specs.get("pe"), ln.specs.get("lb")
            if pe is not None and rpe:
                lo, hi = rpe
                if pe > hi:
                    f.append(("danger", f"{tag} สาย PE {pe:g} (~{pe_to_lb(pe)}lb) แข็งแรงเกินคัน {pw} ที่รับได้ PE {lo:g}–{hi:g} "
                                        "→ เมื่อเหยื่อติดตอหรือปลาใหญ่กระชาก สายไม่ขาดแต่ 'คันหัก' แทน, ตั้งเบรกตามกำลังสายก็เกินกำลังคัน, "
                                        f"สายใหญ่+เหยื่อเบาตีไม่ออกและพันไกด์ง่าย → ลดเป็น PE {lo:g}–{hi:g} หรือเปลี่ยนคัน"))
                elif pe < lo:
                    f.append(("warn", f"{tag} สาย PE {pe:g} เล็กกว่าที่คัน {pw} รองรับ (PE {lo:g}–{hi:g}) — ใช้กำลังคันไม่เต็ม เสี่ยงสายขาดตอนอัดปลา/ถูตอ"))
                else:
                    f.append(("ok", f"{tag} PE {pe:g} อยู่ในช่วงของคัน {pw} (PE {lo:g}–{hi:g})"))
            elif lb and (rl := r.specs.get("line_lb")):
                if lb > rl[1] * 1.3:
                    f.append(("danger", f"{tag} สาย {lb:g}lb แรงเกินคัน (รับ {_fmt(rl)}lb) — เสี่ยงคันหัก"))
                elif lb < rl[0]:
                    f.append(("warn", f"{tag} สาย {lb:g}lb อ่อนกว่าช่วงคัน ({_fmt(rl)}lb)"))
                else:
                    f.append(("ok", f"{tag} สาย {lb:g}lb อยู่ในช่วงคัน"))
        for rl_ in reels:
            tag, rt, et, sz = f"[#{r.seq}×#{rl_.seq}]", r.specs.get("type"), rl_.specs.get("type"), rl_.specs.get("size")
            if rt and et and rt != et:
                f.append(("danger", f"{tag} รอก{TYPE_TH[et]} ใช้กับคัน{TYPE_TH[rt]} ไม่ได้ — ตำแหน่ง/ขนาดไกด์และที่จับรอกออกแบบต่างกัน สายเสียดสีและคันรับแรงผิดทิศ"))
            elif rt and et:
                f.append(("ok", f"{tag} ระบบคัน-รอกตรงกัน ({TYPE_TH[rt]})"))
            if et == "spinning" and sz and pw in POWER_REEL:
                lo, hi = POWER_REEL[pw]
                if sz > hi:
                    f.append(("warn", f"{tag} รอกเบอร์ {sz} ใหญ่/หนักเกินคัน {pw} (เหมาะ {lo}–{hi}) — สมดุลเสีย ข้อมือล้า และมักตั้งเบรกเกินกำลังคัน"))
                elif sz < lo:
                    f.append(("warn", f"{tag} รอกเบอร์ {sz} เล็กเกินคัน {pw} (เหมาะ {lo}–{hi}) — เบรกและความจุสายไม่พอ"))
                else:
                    f.append(("ok", f"{tag} รอกเบอร์ {sz} สมดุลกับคัน {pw}"))
        for lu in lures:
            tag, w, lg = f"[#{r.seq}×#{lu.seq}]", lu.specs.get("weight_g"), r.specs.get("lure_g")
            if w and lg:
                if w > lg[1] * 1.2:
                    f.append(("danger", f"{tag} เหยื่อ {w:g} g หนักเกินช่วงคัน ({_fmt(lg)} g) มาก — ตีเต็มแรงเสี่ยงคันหักช่วงปลาย"))
                elif w > lg[1]:
                    f.append(("warn", f"{tag} เหยื่อ {w:g} g เกินช่วงคันเล็กน้อย ({_fmt(lg)} g) — ตีแบบส่ง อย่ากระชาก"))
                elif w < lg[0] * 0.8:
                    f.append(("warn", f"{tag} เหยื่อ {w:g} g เบาเกินคัน ({_fmt(lg)} g) — คันไม่ย้วยตาม ตีไม่ได้ระยะ"))
                else:
                    f.append(("ok", f"{tag} เหยื่อ {w:g} g อยู่ในช่วงคัน"))
    for rl_ in reels:
        for ln in lines:
            pe, et, sz = ln.specs.get("pe"), rl_.specs.get("type"), rl_.specs.get("size")
            tag = f"[#{rl_.seq}×#{ln.seq}]"
            if pe is None:
                continue
            if et == "casting" and pe < 0.8:
                f.append(("warn", f"{tag} PE {pe:g} เล็กเกินสำหรับรอกหยดน้ำ — สายจมกินกันในสปูล ฟูง่าย"))
            if et == "spinning" and sz and sz <= 1000 and pe >= 1.5:
                f.append(("warn", f"{tag} PE {pe:g} ใหญ่เกินสปูลเบอร์ {sz} — ความจุสายน้อย สายดีดเป็นขด พันง่าย"))
    for s in (i for i in items if i.domain == "running"):
        f += [(l, f"[#{s.seq}] {m}") for l, m in _shoe_flags(s, sc)]
    if not f:
        f.append(("info", "ไม่มีคู่อุปกรณ์ที่ตรวจได้ — ต้องมีสเปก เช่น power / PE / ขนาดรอก / ช่วงเหยื่อ"))
    return sorted(f, key=lambda x: SEVERITY[x[0]])

# ════════════════════════ คลังสินค้า ════════════════════════
class Inventory:
    def __init__(self, path: Path | str = DB_PATH,
                 vision_hook: Optional[Callable[[str], str]] = None,
                 spec_hook: Optional[Callable[[str, str], dict]] = None):
        self.path, self.vision_hook, self.spec_hook = Path(path), vision_hook, spec_hook
        self.items: list[Item] = []
        if self.path.exists():
            self.items = [Item(**d) for d in json.loads(self.path.read_text(encoding="utf-8"))]

    def _save(self):
        self.path.write_text(json.dumps([asdict(i) for i in self.items], ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, seq: int) -> Optional[Item]:
        return next((i for i in self.items if i.seq == seq), None)

    def find_duplicate(self, name: str, category: str) -> Optional[Item]:
        key, nums = normalize_name(name), _name_numbers(name)
        for it in self.items:
            if it.key == key:
                return it
            if it.category != category or _name_numbers(it.name) != nums:
                continue  # เลขรุ่นต่างกัน (Pegasus 40 ≠ 41, PE 1.5 ≠ 2.0) = คนละสินค้า
            a, b = sorted((key, it.key), key=len)
            if (len(a) >= 6 and a in b) or difflib.SequenceMatcher(None, key, it.key).ratio() >= 0.88:
                return it
        return None

    # ── 1+2) เพิ่มสินค้า ──
    def add(self, name: str, description: str = "", image_path: Optional[str] = None,
            category: Optional[str] = None) -> tuple[Item, bool]:
        vision_text = ""
        if image_path:
            if not self.vision_hook:
                raise RuntimeError("ยังไม่ได้ตั้ง vision hook (รันด้วย --vision)")
            vision_text = self.vision_hook(image_path)
            if not name:
                name = vision_text.split("|")[0].strip()[:80]
        if not name:
            raise ValueError("ต้องมีชื่อสินค้า")
        text = f"{name} {description} {vision_text}".strip()
        cat = category or classify(text)
        if dup := self.find_duplicate(name, cat):
            return dup, False
        specs = extract_specs(text, cat)
        if self.spec_hook:
            specs.update({k: v for k, v in (self.spec_hook(text, cat) or {}).items() if v is not None})
        item = Item(seq=max((i.seq for i in self.items), default=0) + 1,
                    cat_seq=max((i.cat_seq for i in self.items if i.category == cat), default=0) + 1,
                    category=cat, name=name, key=normalize_name(name), specs=specs, raw=text,
                    added_at=datetime.now().isoformat(timespec="seconds"), image=image_path)
        self.items.append(item)
        self._save()
        return item, True

    def add_report(self, *a, **kw) -> str:
        item, new = self.add(*a, **kw)
        if new:
            return f"✅ สินค้าใหม่ → บันทึกเป็น {item.short()}"
        return f"♻️ มีในคลังแล้ว (ไม่เพิ่มซ้ำ) → อ้างอิงลำดับเดิม:\n   {item.short()}"

    # ── 3) จัดอันดับตามโจทย์ ──
    def ask(self, text: str) -> str:
        sc = parse_scenario(text)
        if not sc:
            return "❓ ยังตีความโจทย์ไม่ออก ลองแบบ 'วิ่ง 10 โล เพซ 6-7' หรือ 'ตกปลาช่อนข้างทาง'"
        return self._ask_running(sc) if sc["domain"] == "running" else self._ask_fishing(sc)

    def _ask_running(self, sc: dict) -> str:
        pool = [i for i in self.items if i.domain == "running"]
        if not pool:
            return "คลังยังไม่มีรองเท้าวิ่ง — เพิ่มก่อนด้วยคำสั่ง add"
        out = [f"🏃 โจทย์: วิ่ง {sc['distance_km']:g} กม. | เพซ {_pace_txt(sc)} | โซน: {ZONE_TH[sc['zone']]}"]
        ranked = sorted(((_score_shoe(i, sc), i) for i in pool), key=lambda x: -x[0][0])
        for n, ((score, why, flags), it) in enumerate(ranked, 1):
            out.append(f"\n{n}. {it.short()}\n   คะแนน {score:.0f}/100")
            out += [f"   ✓ {w}" for w in why] + [f"   {LV[l]}: {m}" for l, m in flags]
        out.append(f"\n👉 ตอบโจทย์ที่สุด: #{ranked[0][1].seq:03d} {ranked[0][1].name}")
        return "\n".join(out)

    def _ask_fishing(self, sc: dict) -> str:
        p = sc["profile"]
        if not p:
            return f"ยังไม่มีโปรไฟล์ปลาชนิดนี้ — ตอนนี้รองรับ: {', '.join(FISH_PROFILES)} (เพิ่มได้ใน FISH_PROFILES)"
        out = [f"🎣 โจทย์: ปลา{sc['fish']}" + (" | สภาพที่รก/ข้างทาง" if sc["weedy"] else ""),
               f"💡 {p['note']}",
               f"🎯 สเปกเป้าหมาย: คัน {p['power'][0]}–{p['power'][1]} | PE {_fmt(list(p['pe']))} | "
               f"เหยื่อ {_fmt(list(p['lure_g']))} g | รอก {TYPE_TH.get(p['reel'], 'ได้ทั้งสองแบบ')} | เบรก ≥{p['drag_kg']:g} kg"]
        best = []
        for cat in ("fishing_rod", "fishing_reel", "fishing_line", "fishing_lure"):
            pool = [i for i in self.items if i.category == cat]
            out.append(f"\n▸ {CATEGORIES[cat]['label']}")
            if not pool:
                out.append("   (ยังไม่มีในคลัง)")
                continue
            ranked = sorted(((_score_fishing(i, sc), i) for i in pool), key=lambda x: -x[0][0])
            for n, ((score, why, flags), it) in enumerate(ranked, 1):
                out.append(f"  {n}. {it.short()} — {score:.0f}/100")
                out += [f"     ✓ {w}" for w in why] + [f"     {LV[l]}: {m}" for l, m in flags]
            best.append(ranked[0][1])
        if len(best) >= 2:
            out.append("\n🧩 ชุดแนะนำ (อันดับ 1 ของแต่ละหมวด) — ตรวจความเข้ากันได้:")
            out += [f"   {LV[l]}: {m}" for l, m in check_compat(best, sc)]
        return "\n".join(out)

    # ── 4) ตรวจความเข้ากันได้ ──
    def check(self, seqs: list[int], scenario_text: Optional[str] = None) -> str:
        items = [self.get(s) for s in seqs]
        if missing := [s for s, i in zip(seqs, items) if i is None]:
            return f"ไม่พบลำดับ {missing} ในคลัง"
        sc = parse_scenario(scenario_text) if scenario_text else None
        out = ["🔎 ตรวจความเข้ากันได้:"] + [f"   • {i.short()}" for i in items] + [""]
        out += [f"{LV[l]}: {m}" for l, m in check_compat(items, sc)]
        return "\n".join(out)

    # ── 5) สรุปคลัง ──
    def summary(self) -> str:
        out = ["═══════ MASTER INVENTORY ═══════", f"ทั้งหมด {len(self.items)} รายการ"]
        for cat in list(CATEGORIES) + ["uncategorized"]:
            group = sorted((i for i in self.items if i.category == cat), key=lambda x: x.cat_seq)
            if group:
                out.append(f"\n▸ {group[0].label} ({len(group)} รายการ)")
                for i in group:
                    sp = ", ".join(f"{k}={_fmt(v)}" for k, v in i.specs.items())
                    out.append(f"   {i.cat_seq}. (#{i.seq:03d}) {i.name}" + (f"  [{sp}]" if sp else ""))
        return "\n".join(out)

# ════════════════════════ Vision hook (ไม่บังคับ) ════════════════════════
def make_claude_vision_hook(model: str = "claude-sonnet-4-5") -> Callable[[str], str]:
    """ต้อง pip install anthropic และตั้งค่า ANTHROPIC_API_KEY — เปลี่ยน model เป็นรุ่นที่คุณใช้ได้"""
    import anthropic
    client = anthropic.Anthropic()
    prompt = ("ดูรูปสินค้าแล้วตอบบรรทัดเดียวรูปแบบ: <แบรนด์ รุ่น> | <สเปก> "
              "รองเท้า: น้ำหนัก g, stack x/y mm, drop mm, carbon/nylon plate, หน้าเท้าแคบ/กว้าง | "
              "คันเบ็ด: power UL/L/ML/M/MH/H, คันสปิน/คันเบท, x-ylb, PE x-y, x-yg | "
              "รอก: สปิน/หยดน้ำ, เบอร์, drag x kg, x:1 | สาย: PE x, xlb | เหยื่อ: ประเภท, x g "
              "ค่าที่ไม่แน่ใจให้เว้นไว้ ห้ามเดา")

    def hook(path: str) -> str:
        p = Path(path)
        media = {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(p.suffix.lower(), "image/jpeg")
        data = base64.standard_b64encode(p.read_bytes()).decode()
        msg = client.messages.create(model=model, max_tokens=400, messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}},
            {"type": "text", "text": prompt}]}])
        return msg.content[0].text.strip()
    return hook

# ════════════════════════ CLI ════════════════════════
HELP = """คำสั่ง:
  add <ชื่อสินค้า> | <สเปก/รายละเอียด>     เพิ่มสินค้า (คัดหมวด + กันซ้ำอัตโนมัติ)
  img <path รูป> | <ชื่อ (ถ้ามี)>          เพิ่มจากรูป (ต้องรันด้วย --vision)
  ask <โจทย์>                              จัดอันดับตามสถานการณ์
  check <ลำดับ> <ลำดับ> ... [| โจทย์]      ตรวจความเข้ากันได้ + จุดเสี่ยง
  show <ลำดับ>                             ดูสินค้าตามลำดับ
  list                                     สรุปคลังทั้งหมด
  help / quit"""

def demo():
    p = Path("demo_inventory.json")
    p.unlink(missing_ok=True)
    inv = Inventory(p)
    samples = [  # ตัวเลขสเปกเป็นค่าตัวอย่าง — ใส่ค่าจริงของคุณเอง
        ("Nike Vaporfly 3", "carbon plate 196g stack 40/32mm drop 8mm"),
        ("ASICS Metaspeed Sky Paris", "carbon plate 190g stack 39/34mm drop 5mm"),
        ("ASICS Novablast 4", "daily trainer 255g stack 41.5/33.5mm drop 8mm"),
        ("Nike Pegasus 41", "daily trainer 280g stack 37/27mm drop 10mm"),
        ("ASICS Gel-Kayano 31", "stability 300g stack 40/32mm drop 8mm หน้าเท้ากว้าง 2E"),
        ("คันเบท Abu Garcia MH 6'6\"", "power MH line 12-25lb PE 1.5-3 lure 10-28g"),
        ("คันสปิน UL 6'0\"", "power UL 2-6lb lure 1-5g"),
        ("รอกหยดน้ำ Shimano SLX", "gear 7.2:1 drag 5.5kg"),
        ("รอกสปิน Shimano Sedona 1000", "drag 3kg"),
        ("สาย PE X8 2.0", "30lb ถัก 8"),
        ("สาย PE X4 0.6", ""),
        ("เหยื่อกบยาง Thunder Frog", "13g weedless"),
        ("ปลั๊ก minnow 5g", "ตัวเบ็ดสามทาง"),
    ]
    for n, d in samples:
        print(inv.add_report(n, d))
    print(inv.add_report("nike vaporfly 3 สีชมพู"))  # ← สินค้าซ้ำ
    print("\n" + inv.summary())
    for q in ("วิ่ง 5 โล เพซ 4-5", "วิ่ง 10 โล เพซ 6-7", "ตกปลาช่อนข้างทาง"):
        print("\n" + "─" * 60 + "\n" + inv.ask(q))
    print("\n" + "─" * 60 + "\n" + inv.check([7, 10, 9]))  # คัน UL + PE 2.0 + รอก 1000

def main():
    if "--demo" in sys.argv:
        return demo()
    inv = Inventory(vision_hook=make_claude_vision_hook() if "--vision" in sys.argv else None)
    print("🛒 Personal Gear Assistant\n" + HELP)
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        cmd, _, arg = line.partition(" ")
        cmd = cmd.lower()
        try:
            if cmd in ("quit", "exit"):
                break
            elif cmd == "help":
                print(HELP)
            elif cmd == "add":
                name, _, desc = arg.partition("|")
                print(inv.add_report(name.strip(), desc.strip()))
            elif cmd == "img":
                path, _, name = arg.partition("|")
                print(inv.add_report(name.strip(), image_path=path.strip()))
            elif cmd == "ask":
                print(inv.ask(arg))
            elif cmd == "check":
                nums, _, sc = arg.partition("|")
                print(inv.check([int(x) for x in re.findall(r"\d+", nums)], sc.strip() or None))
            elif cmd == "show":
                it = inv.get(int(arg))
                print(it.short() if it else "ไม่พบลำดับนี้")
            elif cmd == "list":
                print(inv.summary())
            elif line:
                print("ไม่รู้จักคำสั่ง — พิมพ์ help")
        except Exception as e:
            print(f"⚠️ {e}")

if __name__ == "__main__":
    main()