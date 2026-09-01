from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_, and_
from backend.database import Pasien, Kunjungan, LabViralLoad, LabCD4, UploadHistory, SimrsResep

MONTH_NAMES_ID = {
    "01": "Januari", "02": "Februari", "03": "Maret", "04": "April",
    "05": "Mei", "06": "Juni", "07": "Juli", "08": "Agustus",
    "09": "September", "10": "Oktober", "11": "November", "12": "Desember"
}

def get_executive_metrics(db: Session, date_start: str = None, date_end: str = None, period_preset: str = None):
    # 1. Ambil data mentah kunjungan dan lab
    all_kunj = db.query(
        Kunjungan.pasien_id,
        Kunjungan.tanggal_kunjungan,
        Kunjungan.nama_rejimen,
        Kunjungan.kategori_rejimen,
        Kunjungan.stadium_klinis,
        Kunjungan.alasan_kunjungan,
        Kunjungan.akhir_follow_up,
        Kunjungan.no_rekam_medik,
        Kunjungan.jumlah_hari_arv
    ).order_by(desc(Kunjungan.tanggal_kunjungan)).all()

    all_vl = db.query(
        LabViralLoad.pasien_id,
        LabViralLoad.tanggal_pemeriksaan,
        LabViralLoad.hasil_raw,
        LabViralLoad.hasil_numerik,
        LabViralLoad.kategori_vl,
        LabViralLoad.is_suppressed,
        LabViralLoad.is_undetectable,
        LabViralLoad.status_pemeriksaan
    ).order_by(desc(LabViralLoad.tanggal_pemeriksaan)).all()

    total_pasien_master = db.query(Pasien).count()
    total_kunjungan_all = len(all_kunj)
    total_vl_all = len(all_vl)

    # 2. Hitung Time-Series Tren Kunjungan Bulanan & MMD (Seluruh Waktu)
    from collections import defaultdict
    monthly_total = defaultdict(int)
    monthly_mmd = defaultdict(int)
    monthly_non_mmd = defaultdict(int)

    for k in all_kunj:
        if k.tanggal_kunjungan and len(k.tanggal_kunjungan) >= 7:
            m = k.tanggal_kunjungan[:7]
            monthly_total[m] += 1
            is_mmd = bool(k.jumlah_hari_arv and k.jumlah_hari_arv > 30)
            if is_mmd:
                monthly_mmd[m] += 1
            else:
                monthly_non_mmd[m] += 1

    sorted_months = sorted(monthly_total.keys())

    monthly_trend = []
    for m in sorted_months:
        y, mon = m.split('-')
        m_name = MONTH_NAMES_ID.get(mon, mon)
        tot = monthly_total[m]
        mmd = monthly_mmd[m]
        non_mmd = monthly_non_mmd[m]
        rate = round((mmd / tot * 100), 1) if tot > 0 else 0.0
        monthly_trend.append({
            "month": m,
            "label": f"{m_name[:3]} {y}",
            "full_label": f"{m_name} {y}",
            "count": tot,
            "non_mmd_count": non_mmd,
            "mmd_count": mmd,
            "mmd_rate": rate
        })

    # Susun opsi preset periode
    latest_m_code = sorted_months[-1] if sorted_months else "2026-08"
    ly, lm = latest_m_code.split('-')
    latest_label = f"{MONTH_NAMES_ID.get(lm, lm)} {ly}"

    available_periods = [
        {"id": "latest", "label": f"Bulan Berjalan ({latest_label})", "start": f"{latest_m_code}-01", "end": f"{latest_m_code}-31"},
        {"id": "all", "label": "Semua Waktu (Kumulatif)", "start": None, "end": None},
        {"id": "year_2026", "label": "Tahun 2026 (YTD)", "start": "2026-01-01", "end": "2026-12-31"},
        {"id": "q3_2026", "label": "Triwulan III (Jul - Sep 2026)", "start": "2026-07-01", "end": "2026-09-30"},
        {"id": "q2_2026", "label": "Triwulan II (Apr - Jun 2026)", "start": "2026-04-01", "end": "2026-06-30"},
        {"id": "q1_2026", "label": "Triwulan I (Jan - Mar 2026)", "start": "2026-01-01", "end": "2026-03-31"},
    ]

    for m in reversed(sorted_months):
        y, mon = m.split('-')
        available_periods.append({
            "id": f"month_{m}",
            "label": f"Bulan {MONTH_NAMES_ID.get(mon, mon)} {y}",
            "start": f"{m}-01",
            "end": f"{m}-31"
        })

    # 3. Resolusi Periode Terpilih
    active_start = date_start
    active_end = date_end
    active_label = "Semua Waktu (Kumulatif)"
    preset_selected = period_preset or ("all" if not (date_start or date_end) else "custom")

    if period_preset:
        matched = next((p for p in available_periods if p["id"] == period_preset), None)
        if matched:
            active_start = matched["start"]
            active_end = matched["end"]
            active_label = matched["label"]
    elif date_start and date_end:
        active_label = f"Rentang: {date_start} s/d {date_end}"
        preset_selected = "custom"
    elif not date_start and not date_end:
        active_label = "Semua Waktu (Kumulatif)"
        preset_selected = "all"

    # 4. Filter Kunjungan dan Lab Sesuai Periode
    if active_start and active_end:
        kunj_in_scope = [k for k in all_kunj if k.tanggal_kunjungan and active_start <= k.tanggal_kunjungan[:10] <= active_end]
    elif active_start:
        kunj_in_scope = [k for k in all_kunj if k.tanggal_kunjungan and active_start <= k.tanggal_kunjungan[:10]]
    elif active_end:
        kunj_in_scope = [k for k in all_kunj if k.tanggal_kunjungan and k.tanggal_kunjungan[:10] <= active_end]
    else:
        kunj_in_scope = all_kunj

    pts_in_scope_ids = set(k.pasien_id for k in kunj_in_scope)
    pts_on_art_ids = set(k.pasien_id for k in kunj_in_scope if k.nama_rejimen)
    total_kunjungan_period = len(kunj_in_scope)
    pasien_aktif_period = len(pts_in_scope_ids)

    # 5. Kunjungan terbaru tiap pasien dalam periode
    latest_kunj_map = {}
    for k in kunj_in_scope:
        if k.pasien_id not in latest_kunj_map:
            latest_kunj_map[k.pasien_id] = k

    # 6. Lab VL terbaru untuk pasien dalam periode
    target_pts = pts_in_scope_ids if (active_start or active_end) else None
    latest_vl_map = {}
    for v in all_vl:
        if target_pts is not None and v.pasien_id not in target_pts:
            continue
        if v.pasien_id not in latest_vl_map:
            latest_vl_map[v.pasien_id] = v

    vl_tested_count = len(latest_vl_map)
    suppressed_count = sum(1 for v in latest_vl_map.values() if v.is_suppressed)
    undetectable_count = sum(1 for v in latest_vl_map.values() if v.is_undetectable)
    unsuppressed_count = sum(1 for v in latest_vl_map.values() if v.kategori_vl and "Gagal Virologis" in v.kategori_vl)

    # Distribusi Kategori VL
    vl_cat_counts = {}
    for v in latest_vl_map.values():
        c = v.kategori_vl or "Belum Terkategori"
        vl_cat_counts[c] = vl_cat_counts.get(c, 0) + 1
    vl_cat_distribution = [{"category": k, "count": v} for k, v in sorted(vl_cat_counts.items(), key=lambda x: x[1], reverse=True)]

    # Distribusi Rejimen dalam Periode
    regimen_counts = {}
    for k in latest_kunj_map.values():
        reg = k.kategori_rejimen or "Tanpa ARV / Belum Ada"
        regimen_counts[reg] = regimen_counts.get(reg, 0) + 1
    regimen_distribution = [{"regimen": k, "count": v} for k, v in sorted(regimen_counts.items(), key=lambda x: x[1], reverse=True)]

    # Alasan Kunjungan dalam Periode
    alasan_counts = {}
    for k in kunj_in_scope:
        a = k.alasan_kunjungan or "Lainnya"
        alasan_counts[a] = alasan_counts.get(a, 0) + 1
    alasan_distribution = [{"alasan": k, "count": v} for k, v in sorted(alasan_counts.items(), key=lambda x: x[1], reverse=True)]

    # Early Warning Keterlambatan Obat
    max_kunj_date = max((k.tanggal_kunjungan for k in latest_kunj_map.values() if k.tanggal_kunjungan), default="2026-08-28")
    ref_date_str = active_end[:10] if (active_end and active_end <= max_kunj_date[:10]) else max_kunj_date[:10]
    ref_date = datetime.strptime(ref_date_str, "%Y-%m-%d")

    late_alerts = []
    for p_id, k in latest_kunj_map.items():
        if k.akhir_follow_up and k.nama_rejimen:
            try:
                fu_date = datetime.strptime(k.akhir_follow_up[:10], "%Y-%m-%d")
                delta_days = (ref_date - fu_date).days
                if delta_days > 0:
                    pasien_obj = db.query(Pasien).filter(Pasien.pasien_id == p_id).first()
                    nama = pasien_obj.nama_pasien if pasien_obj else "Anonim"
                    late_alerts.append({
                        "pasien_id": p_id,
                        "nama_pasien": nama,
                        "no_rekam_medik": k.no_rekam_medik or (pasien_obj.no_rekam_medik if pasien_obj else "-"),
                        "rejimen": k.nama_rejimen,
                        "akhir_follow_up": k.akhir_follow_up,
                        "hari_terlambat": delta_days,
                        "status": "Telat >30 Hari (Potensi LTFU)" if delta_days > 30 else ("Telat 8-30 Hari" if delta_days > 7 else "Telat 1-7 Hari")
                    })
            except Exception:
                pass
    late_alerts.sort(key=lambda x: x["hari_terlambat"], reverse=True)

    # Kaskade 95-95-95 Dinamis
    is_filtered_period = bool(active_start or active_end)
    base_cohort = pasien_aktif_period if is_filtered_period else total_pasien_master
    cohort_label = "Pasien Aktif Terlayani" if is_filtered_period else "Total Kohor Terdaftar"
    on_art_count = len(pts_on_art_ids)

    pct_on_art = round((on_art_count / base_cohort * 100), 1) if base_cohort > 0 else 0
    pct_tested_vl = round((vl_tested_count / on_art_count * 100), 1) if on_art_count > 0 else 0
    pct_suppressed = round((suppressed_count / vl_tested_count * 100), 1) if vl_tested_count > 0 else 0
    pct_undetectable = round((undetectable_count / vl_tested_count * 100), 1) if vl_tested_count > 0 else 0

    # Demografi Pasien Master
    gender_counts = db.query(Pasien.jenis_kelamin, func.count(Pasien.pasien_id)).group_by(Pasien.jenis_kelamin).all()
    gender_distribution = [{"gender": g or "Tidak Tercatat", "count": cnt} for g, cnt in gender_counts]

    populasi_counts = db.query(Pasien.kelompok_populasi, func.count(Pasien.pasien_id)).filter(
        Pasien.kelompok_populasi.isnot(None)
    ).group_by(Pasien.kelompok_populasi).order_by(desc(func.count(Pasien.pasien_id))).limit(8).all()
    populasi_distribution = [{"populasi": p, "count": cnt} for p, cnt in populasi_counts]

    wilayah_counts = db.query(Pasien.domisili_kabupaten, func.count(Pasien.pasien_id)).filter(
        Pasien.domisili_kabupaten.isnot(None),
        Pasien.domisili_kabupaten != ""
    ).group_by(Pasien.domisili_kabupaten).order_by(desc(func.count(Pasien.pasien_id))).limit(8).all()
    wilayah_distribution = [{"wilayah": w, "count": cnt} for w, cnt in wilayah_counts]

    # 5. Stratifikasi Mutu Layanan Baku (Eligible Active on ART Cohort - Bebas Denominator Inflation)
    all_patients_master = db.query(Pasien).all()
    vls_master = db.query(LabViralLoad).order_by(LabViralLoad.tanggal_pemeriksaan.desc()).all()
    latest_vl_dict = {}
    for v in vls_master:
        if v.pasien_id not in latest_vl_dict:
            latest_vl_dict[v.pasien_id] = v

    # Filter Kohor Pasien ODHIV Aktif Sedang Pengobatan ART
    active_on_art_pts = []
    for p in all_patients_master:
        status_pdp = str(p.status_odhiv_pdp or '').strip()
        status_odhiv = str(p.status_odhiv or '').strip()
        is_odhiv = (status_odhiv == 'ODHIV') or ('odhiv' in status_pdp.lower())
        is_active = (status_pdp in ['ODHIV sedang pengobatan', 'Sedang Pengobatan', 'ODHIV masuk perawatan']) or (p.tanggal_mulai_art and status_pdp not in ['Meninggal', 'Gagal follow up', 'Rujuk Keluar'])
        if is_odhiv and is_active:
            active_on_art_pts.append(p)

    asli_pts = []
    rujuk_pts = []
    for p in active_on_art_pts:
        is_rujuk_masuk = bool(
            (p.rujuk_masuk and str(p.rujuk_masuk).strip().lower() == 'ya') or
            (p.rujuk_masuk_dari_upk and str(p.rujuk_masuk_dari_upk).strip() != '') or
            (p.asal_rujukan and any(k in str(p.asal_rujukan).lower() for k in ['upk', 'rujukan', 'faskes', 'puskesmas', 'rs', 'bkpm', 'bkm']))
        )
        if is_rujuk_masuk:
            rujuk_pts.append(p)
        else:
            asli_pts.append(p)

    def calc_group_quality(group_list):
        tot = len(group_list)
        t_list = []
        s_list = []
        u_list = []
        f_list = []
        for p in group_list:
            vl = latest_vl_dict.get(p.pasien_id)
            if vl and vl.kategori_vl and vl.kategori_vl != "Belum Tes VL":
                t_list.append(p)
                if vl.is_suppressed:
                    s_list.append(p)
                if vl.is_undetectable or "undetectable" in str(vl.kategori_vl).lower() or "tnd" in str(vl.kategori_vl).lower():
                    u_list.append(p)
                if not vl.is_suppressed and ("gagal" in str(vl.kategori_vl).lower() or (vl.hasil_numerik and vl.hasil_numerik >= 1000)):
                    f_list.append(p)
        
        t_cnt = len(t_list)
        s_cnt = len(s_list)
        u_cnt = len(u_list)
        f_cnt = len(f_list)
        return {
            "total_pasien": tot,
            "tested_vl_count": t_cnt,
            "tested_vl_pct": round(t_cnt / tot * 100, 1) if tot > 0 else 0,
            "suppressed_count": s_cnt,
            "suppressed_pct": round(s_cnt / t_cnt * 100, 1) if t_cnt > 0 else 0,
            "undetectable_count": u_cnt,
            "undetectable_pct": round(u_cnt / t_cnt * 100, 1) if t_cnt > 0 else 0,
            "failed_count": f_cnt,
            "failed_pct": round(f_cnt / t_cnt * 100, 1) if t_cnt > 0 else 0
        }

    quality_stratification = {
        "asli_kariadi": calc_group_quality(asli_pts),
        "rujuk_masuk": calc_group_quality(rujuk_pts),
        "total_kohor": calc_group_quality(active_on_art_pts)
    }

    return {
        "quality_stratification": quality_stratification,
        "active_period": {
            "label": active_label,
            "preset": preset_selected,
            "date_start": active_start,
            "date_end": active_end,
            "visits_in_period": total_kunjungan_period,
            "patients_in_period": pasien_aktif_period,
            "is_filtered": is_filtered_period
        },
        "available_periods": available_periods,
        "monthly_trend": monthly_trend,
        "kpi": {
            "total_pasien": total_pasien_master,
            "pasien_aktif_period": pasien_aktif_period,
            "total_kunjungan": total_kunjungan_period,
            "total_kunjungan_all": total_kunjungan_all,
            "total_vl_tests": total_vl_all,
            "on_art_count": on_art_count,
            "vl_tested_count": vl_tested_count,
            "suppressed_count": suppressed_count,
            "undetectable_count": undetectable_count,
            "unsuppressed_count": unsuppressed_count,
            "pct_on_art": pct_on_art,
            "pct_tested_vl": pct_tested_vl,
            "pct_suppressed": pct_suppressed,
            "pct_undetectable": pct_undetectable,
            "late_patients_count": len(late_alerts)
        },
        "cascade_95": [
            {"stage": cohort_label, "count": base_cohort, "pct": 100.0, "color": "#3B82F6"},
            {"stage": "On ART (Terapi ARV)", "count": on_art_count, "pct": pct_on_art, "color": "#10B981"},
            {"stage": "Viral Load Tested", "count": vl_tested_count, "pct": pct_tested_vl, "color": "#8B5CF6"},
            {"stage": "VL Tersupresi (<1000)", "count": suppressed_count, "pct": pct_suppressed, "color": "#06B6D4"},
            {"stage": "Undetectable (U=U)", "count": undetectable_count, "pct": pct_undetectable, "color": "#EC4899"}
        ],
        "vl_distribution": vl_cat_distribution,
        "regimen_distribution": regimen_distribution,
        "alasan_distribution": alasan_distribution,
        "gender_distribution": gender_distribution,
        "populasi_distribution": populasi_distribution,
        "wilayah_distribution": wilayah_distribution,
        "late_alerts": late_alerts[:15],
        "active_period": {
            "preset": preset_selected,
            "label": active_label,
            "date_start": active_start,
            "date_end": active_end,
            "is_filtered": bool(active_start or active_end),
            "visits_in_period": total_kunjungan_period,
            "patients_in_period": pasien_aktif_period
        },
        "available_periods": available_periods,
        "ref_date": ref_date_str
    }

import time

_COHORT_RAW_CACHE = {
    "timestamp": 0,
    "pasien_list": None,
    "kunjs_by_pid": None,
    "latest_kunj_overall": None,
    "latest_vl": None,
    "latest_cd4": None
}

def invalidate_cohort_cache():
    global _COHORT_RAW_CACHE
    _COHORT_RAW_CACHE["timestamp"] = 0
    _COHORT_RAW_CACHE["pasien_list"] = None

def get_research_cohort_data(db: Session, filters: dict, is_export: bool = False):
    """
    Mengambil data terintegrasi (Master Pasien + Kunjungan + Lab VL/CD4)
    dengan multi-filtering fleksibel dan in-memory caching ultra-cepat.
    """
    global _COHORT_RAW_CACHE

    date_kunj_start = filters.get("date_kunj_start")
    date_kunj_end = filters.get("date_kunj_end")
    has_date_filter = bool(date_kunj_start or date_kunj_end)

    # 1. Cek / Muat Cache Master Database
    now_ts = time.time()
    if (now_ts - _COHORT_RAW_CACHE["timestamp"] < 60) and (_COHORT_RAW_CACHE["pasien_list"] is not None):
        pasien_list = _COHORT_RAW_CACHE["pasien_list"]
        kunjs_by_pid = _COHORT_RAW_CACHE["kunjs_by_pid"]
        latest_kunj_overall = _COHORT_RAW_CACHE["latest_kunj_overall"]
        latest_vl = _COHORT_RAW_CACHE["latest_vl"]
        latest_cd4 = _COHORT_RAW_CACHE["latest_cd4"]
    else:
        all_kunj = db.query(Kunjungan).order_by(desc(Kunjungan.tanggal_kunjungan)).all()
        from collections import defaultdict
        kunjs_by_pid = defaultdict(list)
        latest_kunj_overall = {}
        for k in all_kunj:
            if k.pasien_id:
                kunjs_by_pid[k.pasien_id].append(k)
                if k.pasien_id not in latest_kunj_overall:
                    latest_kunj_overall[k.pasien_id] = k

        all_vl = db.query(LabViralLoad).order_by(desc(LabViralLoad.tanggal_pemeriksaan)).all()
        latest_vl = {}
        for v in all_vl:
            if v.pasien_id not in latest_vl:
                latest_vl[v.pasien_id] = v

        all_cd4 = db.query(LabCD4).order_by(desc(LabCD4.tanggal_pemeriksaan)).all()
        latest_cd4 = {}
        for c in all_cd4:
            if c.pasien_id not in latest_cd4:
                latest_cd4[c.pasien_id] = c

        pasien_list = db.query(Pasien).all()

        _COHORT_RAW_CACHE["timestamp"] = now_ts
        _COHORT_RAW_CACHE["pasien_list"] = pasien_list
        _COHORT_RAW_CACHE["kunjs_by_pid"] = kunjs_by_pid
        _COHORT_RAW_CACHE["latest_kunj_overall"] = latest_kunj_overall
        _COHORT_RAW_CACHE["latest_vl"] = latest_vl
        _COHORT_RAW_CACHE["latest_cd4"] = latest_cd4

    # 2. Gabungkan menjadi unified flat records
    unified = []
    for p in pasien_list:
        v = latest_vl.get(p.pasien_id)
        c = latest_cd4.get(p.pasien_id)
        k = None
        if has_date_filter:
            p_kunjs = kunjs_by_pid.get(p.pasien_id, [])
            valid_kunjs = []
            for k_item in p_kunjs:
                tgl = k_item.tanggal_kunjungan
                if not tgl:
                    continue
                if date_kunj_start and tgl < date_kunj_start:
                    continue
                if date_kunj_end and tgl > date_kunj_end:
                    continue
                valid_kunjs.append(k_item)
            
            if valid_kunjs:
                k = valid_kunjs[0]
            else:
                p_kunj_terakhir = p.kunjungan_terakhir
                p_reg = p.tanggal_register
                in_range_kunj = (p_kunj_terakhir and (not date_kunj_start or p_kunj_terakhir >= date_kunj_start) and (not date_kunj_end or p_kunj_terakhir <= date_kunj_end))
                in_range_reg = (p_reg and (not date_kunj_start or p_reg >= date_kunj_start) and (not date_kunj_end or p_reg <= date_kunj_end))
                
                if in_range_kunj or in_range_reg:
                    k = latest_kunj_overall.get(p.pasien_id)
                else:
                    continue
        else:
            k = latest_kunj_overall.get(p.pasien_id)

        # Evaluasi Status Retensi PDP Klinis
        if p.tanggal_meninggal:
            status_pdp = "Meninggal"
        elif p.tanggal_rujuk_keluar or (p.rujuk_keluar and p.rujuk_keluar.lower() == "ya") or (k and k.alasan_kunjungan and "rujuk keluar" in k.alasan_kunjungan.lower()):
            status_pdp = "Rujuk Keluar"
        elif p.tanggal_lost_to_follow_up or (k and k.status_odhiv_pdp and "gagal" in k.status_odhiv_pdp.lower()):
            status_pdp = "Gagal Follow-up (LTFU)"
        elif p.rujuk_masuk and p.rujuk_masuk.lower() == "ya":
            status_pdp = "Rujuk Masuk (Transfer In)"
        elif (k and k.status_odhiv_pdp and "pengobatan" in k.status_odhiv_pdp.lower()) or (k and k.nama_rejimen):
            status_pdp = "Sedang Pengobatan"
        elif k and k.status_odhiv_pdp and "masuk" in k.status_odhiv_pdp.lower():
            status_pdp = "Masuk Perawatan"
        else:
            status_pdp = k.status_odhiv_pdp if (k and k.status_odhiv_pdp) else (p.status_odhiv_pdp or "Belum Mulai PDP")

        # Kalkulasi Umur Efektif
        eff_umur = p.umur
        if eff_umur is None and p.tanggal_lahir:
            try:
                dt_lhr = datetime.strptime(p.tanggal_lahir, "%Y-%m-%d")
                eff_umur = datetime.now().year - dt_lhr.year
            except Exception:
                pass

        # Kelompok Usia Klinis (Standar RS Kariadi & Hukum Anak Indonesia: <18 th)
        if eff_umur is not None:
            if eff_umur < 18:
                kel_umur = "Pediatrik (<18 th)"
            elif eff_umur < 25:
                kel_umur = "Remaja (18-24 th)"
            elif eff_umur < 50:
                kel_umur = "Dewasa (25-49 th)"
            else:
                kel_umur = "Geriatrik (>=50 th)"
        elif p.kategori_umur and "anak" in str(p.kategori_umur).lower():
            kel_umur = "Pediatrik (<18 th)"
        else:
            kel_umur = "Tidak Tercatat"

        is_mmd = bool(k and k.jumlah_hari_arv and k.jumlah_hari_arv >= 60)
        status_hamil_val = k.status_hamil if (k and k.status_hamil) else "-"
        
        # Kalkulasi Durasi LTFU
        ltfu_kategori = None
        today_date = datetime.now().date()
        if status_pdp == "Gagal Follow-up (LTFU)":
            if p.tanggal_lost_to_follow_up:
                try:
                    dt_ltfu = datetime.strptime(p.tanggal_lost_to_follow_up, "%Y-%m-%d").date()
                    days = (today_date - dt_ltfu).days
                except ValueError:
                    days = 90 # fallback
            elif k and k.akhir_follow_up:
                try:
                    dt_afu = datetime.strptime(k.akhir_follow_up, "%Y-%m-%d").date()
                    days = (today_date - dt_afu).days
                except ValueError:
                    days = 90
            else:
                days = 90
                
            if days <= 90:
                ltfu_kategori = "LTFU < 3 Bulan"
            elif days <= 180:
                ltfu_kategori = "LTFU 3-6 Bulan"
            else:
                ltfu_kategori = "LTFU > 6 Bulan"

        # Kalkulasi Kepatuhan
        kepatuhan_val = "Tidak Diketahui"
        if k and k.status_keterlambatan:
            kepatuhan_val = k.status_keterlambatan
        elif status_pdp == "Sedang Pengobatan" and k and k.tanggal_kunjungan:
            dt_afu = None
            if k.akhir_follow_up:
                try:
                    dt_afu = datetime.strptime(k.akhir_follow_up, "%Y-%m-%d").date()
                except ValueError:
                    dt_afu = None
            
            # Fallback jika akhir_follow_up bukan tanggal valid
            if not dt_afu and k.tanggal_kunjungan:
                try:
                    dt_kunj = datetime.strptime(k.tanggal_kunjungan, "%Y-%m-%d").date()
                    hari_arv = k.jumlah_hari_arv if k.jumlah_hari_arv else 30
                    dt_afu = dt_kunj + timedelta(days=hari_arv)
                except ValueError:
                    pass

            if dt_afu:
                days_late = (today_date - dt_afu).days
                if days_late <= 0:
                    kepatuhan_val = "Tepat Waktu"
                elif days_late <= 7:
                    kepatuhan_val = "Telat 1-7 Hari"
                else:
                    kepatuhan_val = "Telat >7 Hari"
        elif status_pdp == "Gagal Follow-up (LTFU)":
            kepatuhan_val = "Telat >7 Hari"

        is_rujuk_masuk = bool(
            (p.rujuk_masuk and str(p.rujuk_masuk).strip().lower() == "ya") or
            (p.rujuk_masuk_dari_upk and str(p.rujuk_masuk_dari_upk).strip() != "") or
            (p.asal_rujukan and any(k in str(p.asal_rujukan).lower() for k in ["upk", "rujukan", "faskes", "puskesmas", "rs"]))
        )

        # Kalkulasi Durasi Terapi ART Presisi (Censored Time-on-ART / Bebas Immortal Time Bias)
        durasi_art_th = None
        kelompok_durasi_art = "Belum Mulai ART"
        is_censored = False
        censor_reason = "Aktif Terapi"

        if p.tanggal_mulai_art:
            try:
                dt_art = datetime.strptime(str(p.tanggal_mulai_art)[:10], "%Y-%m-%d")
                end_dt = datetime.now()

                # Right-Censoring: Hentikan penghitungan durasi pada titik akhir observasi klinis
                if status_pdp == "Meninggal":
                    if p.tanggal_meninggal:
                        try:
                            end_dt = datetime.strptime(str(p.tanggal_meninggal)[:10], "%Y-%m-%d")
                            is_censored = True
                            censor_reason = "Meninggal Dunia"
                        except Exception:
                            pass
                elif status_pdp == "Rujuk Keluar":
                    if p.tanggal_rujuk_keluar:
                        try:
                            end_dt = datetime.strptime(str(p.tanggal_rujuk_keluar)[:10], "%Y-%m-%d")
                            is_censored = True
                            censor_reason = "Rujuk Keluar"
                        except Exception:
                            pass
                elif status_pdp == "Gagal Follow-up (LTFU)":
                    if p.tanggal_lost_to_follow_up:
                        try:
                            end_dt = datetime.strptime(str(p.tanggal_lost_to_follow_up)[:10], "%Y-%m-%d")
                            is_censored = True
                            censor_reason = "Mangkir / LTFU"
                        except Exception:
                            pass
                    elif k and k.tanggal_kunjungan:
                        try:
                            end_dt = datetime.strptime(str(k.tanggal_kunjungan)[:10], "%Y-%m-%d")
                            is_censored = True
                            censor_reason = "Kunjungan Terakhir (LTFU)"
                        except Exception:
                            pass

                dur_days = max(0, (end_dt - dt_art).days)
                durasi_art_th = round(dur_days / 365.25, 1)

                if durasi_art_th >= 15:
                    kelompok_durasi_art = ">= 15 Tahun (Kohor Veteran)"
                elif durasi_art_th >= 10:
                    kelompok_durasi_art = "10 - 14 Tahun"
                elif durasi_art_th >= 5:
                    kelompok_durasi_art = "5 - 9 Tahun"
                elif durasi_art_th >= 1:
                    kelompok_durasi_art = "1 - 4 Tahun"
                elif durasi_art_th >= 0:
                    kelompok_durasi_art = "< 1 Tahun (Inisiasi Baru)"
            except Exception:
                pass

        # Riwayat Pergantian / Switch Rejimen
        p_kunjs = kunjs_by_pid.get(p.pasien_id, [])
        historical_regimens = list(dict.fromkeys(k_item.nama_rejimen for k_item in p_kunjs if k_item.nama_rejimen))
        regimen_switch_count = len(historical_regimens)
        status_switch_art = "Pernah Switch Rejimen" if regimen_switch_count > 1 else ("Rejimen Tetap" if regimen_switch_count == 1 else "Belum Ada Catatan")

        rec = {
            "pasien_id": p.pasien_id,
            "no_rekam_medik": p.no_rekam_medik or (k.no_rekam_medik if k else "-"),
            "nama_pasien": p.nama_pasien or "-",
            "nik": p.nik or "-",
            "umur": eff_umur if eff_umur is not None else p.umur,
            "kategori_umur": p.kategori_umur or "Tidak Diketahui",
            "kelompok_umur_klinis": kel_umur,
            "is_pediatric": bool((eff_umur is not None and eff_umur < 18) or (p.kategori_umur and "anak" in str(p.kategori_umur).lower())),
            "jenis_kelamin": p.jenis_kelamin or "Tidak Tercatat",
            "kelompok_populasi": p.kelompok_populasi or "Populasi Umum",
            "domisili_kabupaten": p.domisili_kabupaten or "-",
            "tanggal_register": p.tanggal_register,
            "status_odhiv": p.status_odhiv or (k.status_odhiv if k else "-"),
            "status_pdp": status_pdp,
            "status_hamil": status_hamil_val,
            "tanggal_meninggal": p.tanggal_meninggal,
            "is_rujuk_masuk": is_rujuk_masuk,
            "rujuk_masuk_dari_upk": p.rujuk_masuk_dari_upk or "-",
            "asal_rujukan": p.asal_rujukan or "-",
            
            # Durasi Terapi ART & Riwayat Switch Rejimen (Censored)
            "tanggal_mulai_art": p.tanggal_mulai_art,
            "durasi_art_tahun": durasi_art_th,
            "kelompok_durasi_art": kelompok_durasi_art,
            "is_censored": is_censored,
            "censor_reason": censor_reason,
            "riwayat_rejimen": historical_regimens,
            "regimen_switch_count": regimen_switch_count,
            "status_switch_art": status_switch_art,

            # Data Kunjungan Terakhir
            "tanggal_kunjungan": (k.tanggal_kunjungan if (k and k.tanggal_kunjungan) else p.kunjungan_terakhir) or "-",
            "alasan_kunjungan": k.alasan_kunjungan if k else None,
            "stadium_klinis": k.stadium_klinis if k else (p.stadium_klinis_awal or "-"),
            "nama_rejimen": k.nama_rejimen if k else "-",
            "kategori_rejimen": k.kategori_rejimen if k else "Tanpa ARV / Belum Ada",
            "berat_badan": k.berat_badan if k else None,
            "tinggi_badan": k.tinggi_badan if k else None,
            "imt": k.imt if k else None,
            "kategori_imt": k.kategori_imt if k else "Belum Diukur",
            "jumlah_hari_arv": k.jumlah_hari_arv if k else None,
            "is_mmd": is_mmd,
            "akhir_follow_up": k.akhir_follow_up if k else None,

            # Data Lab VL Terakhir
            "tanggal_vl": v.tanggal_pemeriksaan if v else None,
            "hasil_vl_raw": v.hasil_raw if v else "-",
            "hasil_vl_numerik": v.hasil_numerik if v else None,
            "kategori_vl": v.kategori_vl if v else "Belum Tes VL",
            "is_suppressed": v.is_suppressed if v else False,
            "is_undetectable": v.is_undetectable if v else False,
            
            # Additional Research Variables
            "ltfu_kategori": ltfu_kategori,
            "koinfeksi_tb": "Tidak Dievaluasi", # Placeholder if not in DB yet
            "kepatuhan": kepatuhan_val, # Proxy for adherence

            # Data Lab CD4 Terakhir
            "tanggal_cd4": c.tanggal_pemeriksaan if c else None,
            "nilai_cd4": c.nilai_cd4 if c else None,
            "kategori_cd4": c.kategori_cd4 if c else "Belum Tes CD4"
        }
        unified.append(rec)

    # 4. Filter Processing
    filtered = []
    
    durasi_art_filter = filters.get("durasi_art")
    gender_filter = filters.get("gender")
    populasi_filter = filters.get("populasi")
    stadium_filter = filters.get("stadium")
    rejimen_filter = filters.get("rejimen")
    vl_cat_filter = filters.get("kategori_vl")
    imt_cat_filter = filters.get("kategori_imt")
    cd4_cat_filter = filters.get("kategori_cd4")
    status_pdp_filter = filters.get("status_pdp")
    kel_umur_filter = filters.get("kelompok_umur_klinis")
    status_hamil_filter = filters.get("status_hamil")
    is_mmd_filter = filters.get("is_mmd")

    age_min = filters.get("age_min")
    ltfu_cat_filter = filters.get("ltfu_kategori")
    tb_filter = filters.get("koinfeksi_tb")
    kepatuhan_filter = filters.get("kepatuhan")
    age_min = filters.get("age_min")
    age_max = filters.get("age_max")
    search = (filters.get("search") or "").strip().lower()
    date_kunj_start = filters.get("date_kunj_start")
    date_kunj_end = filters.get("date_kunj_end")

    for r in unified:
        # Search Filter
        if search:
            match_str = f"{r['pasien_id']} {r['no_rekam_medik']} {r['nama_pasien']} {r['nik']} {r['nama_rejimen']} {r['asal_rujukan']} {r['rujuk_masuk_dari_upk']}".lower()
            if search not in match_str:
                continue

        # Durasi Terapi ART Filter
        if durasi_art_filter and r["kelompok_durasi_art"] not in durasi_art_filter:
            continue

        # Status PDP / Retensi
        if status_pdp_filter:
            if "Rujuk Masuk (Transfer In)" in status_pdp_filter:
                if not r["is_rujuk_masuk"]:
                    continue
            elif r["status_pdp"] not in status_pdp_filter:
                continue
            
        # LTFU Kategori
        if ltfu_cat_filter and r["ltfu_kategori"] not in ltfu_cat_filter:
            continue
            
        # TB Koinfeksi
        if tb_filter and r["koinfeksi_tb"] not in tb_filter:
            continue
            
        # Kepatuhan
        if kepatuhan_filter and r["kepatuhan"] not in kepatuhan_filter:
            continue
            
        # Kategori Umur Klinis
        if kel_umur_filter and r["kelompok_umur_klinis"] not in kel_umur_filter:
            continue

        # Status Hamil
        if status_hamil_filter:
            if "Hamil" in status_hamil_filter and "hamil" not in r["status_hamil"].lower():
                continue
            if "Tidak Hamil" in status_hamil_filter and "hamil" in r["status_hamil"].lower():
                continue

        # MMD (Multi-Month Dispensing)
        if is_mmd_filter is not None and r["is_mmd"] != is_mmd_filter:
            continue

        # Gender
        if gender_filter and r["jenis_kelamin"] not in gender_filter:
            continue

        # Populasi
        if populasi_filter and r["kelompok_populasi"] not in populasi_filter:
            continue

        # Stadium
        if stadium_filter and r["stadium_klinis"] not in stadium_filter:
            continue

        # Rejimen
        if rejimen_filter and r["kategori_rejimen"] not in rejimen_filter:
            continue

        # VL Category
        if vl_cat_filter and r["kategori_vl"] not in vl_cat_filter:
            continue

        # IMT Category
        if imt_cat_filter and r["kategori_imt"] not in imt_cat_filter:
            continue

        # CD4 Category
        if cd4_cat_filter and r["kategori_cd4"] not in cd4_cat_filter:
            continue

        # Age Numeric
        if age_min is not None and r["umur"] is not None and r["umur"] < age_min:
            continue
        if age_max is not None and r["umur"] is not None and r["umur"] > age_max:
            continue

        filtered.append(r)

    # 5. Agregasi Statistik Komprehensif untuk Peneliti
    total_matched = len(filtered)
    ages = [r["umur"] for r in filtered if r["umur"] is not None]
    avg_age = round(sum(ages) / len(ages), 1) if ages else 0
    
    tested_vl_count = sum(1 for r in filtered if r["kategori_vl"] != "Belum Tes VL")
    suppressed_count = sum(1 for r in filtered if r["is_suppressed"])
    vls_rate = round((suppressed_count / tested_vl_count * 100), 1) if tested_vl_count > 0 else 0

    # Riset Pediatrik (<15 th)
    pediatric_pts = [r for r in filtered if r["is_pediatric"]]
    pediatric_count = len(pediatric_pts)
    ped_tested = sum(1 for r in pediatric_pts if r["kategori_vl"] != "Belum Tes VL")
    ped_suppressed = sum(1 for r in pediatric_pts if r["is_suppressed"])
    ped_vls_rate = round((ped_suppressed / ped_tested * 100), 1) if ped_tested > 0 else 0

    # Riset Retensi & Outcome
    active_on_art_count = sum(1 for r in filtered if r["status_pdp"] == "Sedang Pengobatan")
    pediatric_count = sum(1 for r in filtered if r["is_pediatric"])
    ltfu_count = sum(1 for r in filtered if r["status_pdp"] == "Gagal Follow-up (LTFU)")
    meninggal_count = sum(1 for r in filtered if r["status_pdp"] == "Meninggal")
    rujuk_keluar_count = sum(1 for r in filtered if r["status_pdp"] == "Rujuk Keluar")
    rujuk_masuk_count = sum(1 for r in filtered if r["is_rujuk_masuk"])
    mmd_count = sum(1 for r in filtered if r["is_mmd"])
    hamil_count = sum(1 for r in filtered if "hamil" in r["status_hamil"].lower())
    
    vl_tested = sum(1 for r in filtered if r["hasil_vl_raw"] != "-")
    vl_suppressed = sum(1 for r in filtered if r["is_suppressed"])

    summary = {
        "total_matched": len(filtered),
        "active_on_art_count": active_on_art_count,
        "pediatric_count": pediatric_count,
        "ltfu_count": ltfu_count,
        "meninggal_count": meninggal_count,
        "rujuk_keluar_count": rujuk_keluar_count,
        "rujuk_masuk_count": rujuk_masuk_count,
        "mmd_count": mmd_count,
        "hamil_count": hamil_count,
        "vl_tested": vl_tested,
        "vl_suppressed": vl_suppressed,
        "vls_percentage": round((vl_suppressed / vl_tested * 100) if vl_tested > 0 else 0, 1)
    }

    # Cross-Tab: Rejimen vs Tingkat Supresi VL
    cross_regimen = {}
    for r in filtered:
        reg = r["kategori_rejimen"]
        if reg not in cross_regimen:
            cross_regimen[reg] = {"total": 0, "tested": 0, "suppressed": 0, "unsuppressed": 0}
        cross_regimen[reg]["total"] += 1
        if r["kategori_vl"] != "Belum Tes VL":
            cross_regimen[reg]["tested"] += 1
            if r["is_suppressed"]:
                cross_regimen[reg]["suppressed"] += 1
            else:
                cross_regimen[reg]["unsuppressed"] += 1

    regimen_crosstab = []
    for reg, stats in cross_regimen.items():
        rate = round((stats["suppressed"] / stats["tested"] * 100), 1) if stats["tested"] > 0 else 0
        regimen_crosstab.append({
            "rejimen": reg,
            "total_pasien": stats["total"],
            "tested_vl": stats["tested"],
            "suppressed": stats["suppressed"],
            "unsuppressed": stats["unsuppressed"],
            "suppression_rate": rate
        })

    # Cross-Tab: Durasi Terapi ART vs Efikasi Supresi Virologis & Switch Rejimen
    cross_duration = {}
    for r in filtered:
        dur_cat = r["kelompok_durasi_art"]
        if dur_cat not in cross_duration:
            cross_duration[dur_cat] = {"total": 0, "tested": 0, "suppressed": 0, "unsuppressed": 0, "switched": 0}
        cross_duration[dur_cat]["total"] += 1
        if r["regimen_switch_count"] > 1:
            cross_duration[dur_cat]["switched"] += 1
        if r["kategori_vl"] != "Belum Tes VL":
            cross_duration[dur_cat]["tested"] += 1
            if r["is_suppressed"]:
                cross_duration[dur_cat]["suppressed"] += 1
            else:
                cross_duration[dur_cat]["unsuppressed"] += 1

    duration_crosstab = []
    dur_order = [">= 15 Tahun (Kohor Veteran)", "10 - 14 Tahun", "5 - 9 Tahun", "1 - 4 Tahun", "< 1 Tahun (Inisiasi Baru)", "Belum Mulai ART"]
    for d_name in dur_order:
        if d_name in cross_duration:
            st = cross_duration[d_name]
            vls_pct = round((st["suppressed"] / st["tested"] * 100), 1) if st["tested"] > 0 else 0
            switch_pct = round((st["switched"] / st["total"] * 100), 1) if st["total"] > 0 else 0
            duration_crosstab.append({
                "kelompok_durasi": d_name,
                "total_pasien": st["total"],
                "tested_vl": st["tested"],
                "suppressed": st["suppressed"],
                "unsuppressed": st["unsuppressed"],
                "suppression_rate": vls_pct,
                "switched_patients": st["switched"],
                "switch_rate": switch_pct
            })

    # Cross-Tab: Stadium Klinis vs Kategori VL
    cross_stadium = {}
    for r in filtered:
        stad = r["stadium_klinis"]
        vl = r["kategori_vl"]
        if stad not in cross_stadium:
            cross_stadium[stad] = {}
        cross_stadium[stad][vl] = cross_stadium[stad].get(vl, 0) + 1

    # Filter Options for UI Dropdowns
    all_durasi_art = [">= 15 Tahun (Kohor Veteran)", "10 - 14 Tahun", "5 - 9 Tahun", "1 - 4 Tahun", "< 1 Tahun (Inisiasi Baru)"]
    all_genders = sorted(list(set(r["jenis_kelamin"] for r in unified if r["jenis_kelamin"])))
    all_populasi = sorted(list(set(r["kelompok_populasi"] for r in unified if r["kelompok_populasi"])))
    all_stadium = sorted(list(set(r["stadium_klinis"] for r in unified if r["stadium_klinis"] and r["stadium_klinis"] != "-")))
    all_rejimen = sorted(list(set(r["kategori_rejimen"] for r in unified if r["kategori_rejimen"])))
    all_vl_cats = sorted(list(set(r["kategori_vl"] for r in unified if r["kategori_vl"])))
    all_imt_cats = sorted(list(set(r["kategori_imt"] for r in unified if r["kategori_imt"])))
    all_cd4_cats = sorted(list(set(r["kategori_cd4"] for r in unified if r["kategori_cd4"] and r["kategori_cd4"] != "Belum Tes CD4")))
    all_status_pdp = sorted(list(set(r["status_pdp"] for r in unified if r["status_pdp"])))
    all_kel_umur = ["Pediatrik (<18 th)", "Remaja (18-24 th)", "Dewasa (25-49 th)", "Geriatrik (>=50 th)"]

    # Aggregation Top Faskes Rujuk Masuk
    referral_sources = {}
    for r in filtered:
        if r["is_rujuk_masuk"]:
            src = r["rujuk_masuk_dari_upk"]
            if src == "-" or not src:
                src = r["asal_rujukan"]
            if src and src != "-":
                referral_sources[src] = referral_sources.get(src, 0) + 1

    top_referral_sources = [{"facility": f, "count": c} for f, c in sorted(referral_sources.items(), key=lambda x: x[1], reverse=True)[:10]]

    summary = {
        "total_matched": total_matched,
        "avg_age": avg_age,
        "tested_vl_count": tested_vl_count,
        "suppressed_count": suppressed_count,
        "vls_rate": vls_rate,
        "vls_percentage": vls_rate,
        "active_on_art_count": active_on_art_count,
        "ltfu_count": ltfu_count,
        "meninggal_count": meninggal_count,
        "rujuk_keluar_count": rujuk_keluar_count,
        "rujuk_masuk_count": rujuk_masuk_count,
        "pediatric_count": pediatric_count,
        "pediatric_suppressed_rate": ped_vls_rate,
        "mmd_count": mmd_count,
        "hamil_count": hamil_count
    }

    return {
        "summary": summary,
        "top_referral_sources": top_referral_sources,
        "regimen_crosstab": sorted(regimen_crosstab, key=lambda x: x["total_pasien"], reverse=True),
        "duration_crosstab": duration_crosstab,
        "stadium_crosstab": cross_stadium,
        "filter_options": {
            "durasi_art": all_durasi_art,
            "genders": all_genders,
            "populasi": all_populasi,
            "stadium": all_stadium,
            "rejimen": all_rejimen,
            "kategori_vl": all_vl_cats,
            "kategori_imt": all_imt_cats,
            "kategori_cd4": all_cd4_cats,
            "status_pdp": all_status_pdp,
            "kelompok_umur_klinis": all_kel_umur
        },
        "records": filtered if is_export else filtered[:100]
    }


def get_pediatric_dashboard_data(db: Session, period_month: str = None):
    cohort = get_research_cohort_data(db, {})
    all_recs = cohort["records"]
    
    peds = [r for r in all_recs if r["is_pediatric"]]
    ped_pasien_ids = set(r["pasien_id"] for r in peds)

    # Monthly visit breakdown for pediatric cohort
    kunj_list = db.query(Kunjungan).filter(Kunjungan.pasien_id.in_(ped_pasien_ids)).all()
    monthly_visits = {}
    for k in kunj_list:
        if k.tanggal_kunjungan:
            m_key = k.tanggal_kunjungan[:7] # YYYY-MM
            if m_key not in monthly_visits:
                monthly_visits[m_key] = set()
            monthly_visits[m_key].add(k.pasien_id)

    sorted_months = sorted(monthly_visits.keys(), reverse=True)
    monthly_trend = []
    for m in sorted_months:
        yr, mo = m.split("-") if "-" in m else (m, "")
        mo_name = MONTH_NAMES_ID.get(mo, mo)
        monthly_trend.append({
            "month": m,
            "label": f"{mo_name} {yr}",
            "count": len(monthly_visits[m])
        })

    # Apply period_month filter if requested
    if period_month and period_month.strip() != "" and period_month.lower() != "all":
        active_ids = monthly_visits.get(period_month, set())
        peds = [r for r in peds if r["pasien_id"] in active_ids]
    
    terpajan_profilaksis = []
    odhiv_terkonfirmasi = []
    skrining_negatif = []
    
    for r in peds:
        rejimen_lower = str(r["nama_rejimen"] or "").lower()
        alasan_lower = str(r["alasan_kunjungan"] or "").lower()
        status_odhiv = str(r["status_odhiv"] or "").strip()
        
        is_prophylaxis = ("profilaksis" in alasan_lower or 
                          "profilaksis" in rejimen_lower or 
                          ("zdv" in rejimen_lower and "3tc" not in rejimen_lower))
        
        if is_prophylaxis:
            r["status_anak_detail"] = "Bayi Terpajan (Profilaksis ARV/Kotrimoksazol)"
            r["badge_color"] = "bg-amber-100 text-amber-800 border-amber-300"
            terpajan_profilaksis.append(r)
        elif status_odhiv == "ODHIV":
            r["status_anak_detail"] = "Anak Terkonfirmasi ODHIV (Terapi ARV)"
            r["badge_color"] = "bg-rose-100 text-rose-800 border-rose-300"
            odhiv_terkonfirmasi.append(r)
        else:
            r["status_anak_detail"] = "Anak Skrining Non-Reaktif (Bukan ODHIV)"
            r["badge_color"] = "bg-emerald-100 text-emerald-800 border-emerald-300"
            skrining_negatif.append(r)

    total_anak = len(peds)
    total_odhiv = len(odhiv_terkonfirmasi)
    total_profilaksis = len(terpajan_profilaksis)
    total_negatif = len(skrining_negatif)
    
    tested_vl = sum(1 for r in peds if r["kategori_vl"] != "Belum Tes VL")
    suppressed_vl = sum(1 for r in peds if r["is_suppressed"])
    vls_rate = round((suppressed_vl / tested_vl * 100), 1) if tested_vl > 0 else 100.0

    return {
        "summary": {
            "total_anak": total_anak,
            "odhiv_terkonfirmasi": total_odhiv,
            "bayi_terpajan_profilaksis": total_profilaksis,
            "skrining_non_reaktif": total_negatif,
            "tested_vl": tested_vl,
            "suppressed_vl": suppressed_vl,
            "vls_rate": vls_rate
        },
        "monthly_trend": monthly_trend,
        "available_months": monthly_trend,
        "records": peds
    }


def get_simrs_audit_data(db: Session, period_sheet: str = None, depo_name: str = None, nama_dokter: str = None, item_desc: str = None, search: str = None):
    # Fetch distinct options for filter dropdowns
    all_sheets = sorted([r[0] for r in db.query(SimrsResep.periode_sheet).distinct().all() if r[0]])
    all_depos = sorted([r[0] for r in db.query(SimrsResep.depo_name).distinct().all() if r[0]])
    all_doctors = sorted([r[0] for r in db.query(SimrsResep.nama_dokter).distinct().all() if r[0]])
    all_items = sorted([r[0] for r in db.query(SimrsResep.item_code_desc).distinct().all() if r[0]])

    query = db.query(SimrsResep)
    if period_sheet and period_sheet.strip() != "" and period_sheet.lower() != "all":
        query = query.filter(SimrsResep.periode_sheet == period_sheet)
    if depo_name and depo_name.strip() != "" and depo_name.lower() != "all":
        query = query.filter(SimrsResep.depo_name == depo_name)
    if nama_dokter and nama_dokter.strip() != "" and nama_dokter.lower() != "all":
        query = query.filter(SimrsResep.nama_dokter == nama_dokter)
    if item_desc and item_desc.strip() != "" and item_desc.lower() != "all":
        query = query.filter(SimrsResep.item_code_desc == item_desc)
    if search and search.strip() != "":
        kw = f"%{search.strip().lower()}%"
        query = query.filter(or_(
            func.lower(SimrsResep.no_rekam_medik).like(kw),
            func.lower(SimrsResep.nama_pasien).like(kw),
            func.lower(SimrsResep.bill_number).like(kw)
        ))

    simrs_reps = query.all()

    # Map SIHA patients by normalized No RM (alphanumeric & numeric fallback)
    import re
    pasien_siha = db.query(Pasien).all()
    siha_rm_map = {}
    siha_num_map = {}
    for p in pasien_siha:
        if p.no_rekam_medik:
            clean_p_rm = re.sub(r'[^a-zA-Z0-9]', '', str(p.no_rekam_medik)).lower()
            num_p_rm = re.sub(r'\D', '', str(p.no_rekam_medik)).lstrip('0')
            if clean_p_rm:
                siha_rm_map[clean_p_rm] = p
            if num_p_rm:
                siha_num_map[num_p_rm] = p

    # Map latest kunjungan data for alasan_kunjungan
    latest_kunj_reason = {}
    for k in db.query(Kunjungan).order_by(Kunjungan.tanggal_kunjungan.desc()).all():
        if k.pasien_id and k.pasien_id not in latest_kunj_reason and k.alasan_kunjungan:
            latest_kunj_reason[str(k.pasien_id)] = k.alasan_kunjungan
        if k.no_rekam_medik:
            k_rm = re.sub(r'[^a-zA-Z0-9]', '', str(k.no_rekam_medik)).lower()
            if k_rm and k_rm not in latest_kunj_reason and k.alasan_kunjungan:
                latest_kunj_reason[k_rm] = k.alasan_kunjungan

    matched_records = []
    gap_records = []

    unique_simrs_rms = set()
    unique_matched_rms = set()
    unique_gap_rms = set()

    doctor_counts = {}
    item_counts = {}

    for r in simrs_reps:
        rm_raw = str(r.no_rekam_medik or "").strip()
        clean_rm = re.sub(r'[^a-zA-Z0-9]', '', rm_raw).lower()
        num_rm = re.sub(r'\D', '', rm_raw).lstrip('0')
        if not clean_rm:
            continue

        unique_simrs_rms.add(clean_rm)

        doc_name = str(r.nama_dokter or "Dokter Tidak Tercatat").strip()
        doctor_counts[doc_name] = doctor_counts.get(doc_name, 0) + 1

        item_d = str(r.item_code_desc or "ARV / Profilaksis").strip()
        item_counts[item_d] = item_counts.get(item_d, 0) + 1

        p_siha = siha_rm_map.get(clean_rm) or (siha_num_map.get(num_rm) if num_rm else None)

        alasan = None
        if p_siha:
            alasan = latest_kunj_reason.get(str(p_siha.pasien_id)) or latest_kunj_reason.get(clean_rm)
        elif clean_rm in latest_kunj_reason:
            alasan = latest_kunj_reason.get(clean_rm)

        if not alasan:
            item_lower = item_d.lower()
            nama_lower = str(r.nama_pasien or "").lower()
            if "by ny" in nama_lower or "by." in nama_lower or ("zidovudin" in item_lower and "100" in item_lower) or "sirup" in item_lower:
                alasan = "Profilaksis PPIA (Bayi Terpajan)"
            elif "profilaksis" in item_lower:
                alasan = "Profilaksis ARV / PPP"
            elif p_siha:
                alasan = "Kunjungan Rutin PDP (Master SIHA)"
            else:
                alasan = "Kunjungan Resep Farmasi (Belum Sync SIHA)"

        rec = {
            "id": r.id,
            "bill_number": r.bill_number or "-",
            "bill_date": r.bill_date or "-",
            "no_rekam_medik": r.no_rekam_medik or "-",
            "nama_pasien": r.nama_pasien or "-",
            "tanggal_lahir": r.tanggal_lahir or "-",
            "alasan_kunjungan": alasan,
            "item_code_desc": item_d,
            "qty": r.qty or 0,
            "nama_dokter": doc_name,
            "depo_name": r.depo_name or "Depo Rawat Jalan",
            "periode_sheet": r.periode_sheet or "-",
            "is_in_siha": bool(p_siha),
            "siha_pasien_id": p_siha.pasien_id if p_siha else None,
            "siha_status_pdp": p_siha.status_odhiv_pdp if p_siha else "BELUM INPUT SIHA",
            "audit_badge": "bg-emerald-100 text-emerald-800 border-emerald-300" if p_siha else "bg-rose-100 text-rose-800 border-rose-300",
            "audit_status": "MATCH (Terinput SIHA)" if p_siha else "GAP AUDIT (Belum Input SIHA)"
        }

        if p_siha:
            unique_matched_rms.add(clean_rm)
            matched_records.append(rec)
        else:
            unique_gap_rms.add(clean_rm)
            gap_records.append(rec)

    total_unique_simrs = len(unique_simrs_rms)
    total_unique_matched = len(unique_matched_rms)
    total_unique_gap = len(unique_gap_rms)

    compliance_rate = round((total_unique_matched / total_unique_simrs * 100), 1) if total_unique_simrs > 0 else 0.0
    gap_rate = round((total_unique_gap / total_unique_simrs * 100), 1) if total_unique_simrs > 0 else 0.0

    doctor_stats = [{"nama_dokter": d, "resep_count": c} for d, c in sorted(doctor_counts.items(), key=lambda x: x[1], reverse=True)[:15]]
    item_stats = [{"item_desc": i, "resep_count": c} for i, c in sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:15]]

    # Sort all arrays chronologically by bill_date desc
    all_combined_records = matched_records + gap_records
    all_combined_records.sort(key=lambda x: (x.get("bill_date") or "", x.get("id") or 0), reverse=True)
    matched_records.sort(key=lambda x: (x.get("bill_date") or "", x.get("id") or 0), reverse=True)
    gap_records.sort(key=lambda x: (x.get("bill_date") or "", x.get("id") or 0), reverse=True)

    return {
        "summary": {
            "total_simrs_resep": len(simrs_reps),
            "total_unique_simrs_patients": total_unique_simrs,
            "matched_patients_count": total_unique_matched,
            "gap_patients_count": total_unique_gap,
            "compliance_rate": compliance_rate,
            "gap_rate": gap_rate
        },
        "doctor_stats": doctor_stats,
        "item_stats": item_stats,
        "filter_options": {
            "periods": all_sheets,
            "depos": all_depos,
            "doctors": all_doctors,
            "items": all_items
        },
        "matched_records": matched_records,
        "gap_records": gap_records,
        "records": all_combined_records
    }
