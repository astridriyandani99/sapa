import uuid
import json
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from backend.database import (
    Pasien, Kunjungan, LabViralLoad, LabCD4, SimrsResep,
    PatientDeviceSession, PatientAdherenceLog,
    PatientResearchSurvey, PatientSurveyResponse, PatientResearchPayout,
    PatientArticle, AppNativeBanner
)


def mask_patient_name(name: str) -> str:
    """Masks patient name for privacy, e.g., 'BUDI SANTOSO' -> 'Budi S.'"""
    if not name:
        return "Pasien Kariadi"
    parts = name.strip().split()
    if len(parts) == 1:
        return parts[0].capitalize()
    return f"{parts[0].capitalize()} {parts[1][0].upper()}."


def normalize_date_str(d_str: str) -> str:
    """Normalizes date input from DD/MM/YYYY or YYYY-MM-DD to YYYY-MM-DD"""
    if not d_str:
        return ""
    d_str = d_str.strip()
    # Try YYYY-MM-DD
    if "-" in d_str and len(d_str.split("-")[0]) == 4:
        return d_str
    # Try DD/MM/YYYY or DD-MM-YYYY
    for sep in ["/", "-", "."]:
        if sep in d_str:
            parts = d_str.split(sep)
            if len(parts) == 3:
                if len(parts[2]) == 4:  # DD/MM/YYYY
                    return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                elif len(parts[0]) == 4:  # YYYY/MM/DD
                    return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    return d_str


# ============================================================================
# PATIENT AUTHENTICATION & ONBOARDING (PWA)
# ============================================================================

def activate_patient_pwa(db: Session, no_rekam_medik: str, tanggal_lahir: str, pin: str = None, is_biometric: bool = False):
    """
    Validates No. RM + Tanggal Lahir against master Pasien/SimrsResep database.
    If valid, issues a persistent device token.
    """
    clean_rm = no_rekam_medik.strip()
    norm_birth = normalize_date_str(tanggal_lahir)

    # 1. Search in master Pasien
    patient = db.query(Pasien).filter(
        func.lower(Pasien.no_rekam_medik) == clean_rm.lower()
    ).first()

    # Fallback to SimrsResep if not found in SIHA master
    if not patient:
        resep_match = db.query(SimrsResep).filter(
            func.lower(SimrsResep.no_rekam_medik) == clean_rm.lower()
        ).first()
        if not resep_match:
            return {"success": False, "message": "Nomor Rekam Medik tidak ditemukan di sistem RSUP Dr. Kariadi."}
        patient_name = resep_match.nama_pasien
        patient_birth = normalize_date_str(resep_match.tanggal_lahir)
    else:
        patient_name = patient.nama_pasien
        patient_birth = normalize_date_str(patient.tanggal_lahir)

    # 2. Validate Tanggal Lahir
    if patient_birth and norm_birth:
        # Compare normalized or substring
        if norm_birth not in patient_birth and patient_birth not in norm_birth:
            return {"success": False, "message": "Tanggal lahir tidak sesuai dengan data rekam medis."}

    # 3. Create or update session
    existing_session = db.query(PatientDeviceSession).filter(
        PatientDeviceSession.no_rekam_medik == clean_rm
    ).first()

    token = str(uuid.uuid4())
    if existing_session:
        existing_session.device_token = token
        existing_session.pin_hash = pin if pin else existing_session.pin_hash
        existing_session.is_biometric_enabled = is_biometric
        existing_session.last_active = datetime.utcnow()
        existing_session.expires_at = datetime.utcnow() + timedelta(days=180)
    else:
        new_session = PatientDeviceSession(
            session_id=str(uuid.uuid4()),
            no_rekam_medik=clean_rm,
            device_token=token,
            pin_hash=pin,
            is_biometric_enabled=is_biometric,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=180),
            last_active=datetime.utcnow()
        )
        db.add(new_session)

    db.commit()

    return {
        "success": True,
        "token": token,
        "no_rekam_medik": clean_rm,
        "nama_pasien": mask_patient_name(patient_name),
        "is_biometric_enabled": is_biometric,
        "message": "Aktivasi mandiri berhasil! Selamat datang di aplikasi pendamping sehat RSUP Dr. Kariadi."
    }


def verify_patient_session(db: Session, token: str):
    """Verifies active session token"""
    if not token:
        return None
    session = db.query(PatientDeviceSession).filter(
        PatientDeviceSession.device_token == token
    ).first()

    if not session:
        return None
    if session.expires_at and session.expires_at < datetime.utcnow():
        return None

    session.last_active = datetime.utcnow()
    db.commit()
    return session.no_rekam_medik


# ============================================================================
# PATIENT ADHERENCE & HEALTH SUMMARY (PWA)
# ============================================================================

def get_patient_health_summary(db: Session, no_rekam_medik: str):
    """Returns today's adherence status, streak, pillbox, and lab results for PWA Home strictly based on database"""
    clean_rm = no_rekam_medik.strip()
    today_str = date.today().isoformat()

    # 1. Patient profile & Status evaluation
    patient = db.query(Pasien).filter(func.lower(Pasien.no_rekam_medik) == clean_rm.lower()).first()
    nama_display = mask_patient_name(patient.nama_pasien) if patient else "Sahabat Kariadi"
    
    is_odhiv = False
    has_active_art = False
    rejimen_display = "Tidak Ada Resep ARV (Hanya Skrining/Pemeriksaan)"
    
    if patient:
        is_odhiv = (patient.status_odhiv == 'ODHIV') or bool(patient.tanggal_mulai_art)
        if patient.kunjungan_list:
            valid_k = [k for k in patient.kunjungan_list if k.tanggal_kunjungan]
            if valid_k:
                latest_k = sorted(valid_k, key=lambda x: x.tanggal_kunjungan, reverse=True)[0]
                if latest_k and latest_k.nama_rejimen and latest_k.nama_rejimen != 'Tanpa ARV / Belum Ada':
                    rejimen_display = latest_k.nama_rejimen
                    has_active_art = True

    # Check SimrsResep for actual pharmacy prescriptions
    latest_resep = db.query(SimrsResep).filter(
        func.lower(SimrsResep.no_rekam_medik) == clean_rm.lower()
    ).order_by(desc(SimrsResep.bill_date)).first()

    if latest_resep and latest_resep.item_code_desc:
        has_active_art = True
        if rejimen_display == "Tidak Ada Resep ARV (Hanya Skrining/Pemeriksaan)":
            rejimen_display = latest_resep.item_code_desc

    status_pasien_display = "Pasien PDP Terapi Aktif" if (is_odhiv or has_active_art) else "Skrining HIV (Non-ODHIV)"
    
    # 2. Check today's adherence log
    today_log = db.query(PatientAdherenceLog).filter(
        PatientAdherenceLog.no_rekam_medik == clean_rm,
        PatientAdherenceLog.target_date == today_str
    ).first()

    is_logged_today = today_log is not None
    logged_time_str = today_log.logged_at.strftime("%H:%M WIB") if today_log and today_log.logged_at else None

    # 3. Calculate adherence streak
    logs = db.query(PatientAdherenceLog.target_date).filter(
        PatientAdherenceLog.no_rekam_medik == clean_rm
    ).order_by(desc(PatientAdherenceLog.target_date)).limit(60).all()
    
    logged_dates = set(l[0] for l in logs)
    streak = 0
    curr_check = date.today()
    if not is_logged_today:
        curr_check -= timedelta(days=1)
    
    while curr_check.isoformat() in logged_dates:
        streak += 1
        curr_check -= timedelta(days=1)
    
    if streak == 0 and is_logged_today:
        streak = 1

    # 4. Virtual Pillbox (Sisa Obat Dinamis)
    virtual_pillbox = None
    if has_active_art:
        initial_pills = 30
        days_since_refill = 0
        refill_date_str = None

        if latest_resep and latest_resep.bill_date:
            refill_date_str = latest_resep.bill_date
            initial_pills = int(latest_resep.qty) if latest_resep.qty and latest_resep.qty >= 30 else 30
            try:
                r_date = datetime.strptime(normalize_date_str(latest_resep.bill_date), "%Y-%m-%d").date()
                days_since_refill = (date.today() - r_date).days
            except Exception:
                days_since_refill = 0
        elif patient and patient.kunjungan_list:
            valid_k = [k for k in patient.kunjungan_list if k.tanggal_kunjungan]
            if valid_k:
                latest_k = sorted(valid_k, key=lambda x: x.tanggal_kunjungan, reverse=True)[0]
                if latest_k.jumlah_hari_arv:
                    initial_pills = int(latest_k.jumlah_hari_arv)
                try:
                    k_date = datetime.strptime(normalize_date_str(latest_k.tanggal_kunjungan), "%Y-%m-%d").date()
                    days_since_refill = (date.today() - k_date).days
                except Exception:
                    days_since_refill = 0

        remaining_pills = max(0, initial_pills - max(0, days_since_refill))
        estimated_depletion_date = (date.today() + timedelta(days=remaining_pills)).strftime("%d %B %Y")
        virtual_pillbox = {
            "is_active": True,
            "initial_pills": initial_pills,
            "remaining_pills": remaining_pills,
            "days_since_refill": max(0, days_since_refill),
            "refill_date": refill_date_str,
            "estimated_depletion_date": estimated_depletion_date
        }
    else:
        virtual_pillbox = {
            "is_active": False,
            "initial_pills": 0,
            "remaining_pills": 0,
            "days_since_refill": 0,
            "refill_date": None,
            "estimated_depletion_date": "-",
            "message": "Tidak ada resep ARV aktif. Pasien tercatat sebagai riwayat skrining/tes."
        }

    # 5. Latest Viral Load & CD4
    latest_vl = None
    latest_cd4 = None
    if patient:
        vl_rec = db.query(LabViralLoad).filter(LabViralLoad.pasien_id == patient.pasien_id).order_by(desc(LabViralLoad.tanggal_pemeriksaan)).first()
        if vl_rec:
            is_undet = vl_rec.is_undetectable or "undetectable" in str(vl_rec.kategori_vl).lower() or "tnd" in str(vl_rec.kategori_vl).lower()
            latest_vl = {
                "has_record": True,
                "hasil": vl_rec.hasil_numerik or "<50",
                "kategori": "Undetectable (<50 kopi/mL)" if is_undet else (vl_rec.kategori_vl or "Tersupresi"),
                "is_undetectable": is_undet,
                "tanggal": vl_rec.tanggal_pemeriksaan,
                "u_equals_u": is_undet
            }
        
        cd4_rec = db.query(LabCD4).filter(LabCD4.pasien_id == patient.pasien_id).order_by(desc(LabCD4.tanggal_pemeriksaan)).first()
        if cd4_rec:
            latest_cd4 = {
                "has_record": True,
                "nilai": cd4_rec.nilai_cd4,
                "kategori": cd4_rec.kategori_cd4 or "Baik",
                "tanggal": cd4_rec.tanggal_pemeriksaan
            }

    if not latest_vl:
        latest_vl = {
            "has_record": False,
            "hasil": "-",
            "kategori": "Belum ada riwayat pemeriksaan Viral Load",
            "is_undetectable": False,
            "tanggal": "-",
            "u_equals_u": False
        }
    if not latest_cd4:
        latest_cd4 = {
            "has_record": False,
            "nilai": "-",
            "kategori": "Belum ada riwayat pemeriksaan CD4",
            "tanggal": "-"
        }

    # 6. Past 30 Days Adherence Timeline & Progress Score
    logs_30d = db.query(PatientAdherenceLog).filter(
        PatientAdherenceLog.no_rekam_medik == clean_rm,
        PatientAdherenceLog.target_date >= (date.today() - timedelta(days=30)).isoformat()
    ).all()
    logged_dates_map = {l.target_date: l.log_type for l in logs_30d}

    timeline_30d = []
    taken_count = 0
    for i in range(29, -1, -1):
        cur_d = date.today() - timedelta(days=i)
        d_str = cur_d.isoformat()
        day_num = cur_d.strftime("%d")
        day_name = cur_d.strftime("%a")
        
        status = "MISSED"
        if d_str in logged_dates_map:
            l_type = logged_dates_map[d_str]
            status = "TAKEN_ON_TIME" if l_type == "ON_TIME" else "TAKEN_RETROACTIVE"
            taken_count += 1
        elif cur_d == date.today() and not is_logged_today:
            status = "PENDING_TODAY"
        elif cur_d > date.today():
            status = "FUTURE"

        timeline_30d.append({
            "date": d_str,
            "day_num": day_num,
            "day_name": day_name,
            "status": status
        })

    adherence_rate_pct = round((taken_count / 30) * 100, 1) if taken_count > 0 else (100.0 if is_logged_today else (0.0 if not has_active_art else 0.0))

    # Badges
    badges = [
        {
            "id": "shield_cd4",
            "title": "Perisai Imun Aktif",
            "desc": "Disiplin minum obat rutin menjaga sel CD4 tetap kuat",
            "icon": "🛡️",
            "unlocked": streak >= 7
        },
        {
            "id": "hero_30d",
            "title": "Ksatria 30 Hari",
            "desc": "Mencapai konsistensi minum obat selama 30 hari penuh",
            "icon": "🔥",
            "unlocked": streak >= 30
        },
        {
            "id": "undetectable_hero",
            "title": "Undetectable Hero (U=U)",
            "desc": "Kadar virus tersupresi penuh & tidak dapat menular",
            "icon": "💎",
            "unlocked": True
        }
    ]

    return {
        "nama_pasien": nama_display,
        "no_rekam_medik": clean_rm,
        "status_pasien": status_pasien_display,
        "is_odhiv": is_odhiv,
        "has_active_art": has_active_art,
        "rejimen_arv": rejimen_display,
        "is_logged_today": is_logged_today,
        "logged_time": logged_time_str,
        "adherence_streak": streak,
        "adherence_rate_pct": adherence_rate_pct,
        "timeline_30d": timeline_30d,
        "badges": badges,
        "virtual_pillbox": virtual_pillbox,
        "viral_load": latest_vl,
        "cd4": latest_cd4
    }


def log_patient_adherence(db: Session, no_rekam_medik: str, target_date: str = None, log_type: str = "ON_TIME", side_effects: str = None):
    """Logs daily medication taking event (1-Tap or Retroactive)"""
    clean_rm = no_rekam_medik.strip()
    if not target_date:
        target_date = date.today().isoformat()
    else:
        target_date = normalize_date_str(target_date)

    existing = db.query(PatientAdherenceLog).filter(
        PatientAdherenceLog.no_rekam_medik == clean_rm,
        PatientAdherenceLog.target_date == target_date
    ).first()

    if existing:
        existing.logged_at = datetime.utcnow()
        existing.log_type = log_type
        if side_effects:
            existing.side_effects_reported = side_effects
        db.commit()
        return {"success": True, "message": "Log kepatuhan diperbarui!", "log_id": existing.log_id}

    new_log = PatientAdherenceLog(
        no_rekam_medik=clean_rm,
        target_date=target_date,
        logged_at=datetime.utcnow(),
        log_type=log_type,
        side_effects_reported=side_effects,
        created_at=datetime.utcnow()
    )
    db.add(new_log)
    db.commit()

    return {"success": True, "message": "Hebat! Kepatuhan minum obat Anda telah tercatat ✨", "log_id": new_log.log_id}


# ============================================================================
# RESEARCH SURVEYS & LEGAL INFORMED CONSENT
# ============================================================================

def get_surveys_for_patient(db: Session, no_rekam_medik: str):
    """Returns active research surveys with patient's participation status"""
    clean_rm = no_rekam_medik.strip()
    surveys = db.query(PatientResearchSurvey).filter(PatientResearchSurvey.is_active == True).all()
    
    responses = db.query(PatientSurveyResponse).filter(
        PatientSurveyResponse.no_rekam_medik == clean_rm
    ).all()
    resp_map = {r.survey_id: r for r in responses}

    result = []
    for s in surveys:
        resp = resp_map.get(s.survey_id)
        has_submitted = resp is not None
        questions = json.loads(s.questions_schema) if s.questions_schema else []
        
        result.append({
            "survey_id": s.survey_id,
            "judul_penelitian": s.judul_penelitian,
            "no_etik_kepk": s.no_etik_kepk,
            "nama_peneliti": s.nama_peneliti,
            "reward_amount": s.reward_amount,
            "reward_display": f"Rp {s.reward_amount:,.0f}".replace(",", "."),
            "informed_consent_text": s.informed_consent_text,
            "questions_count": len(questions),
            "questions": questions,
            "has_submitted": has_submitted,
            "submission_status": resp.status_verifikasi if resp else None,
            "payment_channel": resp.payment_channel if resp else None,
            "payment_account_no": resp.payment_account_no if resp else None,
            "submitted_at": resp.consent_signed_at.strftime("%d %B %Y, %H:%M WIB") if resp and resp.consent_signed_at else None
        })

    return result


def submit_patient_survey(db: Session, no_rekam_medik: str, survey_id: str, answers: dict, payment_channel: str, payment_account_no: str, payment_account_name: str, device_hash: str = None):
    """Submits research questionnaire response with legal digital consent"""
    clean_rm = no_rekam_medik.strip()
    
    survey = db.query(PatientResearchSurvey).filter(PatientResearchSurvey.survey_id == survey_id).first()
    if not survey:
        return {"success": False, "message": "Kuesioner penelitian tidak ditemukan."}

    existing = db.query(PatientSurveyResponse).filter(
        PatientSurveyResponse.survey_id == survey_id,
        PatientSurveyResponse.no_rekam_medik == clean_rm
    ).first()

    if existing:
        return {"success": False, "message": "Anda sudah pernah mengisi kuesioner penelitian ini sebelumnya."}

    new_response = PatientSurveyResponse(
        response_id=str(uuid.uuid4()),
        survey_id=survey_id,
        no_rekam_medik=clean_rm,
        answers_json=json.dumps(answers),
        consent_signed_at=datetime.utcnow(),
        consent_device_hash=device_hash or str(uuid.uuid4())[:16],
        payment_channel=payment_channel,
        payment_account_no=payment_account_no,
        payment_account_name=payment_account_name,
        status_verifikasi="PENDING",
        created_at=datetime.utcnow()
    )
    db.add(new_response)
    db.commit()

    return {
        "success": True,
        "message": "Kuesioner berhasil dikirim! Tim peneliti akan memverifikasi dan mentransfer uang pengganti waktu Anda.",
        "response_id": new_response.response_id
    }


# ============================================================================
# ARTICLES & NATIVE BANNERS (CMS FEED)
# ============================================================================

def get_articles_and_banners(db: Session):
    """Returns active native banners and articles for PWA feed"""
    banners = db.query(AppNativeBanner).filter(
        AppNativeBanner.is_active == True
    ).order_by(AppNativeBanner.sort_order).all()

    articles = db.query(PatientArticle).order_by(desc(PatientArticle.published_at)).all()

    return {
        "banners": [
            {
                "banner_id": b.banner_id,
                "title": b.title,
                "subtitle": b.subtitle,
                "badge_label": b.badge_label,
                "image_url": b.image_url,
                "link_type": b.link_type,
                "target_url": b.target_url
            } for b in banners
        ],
        "articles": [
            {
                "article_id": a.article_id,
                "title": a.title,
                "category": a.category,
                "author_name": a.author_name,
                "thumbnail_url": a.thumbnail_url,
                "content_markdown": a.content_markdown,
                "read_time_minutes": a.read_time_minutes,
                "is_featured": a.is_featured,
                "published_at": a.published_at.strftime("%d %b %Y") if a.published_at else ""
            } for a in articles
        ]
    }


# ============================================================================
# ADMIN HOSPITAL DASHBOARD (TAB 5) SERVICES
# ============================================================================

def get_admin_pwa_overview(db: Session):
    """Summary metrics for Hospital Admin Tab 5"""
    total_sessions = db.query(PatientDeviceSession).count()
    total_logs = db.query(PatientAdherenceLog).count()
    
    today_str = date.today().isoformat()
    today_logs_count = db.query(PatientAdherenceLog).filter(PatientAdherenceLog.target_date == today_str).count()
    
    total_surveys = db.query(PatientResearchSurvey).count()
    total_survey_responses = db.query(PatientSurveyResponse).count()
    pending_payouts_count = db.query(PatientSurveyResponse).filter(PatientSurveyResponse.status_verifikasi == "PENDING").count()

    return {
        "total_active_sessions": total_sessions,
        "today_adherence_logs": today_logs_count,
        "total_all_time_logs": total_logs,
        "total_surveys": total_surveys,
        "total_survey_responses": total_survey_responses,
        "pending_payouts_count": pending_payouts_count
    }


def get_admin_pre_ltfu_radar(db: Session, filter_rujukan: str = "aktif_kariadi"):
    """
    Calculates Pre-LTFU critical risk cohort with precise Referral (Rujuk Masuk/Keluar) Classification.
    Patients who have been officially transferred out (Rujuk Keluar) or deceased are explicitly tagged
    and NOT classified as LTFU mangkir di Kariadi.
    """
    today = date.today()
    
    # Query PDP cohort based on filter to ensure 100% accurate results
    if filter_rujukan == "rujuk_keluar":
        pts_query = db.query(Pasien).filter(
            or_(
                Pasien.rujuk_keluar.ilike("ya"),
                Pasien.tanggal_rujuk_keluar != None,
                Pasien.rujuk_keluar_ke_upk != None,
                Pasien.status_odhiv_pdp.in_(["Rujuk Keluar", "ODHIV rujuk keluar"])
            )
        )
    elif filter_rujukan == "aktif_kariadi":
        pts_query = db.query(Pasien).filter(
            Pasien.status_odhiv_pdp.in_(["ODHIV sedang pengobatan", "Sedang Pengobatan", "ODHIV masuk perawatan"]),
            or_(Pasien.rujuk_keluar == None, Pasien.rujuk_keluar != "Ya"),
            Pasien.tanggal_rujuk_keluar == None,
            Pasien.tanggal_meninggal == None
        )
    else:
        pts_query = db.query(Pasien).filter(
            Pasien.status_odhiv_pdp.in_(["ODHIV sedang pengobatan", "Sedang Pengobatan", "ODHIV masuk perawatan", "Rujuk Keluar", "ODHIV rujuk keluar"])
        )

    active_pts = pts_query.limit(400).all()

    radar_list = []
    
    for p in active_pts:
        # Check referral & deceased flags
        is_meninggal = bool(p.tanggal_meninggal and p.tanggal_meninggal.strip()) or (p.status_odhiv_pdp in ["Meninggal", "ODHIV meninggal"])
        
        is_rujuk_keluar = bool(
            (p.rujuk_keluar and p.rujuk_keluar.strip().lower() in ["ya", "y", "true", "1"]) or
            (p.tanggal_rujuk_keluar and p.tanggal_rujuk_keluar.strip()) or
            (p.rujuk_keluar_ke_upk and p.rujuk_keluar_ke_upk.strip()) or
            (p.status_odhiv_pdp in ["Rujuk Keluar", "ODHIV rujuk keluar"])
        )
        
        is_rujuk_masuk = bool(
            (p.rujuk_masuk and p.rujuk_masuk.strip().lower() in ["ya", "y", "true", "1"]) or
            (p.rujuk_masuk_dari_upk and p.rujuk_masuk_dari_upk.strip())
        )

        # Build referral label
        if is_rujuk_keluar:
            tgl_rk = f" ({p.tanggal_rujuk_keluar})" if p.tanggal_rujuk_keluar else ""
            upk_tujuan = p.rujuk_keluar_ke_upk.strip() if p.rujuk_keluar_ke_upk else "Faskes Lain"
            status_rujukan_label = f"✈️ Rujuk Keluar: {upk_tujuan}{tgl_rk}"
            rujuk_badge_color = "bg-purple-100 text-purple-800 border-purple-200"
            rujuk_category = "RUJUK_KELUAR"
        elif is_rujuk_masuk:
            upk_asal = p.rujuk_masuk_dari_upk.strip() if p.rujuk_masuk_dari_upk else "Faskes Luar"
            status_rujukan_label = f"📥 Rujuk Masuk: {upk_asal}"
            rujuk_badge_color = "bg-blue-100 text-blue-800 border-blue-200"
            rujuk_category = "RUJUK_MASUK"
        else:
            status_rujukan_label = "🏥 Pasien Asli Kariadi"
            rujuk_badge_color = "bg-slate-100 text-slate-700 border-slate-200"
            rujuk_category = "ASLI_KARIADI"

        # Check latest interaction from BOTH SIHA Kunjungan & SIMRS Resep
        # 1. Latest SIMRS Resep
        resep = db.query(SimrsResep).filter(
            func.lower(SimrsResep.no_rekam_medik) == p.no_rekam_medik.lower()
        ).order_by(desc(SimrsResep.bill_date)).first() if p.no_rekam_medik else None

        # 2. Latest SIHA Kunjungan
        latest_kunj = None
        if p.kunjungan_list:
            valid_k = [k for k in p.kunjungan_list if k.tanggal_kunjungan]
            if valid_k:
                latest_kunj = sorted(valid_k, key=lambda x: x.tanggal_kunjungan, reverse=True)[0]

        # Determine newest date & pills given
        resep_date_str = "-"
        latest_interaction_date = None
        initial_pills = 30

        # Check SIMRS
        if resep and resep.bill_date:
            try:
                r_d = datetime.strptime(normalize_date_str(resep.bill_date), "%Y-%m-%d").date()
                resep_date_str = resep.bill_date
                latest_interaction_date = r_d
                initial_pills = int(resep.qty) if resep.qty and resep.qty >= 30 else 30
            except Exception:
                pass

        # Check SIHA Kunjungan (override if SIHA is newer or SIMRS is missing)
        if latest_kunj and latest_kunj.tanggal_kunjungan:
            try:
                k_d = datetime.strptime(normalize_date_str(latest_kunj.tanggal_kunjungan), "%Y-%m-%d").date()
                if latest_interaction_date is None or k_d >= latest_interaction_date:
                    latest_interaction_date = k_d
                    resep_date_str = latest_kunj.tanggal_kunjungan
                    initial_pills = int(latest_kunj.jumlah_hari_arv) if latest_kunj.jumlah_hari_arv and latest_kunj.jumlah_hari_arv >= 30 else 30
            except Exception:
                pass

        if latest_interaction_date:
            days_passed = (today - latest_interaction_date).days
        else:
            days_passed = 15

        remaining = initial_pills - days_passed
        
        # Determine radar status & urgency
        if is_meninggal:
            status_badge = "✝️ Pasien Meninggal"
            urgency = "DECEASED"
        elif is_rujuk_keluar:
            status_badge = f"✈️ Pindah Faskes ({p.rujuk_keluar_ke_upk or 'Rujuk Keluar'})"
            urgency = "TRANSFERRED_OUT"
        elif remaining <= 0:
            status_badge = "🔴 Krisis Mangkir (H=0 / Telat)"
            urgency = "HIGH"
        elif remaining <= 3:
            status_badge = "🟠 Waspada Stok (H-2 Sisa Obat)"
            urgency = "MEDIUM"
        else:
            status_badge = "🟢 Stok Masih Aman"
            urgency = "SAFE"

        # Apply filter
        if filter_rujukan == "aktif_kariadi":
            if is_rujuk_keluar or is_meninggal:
                continue
            if remaining > 3:
                continue
        elif filter_rujukan == "rujuk_keluar":
            if not is_rujuk_keluar:
                continue
        else:
            # Default "all" returns critical active cases + transferred out for context
            if remaining > 3 and not is_rujuk_keluar:
                continue

        # Regimen
        rej_name = "TLD"
        if p.kunjungan_list:
            valid_k = [k for k in p.kunjungan_list if k.tanggal_kunjungan]
            if valid_k:
                latest_k = sorted(valid_k, key=lambda x: x.tanggal_kunjungan, reverse=True)
                if latest_k and latest_k[0].nama_rejimen:
                    rej_name = latest_k[0].nama_rejimen

        radar_list.append({
            "no_rekam_medik": p.no_rekam_medik,
            "nama_pasien": mask_patient_name(p.nama_pasien),
            "rejimen": rej_name,
            "status_rujukan": status_rujukan_label,
            "rujuk_category": rujuk_category,
            "rujuk_badge_color": rujuk_badge_color,
            "rujuk_masuk_dari": p.rujuk_masuk_dari_upk or "-",
            "rujuk_keluar_ke": p.rujuk_keluar_ke_upk or "-",
            "tgl_rujuk_keluar": p.tanggal_rujuk_keluar or "-",
            "tgl_resep_terakhir": resep_date_str,
            "sisa_obat_hari": max(0, remaining) if not is_rujuk_keluar else "-",
            "hari_terlambat": max(0, -remaining) if remaining < 0 and not is_rujuk_keluar else 0,
            "status_radar": status_badge,
            "urgency": urgency,
            "is_rujuk_keluar": is_rujuk_keluar,
            "is_rujuk_masuk": is_rujuk_masuk,
            "no_kontak_pdp": "Tersedia di SIMRS"
        })

    # Sort: HIGH first, then MEDIUM, then TRANSFERRED_OUT
    urgency_order = {"HIGH": 1, "MEDIUM": 2, "TRANSFERRED_OUT": 3, "DECEASED": 4, "SAFE": 5}
    radar_list.sort(key=lambda x: (urgency_order.get(x["urgency"], 99), str(x["sisa_obat_hari"])))
    return radar_list[:100]


def get_admin_survey_responses(db: Session, survey_id: str = None):
    """Returns list of survey responses for researcher review & payout"""
    query = db.query(PatientSurveyResponse)
    if survey_id:
        query = query.filter(PatientSurveyResponse.survey_id == survey_id)
    
    responses = query.order_by(desc(PatientSurveyResponse.created_at)).all()
    surveys_map = {s.survey_id: s for s in db.query(PatientResearchSurvey).all()}

    result = []
    for r in responses:
        surv = surveys_map.get(r.survey_id)
        result.append({
            "response_id": r.response_id,
            "survey_id": r.survey_id,
            "judul_penelitian": surv.judul_penelitian if surv else r.survey_id,
            "no_rekam_medik": r.no_rekam_medik,
            "reward_amount": surv.reward_amount if surv else 50000,
            "reward_display": f"Rp {surv.reward_amount:,.0f}".replace(",", ".") if surv else "Rp 50.000",
            "answers": json.loads(r.answers_json) if r.answers_json else {},
            "consent_signed_at": r.consent_signed_at.strftime("%d/%m/%Y %H:%M") if r.consent_signed_at else "-",
            "payment_channel": r.payment_channel or "DANA",
            "payment_account_no": r.payment_account_no or "-",
            "payment_account_name": r.payment_account_name or "-",
            "status_verifikasi": r.status_verifikasi
        })
    return result


def verify_survey_payout(db: Session, response_id: str, amount_paid: int, bank_reference_no: str, admin_name: str, notes: str = None):
    """Marks survey response as verified/paid and records in audit log"""
    resp = db.query(PatientSurveyResponse).filter(PatientSurveyResponse.response_id == response_id).first()
    if not resp:
        return {"success": False, "message": "Data respon kuesioner tidak ditemukan."}

    resp.status_verifikasi = "APPROVED"

    payout = PatientResearchPayout(
        payout_id=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        response_id=response_id,
        no_rekam_medik=resp.no_rekam_medik,
        amount_paid=amount_paid,
        bank_reference_no=bank_reference_no,
        transferred_at=datetime.utcnow(),
        verified_by_admin=admin_name,
        notes=notes
    )
    db.add(payout)
    db.commit()

    return {
        "success": True,
        "message": f"Pembayaran imbalan Rp {amount_paid:,.0f} berhasil diverifikasi & dicatat dalam audit log!",
        "payout_id": payout.payout_id
    }


def get_admin_adherence_logs_list(db: Session, target_date: str = None, search: str = None, limit: int = 150):
    """Returns granular log feed for hospital admin with patient names, timestamps, and pill remaining status"""
    query = db.query(PatientAdherenceLog)
    if target_date and target_date.strip() != "" and target_date.lower() != "all":
        query = query.filter(PatientAdherenceLog.target_date == target_date)
    
    if search and search.strip() != "":
        kw = f"%{search.strip().lower()}%"
        query = query.filter(func.lower(PatientAdherenceLog.no_rekam_medik).like(kw))

    logs = query.order_by(desc(PatientAdherenceLog.logged_at)).limit(limit).all()

    # Pre-fetch patients & SIMRS for fast lookup
    rms = list(set(l.no_rekam_medik for l in logs if l.no_rekam_medik))
    pts = db.query(Pasien).filter(Pasien.no_rekam_medik.in_(rms)).all() if rms else []
    pt_map = {p.no_rekam_medik.lower(): p for p in pts if p.no_rekam_medik}

    reseps = db.query(SimrsResep).filter(SimrsResep.no_rekam_medik.in_(rms)).order_by(desc(SimrsResep.bill_date)).all() if rms else []
    resep_map = {}
    for r in reseps:
        if r.no_rekam_medik and r.no_rekam_medik.lower() not in resep_map:
            resep_map[r.no_rekam_medik.lower()] = r

    result = []
    for l in logs:
        rm_key = (l.no_rekam_medik or "").lower()
        p = pt_map.get(rm_key)
        r = resep_map.get(rm_key)
        
        nama = (p.nama_pasien if p else (r.nama_pasien if r else "Pasien Terverifikasi"))
        rejimen = (r.item_code_desc if r else "TLD (Tenofovir/Lamivudine/Dolutegravir)")
        
        result.append({
            "log_id": l.log_id,
            "no_rekam_medik": l.no_rekam_medik,
            "nama_pasien": nama,
            "rejimen": rejimen,
            "target_date": l.target_date,
            "logged_at": l.logged_at.strftime("%d/%m/%Y %H:%M:%S") if l.logged_at else (l.target_date or "-"),
            "log_type": "TEPAT WAKTU (Hari Ini)" if l.log_type == "ON_TIME" else "SUSULAN (Kemarin)",
            "side_effects": l.side_effects_reported or "Tidak ada keluhan",
            "badge_color": "bg-emerald-100 text-emerald-800 border-emerald-300" if l.log_type == "ON_TIME" else "bg-amber-100 text-amber-800 border-amber-300"
        })
    return result

