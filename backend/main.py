import os
import io
from typing import Optional, List
from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db, init_db, Pasien, Kunjungan, LabViralLoad, LabCD4, UploadHistory, BASE_DIR
from backend.importer import process_file_upload, auto_seed_local_files
from backend.simrs_importer import auto_seed_simrs_arv
from backend.analytics import get_executive_metrics, get_research_cohort_data, get_pediatric_dashboard_data, get_simrs_audit_data
from backend.export_service import generate_research_excel, generate_research_csv, generate_pediatric_excel

app = FastAPI(
    title="SIHA & SIMRS Analytics Dashboard",
    description="Sistem Analitik Data Surveilans HIV-AIDS & Rekam Medis Rumah Sakit",
    version="1.0.0"
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
os.makedirs(FRONTEND_DIR, exist_ok=True)

# Pydantic schema for research filter
class ResearchFilterRequest(BaseModel):
    search: Optional[str] = None
    gender: Optional[List[str]] = None
    populasi: Optional[List[str]] = None
    stadium: Optional[List[str]] = None
    rejimen: Optional[List[str]] = None
    kategori_vl: Optional[List[str]] = None
    kategori_imt: Optional[List[str]] = None
    kategori_cd4: Optional[List[str]] = None
    status_pdp: Optional[List[str]] = None
    kelompok_umur_klinis: Optional[List[str]] = None
    status_hamil: Optional[List[str]] = None
    is_mmd: Optional[bool] = None
    ltfu_kategori: Optional[List[str]] = None
    koinfeksi_tb: Optional[List[str]] = None
    kepatuhan: Optional[List[str]] = None
    durasi_art: Optional[List[str]] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    date_kunj_start: Optional[str] = None
    date_kunj_end: Optional[str] = None
    search: Optional[str] = ""

class ExportRequest(BaseModel):
    filters: ResearchFilterRequest
    format: str = "excel"  # "excel" or "csv"
    anonymize: bool = True

@app.on_event("startup")
def on_startup():
    init_db()
    # Auto-seed existing local files if database is fresh
    try:
        auto_seed_local_files()
        auto_seed_simrs_arv()
    except Exception as e:
        print(f"Error during initial seeding: {e}")

@app.get("/api/dashboard/audit")
def get_simrs_audit_dashboard(
    period_sheet: Optional[str] = Query(None),
    depo_name: Optional[str] = Query(None),
    nama_dokter: Optional[str] = Query(None),
    item_desc: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    return get_simrs_audit_data(
        db,
        period_sheet=period_sheet,
        depo_name=depo_name,
        nama_dokter=nama_dokter,
        item_desc=item_desc,
        search=search
    )

@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Frontend sedang diinisialisasi...</h1>"

@app.get("/api/system/status")
def get_system_status(db: Session = Depends(get_db)):
    return {
        "status": "ONLINE",
        "total_pasien": db.query(Pasien).count(),
        "total_kunjungan": db.query(Kunjungan).count(),
        "total_viral_load": db.query(LabViralLoad).count(),
        "total_cd4": db.query(LabCD4).count(),
        "last_upload": db.query(UploadHistory).order_by(UploadHistory.uploaded_at.desc()).first()
    }

@app.get("/api/upload/history")
def get_upload_history(db: Session = Depends(get_db)):
    history = db.query(UploadHistory).order_by(UploadHistory.uploaded_at.desc()).limit(20).all()
    return [{
        "id": h.id,
        "filename": h.filename,
        "file_type": h.file_type,
        "uploaded_at": h.uploaded_at.strftime("%Y-%m-%d %H:%M:%S") if h.uploaded_at else "-",
        "rows_processed": h.rows_processed,
        "rows_inserted": h.rows_inserted,
        "rows_updated": h.rows_updated,
        "status": h.status,
        "details": h.details
    } for h in history]

@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    file_type: Optional[str] = Form(None)
):
    try:
        contents = await file.read()
        res = process_file_upload(io.BytesIO(contents), file.filename, forced_type=file_type)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/dashboard/executive")
def get_executive_dashboard(
    date_start: Optional[str] = Query(None),
    date_end: Optional[str] = Query(None),
    period_preset: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    return get_executive_metrics(db, date_start=date_start, date_end=date_end, period_preset=period_preset)

@app.post("/api/dashboard/research")
def get_research_dashboard(payload: ResearchFilterRequest, db: Session = Depends(get_db)):
    filters = payload.dict()
    result = get_research_cohort_data(db, filters)
    return result

@app.get("/api/dashboard/pediatric")
def get_pediatric_dashboard(period_month: Optional[str] = Query(None), db: Session = Depends(get_db)):
    return get_pediatric_dashboard_data(db, period_month=period_month)

@app.get("/api/export/pediatric")
def export_pediatric_data(
    period_month: Optional[str] = Query(None),
    filter_type: Optional[str] = Query("all"),
    anonymize: bool = Query(False),
    db: Session = Depends(get_db)
):
    data = get_pediatric_dashboard_data(db, period_month=period_month)
    records = data["records"]
    
    filter_label = "Semua Kohor Anak (<18 Th)"
    if filter_type == "odhiv":
        records = [r for r in records if r.get("status_anak_detail") and "Terkonfirmasi ODHIV" in r["status_anak_detail"]]
        filter_label = "Anak Terkonfirmasi ODHIV (Terapi ARV)"
    elif filter_type == "prophylaxis":
        records = [r for r in records if r.get("status_anak_detail") and "Terpajan" in r["status_anak_detail"]]
        filter_label = "Bayi Terpajan (Profilaksis PPIA)"
    elif filter_type == "negative":
        records = [r for r in records if r.get("status_anak_detail") and "Non-Reaktif" in r["status_anak_detail"]]
        filter_label = "Skrining Non-Reaktif (Bukan ODHIV)"
        
    period_label = period_month if (period_month and period_month.lower() != "all") else "Semua Bulan Kunjungan"
    
    buf = generate_pediatric_excel(records, period_label=period_label, filter_type=filter_label, anonymize=anonymize)
    filename = f"Kohor_Anak_PPIA_Kariadi_{filter_type}_{period_month or 'All'}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/export")
def export_research_data(payload: ExportRequest, db: Session = Depends(get_db)):
    filters = payload.filters.dict()
    result = get_research_cohort_data(db, filters)
    records = result["records"]

    if payload.format.lower() == "csv":
        buf = generate_research_csv(records, anonymize=payload.anonymize)
        filename = f"SIHA_Research_Export_{'Anon' if payload.anonymize else 'Raw'}.csv"
        return StreamingResponse(
            buf,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        buf = generate_research_excel(records, filters, anonymize=payload.anonymize)
        filename = f"SIHA_Research_Export_{'Anon' if payload.anonymize else 'Raw'}.xlsx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

from backend.pwa_service import (
    activate_patient_pwa, verify_patient_session, get_patient_health_summary,
    log_patient_adherence, get_surveys_for_patient, submit_patient_survey,
    get_articles_and_banners, get_admin_pwa_overview, get_admin_pre_ltfu_radar,
    get_admin_survey_responses, verify_survey_payout, get_admin_adherence_logs_list
)

# Pydantic schemas for PWA
class PwaActivationRequest(BaseModel):
    no_rekam_medik: str
    tanggal_lahir: str
    pin: Optional[str] = None
    is_biometric: Optional[bool] = False

class PwaAdherenceLogRequest(BaseModel):
    no_rekam_medik: str
    target_date: Optional[str] = None
    log_type: Optional[str] = "ON_TIME"
    side_effects: Optional[str] = None

class PwaSurveySubmitRequest(BaseModel):
    no_rekam_medik: str
    survey_id: str
    answers: dict
    payment_channel: str
    payment_account_no: str
    payment_account_name: str
    device_hash: Optional[str] = None

class AdminPayoutVerifyRequest(BaseModel):
    response_id: str
    amount_paid: int
    bank_reference_no: str
    admin_name: str
    notes: Optional[str] = None

@app.get("/api/template/cd4")
def get_cd4_template():
    import pandas as pd
    sample_df = pd.DataFrame([
        {"Pasien ID": "3507969", "No Rekam Medik": "D111621", "Tanggal Pemeriksaan": "2026-08-15", "Nilai CD4": 485, "Keterangan": "Pemeriksaan Rutin Baseline"},
        {"Pasien ID": "15861148", "No Rekam Medik": "d411352", "Tanggal Pemeriksaan": "2026-08-16", "Nilai CD4": 180, "Keterangan": "Evaluasi Terapi ARV"}
    ])
    buf = io.BytesIO()
    sample_df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Template_Hasil_CD4_SIMRS.xlsx"}
    )


# ============================================================================
# PWA PATIENT MOBILE API ENDPOINTS
# ============================================================================

@app.post("/api/pwa/auth/activate")
def pwa_activate_patient(payload: PwaActivationRequest, db: Session = Depends(get_db)):
    res = activate_patient_pwa(
        db,
        no_rekam_medik=payload.no_rekam_medik,
        tanggal_lahir=payload.tanggal_lahir,
        pin=payload.pin,
        is_biometric=payload.is_biometric
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res

@app.get("/api/pwa/health/summary")
def pwa_get_health_summary(
    no_rekam_medik: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    rm = no_rekam_medik
    if token and not rm:
        rm = verify_patient_session(db, token)
    if not rm:
        raise HTTPException(status_code=401, detail="Sesi tidak valid atau No. RM tidak disertakan.")
    
    return get_patient_health_summary(db, rm)

@app.post("/api/pwa/adherence/log")
def pwa_log_adherence(payload: PwaAdherenceLogRequest, db: Session = Depends(get_db)):
    return log_patient_adherence(
        db,
        no_rekam_medik=payload.no_rekam_medik,
        target_date=payload.target_date,
        log_type=payload.log_type or "ON_TIME",
        side_effects=payload.side_effects
    )

@app.get("/api/pwa/surveys")
def pwa_get_surveys(no_rekam_medik: str = Query(...), db: Session = Depends(get_db)):
    return get_surveys_for_patient(db, no_rekam_medik)

@app.post("/api/pwa/surveys/submit")
def pwa_submit_survey(payload: PwaSurveySubmitRequest, db: Session = Depends(get_db)):
    res = submit_patient_survey(
        db,
        no_rekam_medik=payload.no_rekam_medik,
        survey_id=payload.survey_id,
        answers=payload.answers,
        payment_channel=payload.payment_channel,
        payment_account_no=payload.payment_account_no,
        payment_account_name=payload.payment_account_name,
        device_hash=payload.device_hash
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res

@app.get("/api/pwa/feed")
def pwa_get_feed(db: Session = Depends(get_db)):
    return get_articles_and_banners(db)


# ============================================================================
# HOSPITAL ADMIN TAB 5 API ENDPOINTS
# ============================================================================

@app.get("/api/admin/pwa/overview")
def admin_get_pwa_overview(db: Session = Depends(get_db)):
    return get_admin_pwa_overview(db)

@app.get("/api/admin/pwa/pre-ltfu")
def admin_get_pre_ltfu_radar(filter_rujukan: str = Query("all"), db: Session = Depends(get_db)):
    return get_admin_pre_ltfu_radar(db, filter_rujukan=filter_rujukan)

@app.get("/api/admin/pwa/surveys")
def admin_get_surveys(survey_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    return get_admin_survey_responses(db, survey_id=survey_id)

@app.get("/api/admin/pwa/adherence-logs")
def admin_get_adherence_logs(
    target_date: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    return get_admin_adherence_logs_list(db, target_date=target_date, search=search)

@app.post("/api/admin/pwa/surveys/payout/verify")
def admin_verify_payout(payload: AdminPayoutVerifyRequest, db: Session = Depends(get_db)):
    res = verify_survey_payout(
        db,
        response_id=payload.response_id,
        amount_paid=payload.amount_paid,
        bank_reference_no=payload.bank_reference_no,
        admin_name=payload.admin_name,
        notes=payload.notes
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


# Route to serve PWA Mobile App directly
@app.get("/pwa", response_class=HTMLResponse)
def serve_pwa_page():
    pwa_file = os.path.join(FRONTEND_DIR, "pwa.html")
    if os.path.exists(pwa_file):
        with open(pwa_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>PWA App sedang disiapkan...</h1>"

