#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py — เว็บแอป Personal Gear Assistant (Streamlit)
วางไว้โฟลเดอร์เดียวกับ gear_assistant.py แล้วรัน:  streamlit run app.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import gear_assistant as ga

st.set_page_config(page_title="Personal Gear Assistant", page_icon="🛒", layout="wide")

# ════════════════════════ ค่าคงที่ฝั่ง UI ════════════════════════
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
ALL_CATS = list(ga.CATEGORIES) + ["uncategorized"]
CAT_LABEL = {c: m["label"] for c, m in ga.CATEGORIES.items()} | {"uncategorized": "ยังไม่ระบุหมวด"}
CAT_ICON = {"running_carbon": "⚡", "running_daily": "👟", "fishing_rod": "🎣", "fishing_reel": "⚙️",
            "fishing_line": "🧵", "fishing_lure": "🐸", "uncategorized": "📦"}
SPEC_TH = {
    "price_thb": "ราคา (บาท)", "weight_g": "น้ำหนัก (g)", "drop_mm": "Drop (mm)",
    "stack_heel_mm": "Stack ส้น (mm)", "stack_fore_mm": "Stack หน้าเท้า (mm)", "plate": "เพลท",
    "toe_box": "หน้าเท้า", "stability": "ซัพพอร์ต", "power": "Power", "length_ft": "ความยาว (ฟุต)",
    "line_lb": "สายที่รับได้ (lb)", "pe_range": "PE ที่รับได้", "lure_g": "เหยื่อที่รับได้ (g)",
    "type": "ระบบ", "size": "เบอร์รอก", "max_drag_kg": "เบรกสูงสุด (kg)", "gear_ratio": "อัตราทด",
    "pe": "PE", "lb": "แรงดึง (lb)", "lb_estimated": "lb ประมาณจาก PE", "material": "วัสดุ",
    "lure_type": "ประเภทเหยื่อ", "weedless": "กันสวะ", "treble_hook": "เบ็ดสามทาง",
}
VAL_TH = {"carbon": "คาร์บอน", "nylon": "ไนลอน", "narrow": "แคบ", "wide": "กว้าง",
          "casting": "เบท (หยดน้ำ)", "spinning": "สปิน", "braid": "PE ถัก",
          "fluorocarbon": "ฟลูออโรคาร์บอน", "mono": "ไนลอน/โมโน"}
FLAG_UI = {"danger": (st.error, "🔴"), "warn": (st.warning, "🟠"),
           "info": (st.info, "💡"), "ok": (st.success, "🟢")}
MEDAL = ["🥇", "🥈", "🥉"]
PAGES = ["➕ เพิ่มสินค้า", "🎯 จับคู่ตามโจทย์", "🔎 ตรวจความเข้ากันได้", "📦 คลังสินค้า"]
SAMPLES = [  # ตัวเลขสเปกเป็นค่าตัวอย่าง
    ("Nike Vaporfly 3", "carbon plate 196g stack 40/32mm drop 8mm หน้าเท้าแคบ"),
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


# ════════════════════════ คลังสินค้า (โหลดครั้งเดียว) ════════════════════════
@st.cache_resource
def get_inventory() -> ga.Inventory:
    hook = None
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            hook = ga.make_claude_vision_hook()
        except Exception as e:  # เช่น ยังไม่ได้ติดตั้ง anthropic
            print("vision disabled:", e)
    return ga.Inventory(ga.DB_PATH, vision_hook=hook)


inv = get_inventory()
ss = st.session_state
ss.setdefault("upl_key", 0)


# ════════════════════════ ตัวช่วยแสดงผล ════════════════════════
def fmt_val(v) -> str:
    return VAL_TH.get(v, v) if isinstance(v, str) else ga._fmt(v)


def spec_text(specs: dict) -> str:
    return " · ".join(f"{SPEC_TH.get(k, k)}: {fmt_val(v)}" for k, v in specs.items())


def flag_box(level: str, msg: str):
    fn, icon = FLAG_UI[level]
    fn(msg, icon=icon)


def item_card(it: ga.Item, manage: bool = False):
    with st.container(border=True):
        if it.image and Path(it.image).exists():
            c_img, c_body = st.columns([1, 4])
            c_img.image(it.image, width=120)
        else:
            c_body = st.container()
        with c_body:
            st.markdown(f"**#{it.seq:03d} · {it.name}**")
            st.caption(f"{CAT_ICON.get(it.category, '📦')} {it.label} · ลำดับในหมวด {it.cat_seq} · "
                       f"บันทึกเมื่อ {it.added_at.replace('T', ' ')}")
            st.write(spec_text(it.specs) or "ยังไม่มีสเปก — เพิ่มได้ในเมนูแก้ไข")
        if manage:
            manage_box(it)


def manage_box(it: ga.Item):
    with st.expander("✏️ แก้ไข / ลบ"):
        new_name = st.text_input("ชื่อสินค้า", it.name, key=f"en_{it.seq}")
        new_cat = st.selectbox("หมวดหมู่", ALL_CATS, index=ALL_CATS.index(it.category),
                               format_func=CAT_LABEL.get, key=f"ec_{it.seq}")
        new_specs = st.text_area("สเปก (JSON)", json.dumps(it.specs, ensure_ascii=False, indent=2),
                                 key=f"es_{it.seq}", height=160)
        c1, c2, c3 = st.columns([1, 1, 2])
        if c1.button("💾 บันทึก", key=f"save_{it.seq}", type="primary"):
            try:
                specs = json.loads(new_specs)
                if not isinstance(specs, dict):
                    raise ValueError
            except Exception:
                st.error("รูปแบบ JSON ไม่ถูกต้อง")
                return
            if new_cat != it.category:  # ย้ายหมวด → ต่อท้ายลำดับของหมวดใหม่
                it.cat_seq = max((i.cat_seq for i in inv.items if i.category == new_cat), default=0) + 1
                it.category = new_cat
            it.name = new_name.strip() or it.name
            it.key, it.specs = ga.normalize_name(it.name), specs
            inv._save()
            st.rerun()
        sure = c3.checkbox("ยืนยันการลบ", key=f"sure_{it.seq}")
        if c2.button("🗑️ ลบ", key=f"del_{it.seq}", disabled=not sure):
            inv.items.remove(it)
            inv._save()
            st.rerun()


def rank_row(n: int, it: ga.Item, score: float, why: list[str], flags: list[tuple[str, str]]):
    with st.container(border=True):
        c1, c2 = st.columns([4, 1])
        badge = MEDAL[n] if n < 3 else f"{n + 1}."
        c1.markdown(f"#### {badge} #{it.seq:03d} {it.name}")
        c1.caption(f"{it.label} · {spec_text(it.specs)}")
        c2.metric("คะแนน", f"{score:.0f}/100")
        st.progress(int(score))
        for w in why:
            st.markdown(f"✓ {w}")
        for lvl, msg in flags:
            flag_box(lvl, msg)


# ════════════════════════ หน้า 1: เพิ่มสินค้า ════════════════════════
def do_add():
    name, desc = ss.f_name.strip(), ss.f_desc.strip()
    cat = None if ss.f_cat == "auto" else ss.f_cat
    upl = ss.get(f"f_img_{ss.upl_key}")
    img_path = None
    if upl:
        img_path = str(UPLOAD_DIR / f"{datetime.now():%Y%m%d%H%M%S}_{upl.name}")
        Path(img_path).write_bytes(upl.getvalue())
    try:
        if img_path and inv.vision_hook:  # วิเคราะห์รูปด้วย AI
            item, new = inv.add(name, desc, image_path=img_path, category=cat)
        else:
            if not name:
                raise ValueError("กรุณาใส่ชื่อสินค้า")
            item, new = inv.add(name, desc, category=cat)
            if new and img_path:  # ไม่มี vision → แนบรูปไว้ดูอย่างเดียว
                item.image = img_path
                inv._save()
    except Exception as e:
        ss.add_result = ("error", str(e))
        return
    if not new and img_path:
        Path(img_path).unlink(missing_ok=True)
    ss.add_result = ("new" if new else "dup", item.seq)
    ss.f_name, ss.f_desc = "", ""
    ss.upl_key += 1  # ล้างช่องอัปโหลดรูป


def page_add():
    st.header("➕ เพิ่มสินค้าเข้าคลัง")
    st.caption("ระบบคัดหมวด สกัดสเปก และตรวจของซ้ำให้อัตโนมัติ")

    if res := ss.get("add_result"):
        kind, val = res
        if kind == "error":
            st.error(val, icon="⚠️")
        elif (it := inv.get(val)):
            if kind == "new":
                st.success(f"บันทึกสินค้าใหม่แล้ว → ลำดับรวม #{it.seq:03d} · {it.label} ลำดับ {it.cat_seq}", icon="✅")
            else:
                st.info("สินค้านี้มีในคลังแล้ว ระบบไม่เพิ่มซ้ำ — อ้างอิงข้อมูลจากลำดับเดิม:", icon="♻️")
            item_card(it)

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.text_input("ชื่อสินค้า", key="f_name", placeholder="เช่น Nike Vaporfly 3 / คันเบท MH 6'6\"")
        st.text_area("สเปก / รายละเอียด", key="f_desc", height=110,
                     placeholder="เช่น carbon plate 196g stack 40/32mm drop 8mm / power MH PE 1.5-3 lure 10-28g")
        st.selectbox("หมวดหมู่", ["auto"] + list(ga.CATEGORIES), key="f_cat",
                     format_func=lambda c: "🤖 ให้ระบบเลือกอัตโนมัติ" if c == "auto" else CAT_LABEL[c])
        st.file_uploader("รูปสินค้า (ไม่บังคับ)", type=["png", "jpg", "jpeg", "webp"], key=f"f_img_{ss.upl_key}",
                         help="ถ้าเปิดระบบวิเคราะห์รูป จะอ่านชื่อและสเปกจากรูปให้ ถ้าไม่เปิด จะแนบรูปไว้ดูอย่างเดียว")
        st.button("บันทึกเข้าคลัง", type="primary", on_click=do_add)

    with right:  # พรีวิวแบบเรียลไทม์ก่อนบันทึก
        st.subheader("👀 พรีวิว")
        name, desc = ss.get("f_name", "").strip(), ss.get("f_desc", "").strip()
        if upl := ss.get(f"f_img_{ss.upl_key}"):
            st.image(upl, width=200)
        if not name:
            st.caption("พิมพ์ชื่อสินค้าเพื่อดูหมวด สเปก และผลตรวจของซ้ำ"
                       + (" (หรืออัปโหลดรูปให้ระบบอ่านชื่อเอง)" if inv.vision_hook else ""))
        else:
            text = f"{name} {desc}"
            cat = ss.f_cat if ss.f_cat != "auto" else ga.classify(text)
            st.markdown(f"**หมวดที่ตรวจพบ:** {CAT_ICON.get(cat, '📦')} {CAT_LABEL[cat]}")
            if dup := inv.find_duplicate(name, cat):
                st.warning(f"ซ้ำกับสินค้าเดิม #{dup.seq:03d} {dup.name} — กดบันทึกแล้วระบบจะดึงข้อมูลเดิมมาแสดงแทน", icon="♻️")
            else:
                nxt = max((i.seq for i in inv.items), default=0) + 1
                nxt_cat = max((i.cat_seq for i in inv.items if i.category == cat), default=0) + 1
                st.success(f"สินค้าใหม่ → จะบันทึกเป็น #{nxt:03d} (ลำดับ {nxt_cat} ในหมวด)", icon="🆕")
            specs = ga.extract_specs(text, cat)
            if specs:
                st.dataframe(pd.DataFrame([{"สเปก": SPEC_TH.get(k, k), "ค่า": fmt_val(v)} for k, v in specs.items()]),
                             hide_index=True)
            else:
                st.caption("ยังสกัดสเปกไม่ได้ — ลองใส่ตัวเลขในช่องรายละเอียด")
            if ga.CATEGORIES.get(cat, {}).get("domain") == "running":
                tmp = ga.Item(0, 0, cat, name, "", specs, text, "")
                for lvl, msg in ga._shoe_flags(tmp):
                    flag_box(lvl, msg)

    with st.expander("📋 เพิ่มหลายรายการพร้อมกัน"):
        bulk = st.text_area("หนึ่งบรรทัดต่อหนึ่งสินค้า รูปแบบ:  ชื่อ | สเปก", key="bulk", height=150,
                            placeholder="Nike Vaporfly 3 | carbon plate 196g\nสาย PE X8 2.0 | 30lb")
        if st.button("เพิ่มทั้งหมด"):
            for line in filter(str.strip, bulk.splitlines()):
                name, _, desc = line.partition("|")
                try:
                    it, new = inv.add(name.strip(), desc.strip())
                    if new:
                        st.success(f"ใหม่ → #{it.seq:03d} {it.name} ({it.label})", icon="✅")
                    else:
                        st.info(f"ซ้ำ → อ้างอิงลำดับเดิม #{it.seq:03d} {it.name}", icon="♻️")
                except Exception as e:
                    st.error(f"{line}: {e}")


# ════════════════════════ หน้า 2: จับคู่ตามโจทย์ ════════════════════════
def render_running(sc: dict):
    m = st.columns(3)
    m[0].metric("ระยะทาง", f"{sc['distance_km']:g} กม.")
    m[1].metric("เพซ", ga._pace_txt(sc))
    m[2].metric("โซนความเร็ว", ga.ZONE_TH[sc["zone"]])
    pool = [i for i in inv.items if i.domain == "running"]
    if not pool:
        st.info("คลังยังไม่มีรองเท้าวิ่ง — เพิ่มสินค้าก่อน")
        return
    ranked = sorted(((ga._score_shoe(i, sc), i) for i in pool), key=lambda x: -x[0][0])
    (top_score, _, _), top = ranked[0]
    st.success(f"ตอบโจทย์ที่สุด: #{top.seq:03d} {top.name} ({top_score:.0f}/100)", icon="👉")
    for n, ((score, why, flags), it) in enumerate(ranked):
        rank_row(n, it, score, why, flags)


def render_fishing(sc: dict):
    p = sc["profile"]
    if not p:
        st.warning(f"ยังไม่มีโปรไฟล์ปลาชนิดนี้ — ตอนนี้รองรับ: {', '.join(ga.FISH_PROFILES)}")
        return
    st.info(p["note"], icon="💡")
    m = st.columns(5)
    m[0].metric("Power คัน", f"{p['power'][0]}–{p['power'][1]}")
    m[1].metric("สาย PE", f"{p['pe'][0]:g}–{p['pe'][1]:g}")
    m[2].metric("น้ำหนักเหยื่อ", f"{p['lure_g'][0]}–{p['lure_g'][1]} g")
    m[3].metric("ระบบรอก", ga.TYPE_TH.get(p["reel"], "ได้ทั้งสองแบบ"))
    m[4].metric("เบรกขั้นต่ำ", f"{p['drag_kg']:g} kg")
    best = []
    for cat in ("fishing_rod", "fishing_reel", "fishing_line", "fishing_lure"):
        pool = [i for i in inv.items if i.category == cat]
        with st.expander(f"{CAT_ICON[cat]} {CAT_LABEL[cat]} ({len(pool)} รายการ)", expanded=True):
            if not pool:
                st.caption("ยังไม่มีในคลัง")
                continue
            ranked = sorted(((ga._score_fishing(i, sc), i) for i in pool), key=lambda x: -x[0][0])
            for n, ((score, why, flags), it) in enumerate(ranked):
                rank_row(n, it, score, why, flags)
            best.append(ranked[0][1])
    if len(best) >= 2:
        st.subheader("🧩 ชุดแนะนำ (อันดับ 1 ของแต่ละหมวด)")
        st.markdown(" ＋ ".join(f"**#{i.seq:03d}** {i.name}" for i in best))
        for lvl, msg in ga.check_compat(best, sc):
            flag_box(lvl, msg)


def page_match():
    st.header("🎯 จับคู่สินค้าตามโจทย์การใช้งาน")
    mode = st.radio("วิธีใส่โจทย์", ["✍️ พิมพ์โจทย์", "🎛️ เลือกจากตัวเลือก"], horizontal=True)
    if mode.startswith("✍️"):
        examples = ["วิ่ง 5 โล เพซ 4-5", "วิ่ง 10 โล เพซ 6-7", "วิ่งฮาล์ฟ เพซ 5:30-6:00", "ตกปลาช่อนข้างทาง"]
        for col, ex in zip(st.columns(len(examples)), examples):
            col.button(ex, on_click=lambda e=ex: ss.update(q=e))
        q = st.text_input("โจทย์ / สถานการณ์", key="q", placeholder="เช่น วิ่ง 10 โล เพซ 6-7 หรือ ตกปลาช่อนข้างทาง")
    else:
        dom = st.radio("ประเภท", ["🏃 วิ่ง", "🎣 ตกปลา"], horizontal=True)
        if dom.startswith("🏃"):
            c1, c2 = st.columns(2)
            dist = c1.number_input("ระยะทาง (กม.)", 1.0, 100.0, 10.0, step=0.5)
            a, b = c2.slider("ช่วงเพซ (นาที/กม.)", 3.0, 9.0, (5.0, 6.0), step=0.25)
            c2.caption(f"= {ga._fmt_pace(a)} – {ga._fmt_pace(b)} นาที/กม.")
            q = f"วิ่ง {dist:g} โล เพซ {ga._fmt_pace(a)}-{ga._fmt_pace(b)}"
        else:
            c1, c2 = st.columns(2)
            fish = c1.selectbox("ชนิดปลา", list(ga.FISH_PROFILES))
            weedy = c2.checkbox("ตกข้างทาง / ที่รก (ผักตบ หญ้า สวะ)", value=True)
            q = f"ตกปลา{fish}" + ("ข้างทาง" if weedy else "")
        st.caption(f"โจทย์ที่ใช้: {q}")

    if not q:
        st.info("ใส่โจทย์เพื่อเริ่มจัดอันดับ")
        return
    sc = ga.parse_scenario(q)
    if not sc:
        st.warning("ยังตีความโจทย์ไม่ออก ลองพิมพ์แบบ 'วิ่ง 10 โล เพซ 6-7' หรือ 'ตกปลาช่อนข้างทาง'")
        return
    st.divider()
    render_running(sc) if sc["domain"] == "running" else render_fishing(sc)


# ════════════════════════ หน้า 3: ตรวจความเข้ากันได้ ════════════════════════
def page_compat():
    st.header("🔎 ตรวจความเข้ากันได้ & จุดเสี่ยง")
    if not inv.items:
        st.info("คลังยังว่าง — เพิ่มสินค้าก่อน")
        return
    sel = st.multiselect("เลือกอุปกรณ์ที่จะใช้ร่วมกัน", [i.seq for i in inv.items],
                         format_func=lambda s: f"#{s:03d} {inv.get(s).name} · {inv.get(s).label}",
                         placeholder="เช่น คัน + รอก + สาย + เหยื่อ หรือรองเท้า 1 คู่")
    sc_text = st.text_input("โจทย์ประกอบ (ไม่บังคับ)", placeholder="เช่น วิ่ง 10 โล เพซ 6-7 — ใช้ประเมินรองเท้าตามย่านความเร็ว")
    if not sel:
        return
    items = [inv.get(s) for s in sel]
    flags = ga.check_compat(items, ga.parse_scenario(sc_text) if sc_text else None)
    m = st.columns(4)
    for col, (lvl, label) in zip(m, [("danger", "🔴 อันตราย"), ("warn", "🟠 ระวัง"), ("info", "💡 ข้อสังเกต"), ("ok", "🟢 ผ่าน")]):
        col.metric(label, sum(l == lvl for l, _ in flags))
    st.divider()
    for lvl, msg in flags:
        flag_box(lvl, msg)


# ════════════════════════ หน้า 4: คลังสินค้า ════════════════════════
def load_samples():
    for n, d in SAMPLES:
        inv.add(n, d)


def clear_all():
    inv.items.clear()
    inv._save()


def page_inventory():
    st.header("📦 คลังสินค้า (Master Inventory)")
    if not inv.items:
        st.info("คลังยังว่าง — เพิ่มสินค้าเอง หรือลองโหลดข้อมูลตัวอย่าง")
        st.button("โหลดข้อมูลตัวอย่าง", on_click=load_samples)
        return

    m = st.columns(4)
    m[0].metric("ทั้งหมด", len(inv.items))
    m[1].metric("🏃 ของวิ่ง", sum(i.domain == "running" for i in inv.items))
    m[2].metric("🎣 ของตกปลา", sum(i.domain == "fishing" for i in inv.items))
    m[3].metric("หมวดที่ใช้งาน", len({i.category for i in inv.items}))

    c1, c2, c3 = st.columns([2, 2, 1])
    q = c1.text_input("🔍 ค้นหา (ชื่อ, สเปก หรือเลขลำดับ เช่น 7)").strip().lower().lstrip("#")
    cats = c2.multiselect("กรองหมวด", ALL_CATS, format_func=CAT_LABEL.get, placeholder="ทุกหมวด")
    view = c3.radio("มุมมอง", ["การ์ด", "ตาราง"], horizontal=True)

    def match(it: ga.Item) -> bool:
        if cats and it.category not in cats:
            return False
        if not q:
            return True
        return it.seq == int(q) if q.isdigit() else (q in it.name.lower() or q in it.raw.lower())

    shown = 0
    for cat in ALL_CATS:
        group = sorted((i for i in inv.items if i.category == cat and match(i)), key=lambda x: x.cat_seq)
        if not group:
            continue
        shown += len(group)
        st.subheader(f"{CAT_ICON[cat]} {CAT_LABEL[cat]} ({len(group)})")
        if view == "ตาราง":
            st.dataframe(pd.DataFrame([{"ลำดับในหมวด": i.cat_seq, "ลำดับรวม": f"#{i.seq:03d}", "ชื่อสินค้า": i.name,
                                        "สเปก": spec_text(i.specs), "บันทึกเมื่อ": i.added_at.replace("T", " ")}
                                       for i in group]), hide_index=True)
        else:
            for it in group:
                item_card(it, manage=True)
    if not shown:
        st.caption("ไม่พบสินค้าที่ตรงเงื่อนไข")

    with st.expander("⚙️ สำรอง / จัดการข้อมูล"):
        raw_json = json.dumps([ga.asdict(i) for i in inv.items], ensure_ascii=False, indent=2)
        df = pd.DataFrame([{"ลำดับรวม": i.seq, "หมวด": i.label, "ลำดับในหมวด": i.cat_seq, "ชื่อสินค้า": i.name,
                            "สเปก": spec_text(i.specs), "บันทึกเมื่อ": i.added_at} for i in inv.items])
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ ดาวน์โหลด JSON", raw_json, "inventory.json", "application/json")
        d2.download_button("⬇️ ดาวน์โหลด CSV (เปิดใน Excel)", df.to_csv(index=False).encode("utf-8-sig"),
                           "inventory.csv", "text/csv")
        st.divider()
        sure = st.checkbox("ฉันต้องการลบสินค้าทั้งหมดในคลัง")
        st.button("🗑️ ล้างคลังทั้งหมด", disabled=not sure, on_click=clear_all)


# ════════════════════════ Sidebar + Router ════════════════════════
with st.sidebar:
    st.title("🛒 Gear Assistant")
    page = st.radio("เมนู", PAGES, key="page", label_visibility="collapsed")
    st.divider()
    st.metric("สินค้าในคลัง", len(inv.items))
    for cat in ALL_CATS:
        if n := sum(i.category == cat for i in inv.items):
            st.caption(f"{CAT_ICON[cat]} {CAT_LABEL[cat]}: {n}")
    st.divider()
    if inv.vision_hook:
        st.success("วิเคราะห์รูป: เปิดใช้งาน", icon="📷")
    else:
        st.caption("📷 วิเคราะห์รูป: ปิดอยู่ — ตั้งค่า ANTHROPIC_API_KEY แล้วรันใหม่เพื่อเปิดใช้")

{PAGES[0]: page_add, PAGES[1]: page_match, PAGES[2]: page_compat, PAGES[3]: page_inventory}[page]()