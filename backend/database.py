import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Date, DateTime, 
    Boolean, ForeignKey, Text, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DB_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(DB_DIR)
DEFAULT_SQLITE_PATH = os.path.join(BASE_DIR, "data_siha.db")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH}"

# Connect engine based on dialect
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    # Handle Supabase postgres:// -> postgresql:// alias
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(
        DATABASE_URL, 
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Pasien(Base):
    __tablename__ = "pasien"

    # Golden Primary Key: Pasien ID dari SIHA (tidak akan pernah diganti)
    pasien_id = Column(String(50), primary_key=True, index=True)
    
    # Identitas Medis & Kependudukan
    no_rekam_medik = Column(String(50), index=True, nullable=True)
    no_reg_nas = Column(String(50), index=True, nullable=True)
    nama_pasien = Column(String(150), nullable=True)
    nik = Column(String(50), nullable=True)
    status_nik = Column(String(50), nullable=True)
    
    # Demografi
    tanggal_lahir = Column(String(50), nullable=True)
    umur = Column(Integer, nullable=True)
    kategori_umur = Column(String(50), nullable=True)  # Anak, Remaja, Dewasa, Lansia
    jenis_kelamin = Column(String(30), index=True, nullable=True)  # Laki-laki / Perempuan
    pekerjaan = Column(String(100), nullable=True)
    suku = Column(String(50), nullable=True)
    warga_negara = Column(String(20), default="WNI")
    
    # Alamat KTP & Domisili
    alamat_provinsi = Column(String(100), nullable=True)
    alamat_kabupaten = Column(String(100), index=True, nullable=True)
    alamat_kecamatan = Column(String(100), nullable=True)
    alamat_kelurahan = Column(String(100), nullable=True)
    alamat = Column(Text, nullable=True)
    
    domisili_provinsi = Column(String(100), nullable=True)
    domisili_kabupaten = Column(String(100), index=True, nullable=True)
    domisili_kecamatan = Column(String(100), nullable=True)
    domisili_kelurahan = Column(String(100), nullable=True)
    alamat_domisili = Column(Text, nullable=True)
    
    # Registrasi & Rujukan
    tanggal_register = Column(String(50), nullable=True)
    kunjungan_terakhir = Column(String(50), nullable=True)
    asal_rujukan = Column(String(100), nullable=True)
    kelompok_populasi = Column(String(150), index=True, nullable=True)  # LSL, Waria, Pasangan Risti, dll.
    
    # Status Klinis Awal
    stadium_klinis_awal = Column(String(50), nullable=True)
    status_odhiv = Column(String(50), index=True, nullable=True)  # ODHIV, Bukan ODHIV, Belum Tahu
    status_odhiv_pdp = Column(String(100), index=True, nullable=True)  # Sedang pengobatan, Masuk perawatan, Gagal follow up, dll.
    
    tanggal_konfirmasi_hiv = Column(String(50), nullable=True)
    tanggal_masuk_perawatan = Column(String(50), nullable=True)
    tanggal_mulai_art = Column(String(50), nullable=True)
    tanggal_lost_to_follow_up = Column(String(50), nullable=True)
    
    # Rujukan Masuk / Keluar
    rujuk_masuk = Column(String(20), nullable=True)
    rujuk_masuk_dari_upk = Column(String(150), nullable=True)
    rujuk_keluar = Column(String(20), nullable=True)
    rujuk_keluar_ke_upk = Column(String(150), nullable=True)
    tanggal_rujuk_keluar = Column(String(50), nullable=True)
    tanggal_meninggal = Column(String(50), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    kunjungan_list = relationship("Kunjungan", back_populates="pasien", cascade="all, delete-orphan")
    viral_load_list = relationship("LabViralLoad", back_populates="pasien", cascade="all, delete-orphan")
    cd4_list = relationship("LabCD4", back_populates="pasien", cascade="all, delete-orphan")


class Kunjungan(Base):
    __tablename__ = "kunjungan"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pasien_id = Column(String(50), ForeignKey("pasien.pasien_id"), index=True, nullable=False)
    no_rekam_medik = Column(String(50), nullable=True)
    no_reg_nas = Column(String(50), nullable=True)
    
    tanggal_kunjungan = Column(String(50), index=True, nullable=False)
    nama_upk = Column(String(150), nullable=True)
    upk_asal = Column(String(150), nullable=True)
    alasan_kunjungan = Column(String(150), index=True, nullable=True)
    jenis_layanan = Column(String(100), nullable=True)
    
    # Antropometri & Gizi
    berat_badan = Column(Float, nullable=True)
    tinggi_badan = Column(Float, nullable=True)
    imt = Column(Float, nullable=True)
    kategori_imt = Column(String(50), index=True, nullable=True)  # Underweight, Normal, Overweight, Obesitas
    
    # Status Klinis Saat Kunjungan
    status_kawin = Column(String(50), nullable=True)
    status_hamil = Column(String(50), nullable=True)
    status_odhiv = Column(String(50), nullable=True)
    status_odhiv_pdp = Column(String(100), nullable=True)
    stadium_klinis = Column(String(50), index=True, nullable=True)
    
    # Terapi ARV
    nama_rejimen = Column(String(150), index=True, nullable=True)
    kategori_rejimen = Column(String(50), index=True, nullable=True)  # TLD, TLE, Second-Line / Alternatif, Lainnya
    jumlah_hari_arv = Column(Integer, nullable=True)
    
    # Jadwal Kontrol & Follow-up
    akhir_follow_up = Column(String(50), index=True, nullable=True)
    status_keterlambatan = Column(String(50), nullable=True)  # Tepat Waktu, Telat 1-7 Hari, Telat >7 Hari
    tanggal_dirujuk = Column(String(50), nullable=True)
    lembaga_pendamping = Column(String(150), nullable=True)
    
    batch_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    pasien = relationship("Pasien", back_populates="kunjungan_list")


class LabViralLoad(Base):
    __tablename__ = "lab_viral_load"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pasien_id = Column(String(50), ForeignKey("pasien.pasien_id"), index=True, nullable=False)
    no_order = Column(String(100), index=True, nullable=True)
    tanggal_pemeriksaan = Column(String(50), index=True, nullable=False)
    upk_asal = Column(String(150), nullable=True)
    
    hasil_raw = Column(String(100), nullable=True)
    hasil_numerik = Column(Float, nullable=True)
    kategori_vl = Column(String(100), index=True, nullable=True)
    # Kategori: Undetectable, Tersupresi (<200), Viremia Rendah (200-999), Gagal Virologis (>=1000), Error/Invalid, Pending
    is_suppressed = Column(Boolean, default=False, index=True)   # < 1000 copies/mL or undetectable
    is_undetectable = Column(Boolean, default=False, index=True) # Target not detected / < 40 copies/mL
    
    tanggal_hasil_keluar = Column(String(50), nullable=True)
    pemeriksa = Column(String(150), nullable=True)
    penanggung_jawab = Column(String(150), nullable=True)
    status_pemeriksaan = Column(String(50), nullable=True)  # Selesai, Draft, Sedang Proses
    diulang = Column(String(20), nullable=True)
    
    batch_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    pasien = relationship("Pasien", back_populates="viral_load_list")


class LabCD4(Base):
    __tablename__ = "lab_cd4"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pasien_id = Column(String(50), ForeignKey("pasien.pasien_id"), index=True, nullable=False)
    no_rekam_medik = Column(String(50), nullable=True)
    tanggal_pemeriksaan = Column(String(50), index=True, nullable=False)
    
    nilai_cd4 = Column(Float, nullable=False)  # cells/mm3
    kategori_cd4 = Column(String(100), index=True, nullable=True)
    # Kategori: Imunodefisiensi Berat (<200), Sedang (200-349), Ringan (350-499), Normal (>=500)
    persen_cd4 = Column(Float, nullable=True)
    keterangan = Column(String(255), nullable=True)
    
    batch_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    pasien = relationship("Pasien", back_populates="cd4_list")


class UploadHistory(Base):
    __tablename__ = "upload_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # PASIEN, KUNJUNGAN, VIRAL_LOAD, CD4, SIMRS_ARV
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    rows_processed = Column(Integer, default=0)
    rows_inserted = Column(Integer, default=0)
    rows_updated = Column(Integer, default=0)
    status = Column(String(50), default="SUCCESS")
    details = Column(Text, nullable=True)


class SimrsResep(Base):
    __tablename__ = "simrs_resep"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_number = Column(String(100), index=True, nullable=True)
    bill_date = Column(String(50), index=True, nullable=True)
    no_rekam_medik = Column(String(50), index=True, nullable=True)
    nama_pasien = Column(String(150), nullable=True)
    tanggal_lahir = Column(String(50), nullable=True)
    item_code = Column(String(50), nullable=True)
    item_code_desc = Column(String(255), index=True, nullable=True)
    qty = Column(Float, nullable=True)
    uom = Column(String(50), nullable=True)
    depo_name = Column(String(150), nullable=True)
    nama_dokter = Column(String(150), index=True, nullable=True)
    alamat = Column(Text, nullable=True)
    periode_sheet = Column(String(50), index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)



# ============================================================================
# PWA PASIEN & MODUL RISET TERISOLASI
# ============================================================================

class PatientDeviceSession(Base):
    __tablename__ = "patient_device_sessions"

    session_id = Column(String(50), primary_key=True)  # UUID
    no_rekam_medik = Column(String(50), index=True, nullable=False)
    device_token = Column(String(255), unique=True, index=True, nullable=False)
    pin_hash = Column(String(255), nullable=True)
    is_biometric_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_active = Column(DateTime, default=datetime.utcnow)


class PatientAdherenceLog(Base):
    __tablename__ = "patient_adherence_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    no_rekam_medik = Column(String(50), index=True, nullable=False)
    target_date = Column(String(20), index=True, nullable=False)  # YYYY-MM-DD
    logged_at = Column(DateTime, default=datetime.utcnow)
    log_type = Column(String(30), default="ON_TIME")  # ON_TIME, RETROACTIVE, DELAYED
    delay_minutes = Column(Integer, default=0)
    remaining_pills = Column(Integer, default=30)
    side_effects_reported = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PatientResearchSurvey(Base):
    __tablename__ = "patient_research_surveys"

    survey_id = Column(String(50), primary_key=True)  # e.g. SURV-2026-001
    judul_penelitian = Column(Text, nullable=False)
    no_etik_kepk = Column(String(100), nullable=True)
    nama_peneliti = Column(String(150), nullable=True)
    kriteria_inklusi = Column(Text, default="{}")  # JSON string
    reward_amount = Column(Integer, default=0)
    kuota_maksimal = Column(Integer, default=100)
    informed_consent_text = Column(Text, nullable=False)
    questions_schema = Column(Text, nullable=False)  # JSON string array of questions
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PatientSurveyResponse(Base):
    __tablename__ = "patient_survey_responses"

    response_id = Column(String(50), primary_key=True)  # UUID
    survey_id = Column(String(50), ForeignKey("patient_research_surveys.survey_id"), index=True, nullable=False)
    no_rekam_medik = Column(String(50), index=True, nullable=False)
    answers_json = Column(Text, nullable=False)  # JSON string of user answers
    consent_signed_at = Column(DateTime, default=datetime.utcnow)
    consent_device_hash = Column(String(255), nullable=True)
    payment_channel = Column(String(30), nullable=True)  # DANA, GOPAY, OVO, BCA, PULSA
    payment_account_no = Column(String(50), nullable=True)
    payment_account_name = Column(String(100), nullable=True)
    status_verifikasi = Column(String(30), default="PENDING")  # PENDING, APPROVED, REJECTED
    created_at = Column(DateTime, default=datetime.utcnow)


class PatientResearchPayout(Base):
    __tablename__ = "patient_research_payouts"

    payout_id = Column(String(50), primary_key=True)  # UUID / PAY-xxx
    response_id = Column(String(50), index=True, nullable=False)
    no_rekam_medik = Column(String(50), index=True, nullable=False)
    amount_paid = Column(Integer, nullable=False)
    bank_reference_no = Column(String(100), nullable=True)
    transferred_at = Column(DateTime, default=datetime.utcnow)
    verified_by_admin = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)


class PatientArticle(Base):
    __tablename__ = "patient_articles"

    article_id = Column(String(50), primary_key=True)
    title = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)  # Gizi & Nutrisi, Tips Kepatuhan, Efek Samping, Mental Health, U=U
    author_name = Column(String(100), default="Tim Medis RSUP Dr. Kariadi")
    thumbnail_url = Column(Text, nullable=True)
    content_markdown = Column(Text, nullable=False)
    read_time_minutes = Column(Integer, default=3)
    is_featured = Column(Boolean, default=False)
    published_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class AppNativeBanner(Base):
    __tablename__ = "app_native_banners"

    banner_id = Column(String(50), primary_key=True)
    title = Column(String(150), nullable=False)
    subtitle = Column(Text, nullable=True)
    badge_label = Column(String(50), default="INFO SEHAT")
    image_url = Column(Text, nullable=False)
    link_type = Column(String(30), default="INTERNAL_PAGE")  # INTERNAL_PAGE, EXTERNAL_URL, SURVEY_LINK, ARTICLE_LINK
    target_url = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


class PatientNotification(Base):
    __tablename__ = "patient_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    notification_id = Column(String(50), unique=True, index=True, nullable=False)  # e.g. NOTIF-20260901-XXXX
    target_type = Column(String(30), default="INDIVIDUAL")  # INDIVIDUAL, PRE_LTFU, ALL_PATIENTS, BROADCAST
    no_rekam_medik = Column(String(50), index=True, nullable=True)  # Specific RM or 'ALL'
    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    category = Column(String(50), default="INFO_MEDIS")  # REMINDER_OBAT, REMINDER_VL, EDUKASI, URGENT, BROADCAST
    priority = Column(String(20), default="NORMAL")  # LOW, NORMAL, HIGH, URGENT
    action_link = Column(String(100), nullable=True)  # e.g. "health", "pillbox", "articles", "surveys"
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), default="Konselor PDP RSUP Dr. Kariadi")
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)


def seed_initial_pwa_data(db):
    import json
    
    # 1. Seed Surveys if empty
    if db.query(PatientResearchSurvey).count() == 0:
        sample_survey = PatientResearchSurvey(
            survey_id="SURV-2026-001",
            judul_penelitian="Studi Evaluasi Kualitas Hidup & Tolerabilitas Pasien Terapi ARV Lini 1 (TLD)",
            no_etik_kepk="No. 142/EC/KEPK-RSDK/2026",
            nama_peneliti="Tim Peneliti Klinis PDP RSUP Dr. Kariadi",
            kriteria_inklusi=json.dumps({"rejimen": "TLD", "min_age": 18}),
            reward_amount=50000,
            kuota_maksimal=100,
            informed_consent_text="""LEMBAR PERSETUJUAN SETELAH PENJELASAN (INFORMED CONSENT)
Nomor Kaji Etik: No. 142/EC/KEPK-RSDK/2026 (Komite Etik Penelitian Kesehatan RSUP Dr. Kariadi)

1. Tujuan Penelitian: Mengevaluasi kualitas hidup, kepatuhan minum obat, dan tolerabilitas pasien yang menjalani terapi ARV berbasis Dolutegravir (TLD) di RSUP Dr. Kariadi.
2. Kesukarelaan: Keikutsertaan Anda bersifat 100% SUKARELA. Menolak atau menyetujui kuesioner ini TIDAK AKAN MEMPENGARUHI kualitas pelayanan medis Anda di RSUP Dr. Kariadi.
3. Kerahasiaan: Seluruh jawaban Anda dienkripsi dan dilindungi sesuai UU No. 27 Tahun 2022 tentang Perlindungan Data Pribadi (UU PDP).
4. Kompensasi Waktu: Sebagai apresiasi atas waktu yang Anda luangkan (sekitar 5 menit), Anda berhak menerima pengganti pulsa/uang kompensasi sebesar Rp 50.000 (Lima Puluh Ribu Rupiah) yang akan ditransfer manual oleh tim peneliti setelah jawaban divalidasi.""",
            questions_schema=json.dumps([
                {
                    "id": "q1",
                    "type": "scale_5",
                    "question": "Seberapa mudah Anda menyesuaikan jadwal minum obat ARV dengan rutinitas harian Anda?",
                    "options": ["1 - Sangat Sulit", "2 - Sulit", "3 - Cukup", "4 - Mudah", "5 - Sangat Mudah"]
                },
                {
                    "id": "q2",
                    "type": "single_choice",
                    "question": "Apakah Anda merasakan keluhan efek samping (misal: pusing, sulit tidur, atau mual) dalam 30 hari terakhir?",
                    "options": ["Tidak pernah sama sekali", "Kadang-kadang (ringan)", "Sering (mengganggu aktivitas)", "Sangat sering"]
                },
                {
                    "id": "q3",
                    "type": "scale_5",
                    "question": "Bagaimana penilaian Anda terhadap kebugaran fisik dan energi tubuh Anda setelah rutin minum obat?",
                    "options": ["1 - Sangat Lemah", "2 - Kurang Bugar", "3 - Cukup Baik", "4 - Bugar & Segar", "5 - Sangat Prima"]
                },
                {
                    "id": "q4",
                    "type": "text",
                    "question": "Apa saran atau harapan Anda untuk peningkatan layanan klinik PDP dan farmasi RSUP Dr. Kariadi?"
                }
            ]),
            is_active=True
        )
        db.add(sample_survey)
    
    # 2. Seed Articles if empty
    if db.query(PatientArticle).count() == 0:
        articles = [
            PatientArticle(
                article_id="ART-001",
                title="5 Makanan Alami Penunjang Daya Tahan Tubuh & Sel CD4",
                category="Gizi & Nutrisi",
                author_name="Instalasi Gizi Klinis RSUP Dr. Kariadi",
                thumbnail_url="https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=500&auto=format&fit=crop&q=60",
                content_markdown="""Nutrisi seimbang adalah kunci utama dalam mendukung efektivitas terapi ARV. Berikut 5 asupan bernutrisi tinggi yang dianjurkan:

1. **Telur & Ikan Segar:** Sumber protein tinggi untuk regenerasi sel imun tubuh.
2. **Kacang-kacangan & Tempe/Tahu:** Sumber zinc dan mikronutrien penting penunjang limfosit.
3. **Sayuran Hijau (Bayam, Brokoli):** Kaya asam folat dan antioksidan penangkal stres oksidatif.
4. **Buah Pepaya & Jeruk:** Sumber vitamin C alami yang ramah di lambung.
5. **Air Putih 2 Liter/Hari:** Menjaga ginjal tetap sehat dalam memetabolisme obat harian.""",
                read_time_minutes=3,
                is_featured=True
            ),
            PatientArticle(
                article_id="ART-002",
                title="Mengenal Konsep U=U: Mengapa Viral Load <50 Berarti Anda Aman",
                category="U=U & Edukasi",
                author_name="Tim Medis PDP RSUP Dr. Kariadi",
                thumbnail_url="https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=500&auto=format&fit=crop&q=60",
                content_markdown="""**U = U (Undetectable = Untransmittable)** adalah terobosan ilmiah global yang telah diakui oleh WHO dan Kemenkes RI.

* **Apa Artinya?** Ketika hasil tes laboratorium menunjukkan Viral Load Anda tersupresi hingga <50 kopi/mL (Tidak Terdeteksi), jumlah virus dalam darah dan cairan tubuh sangat sedikit sehingga **TIDAK BISA MENULARKAN** HIV ke pasangan seksual maupun anak.
* **Kuncinya:** Disiplin minum ARV setiap hari di jam yang konsisten.""",
                read_time_minutes=4,
                is_featured=True
            ),
            PatientArticle(
                article_id="ART-003",
                title="Tips Mengatasi Mual & Pusing Ringan di Awal Terapi ARV",
                category="Tips Kepatuhan",
                author_name="Apoteker Klinis RSUP Dr. Kariadi",
                thumbnail_url="https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=500&auto=format&fit=crop&q=60",
                content_markdown="""Tubuh membutuhkan waktu adaptasi selama 2–4 minggu pertama. Jika mengalami keluhan ringan:

1. **Minum Obat Bersama Makanan Ringan:** Hindari perut kosong saat menelan obat.
2. **Atur Jadwal Minum Sebelum Tidur:** Jika obat menimbulkan rasa kantuk atau pusing ringan, minumlah 30 menit sebelum jam tidur malam.
3. **Hindari Minuman Berkafein Tinggi:** Kurangi kopi atau minuman energi saat masa penyesuaian.""",
                read_time_minutes=3,
                is_featured=False
            )
        ]
        for a in articles:
            db.add(a)

    # 3. Seed Native Banners if empty
    if db.query(AppNativeBanner).count() == 0:
        banners = [
            AppNativeBanner(
                banner_id="BAN-001",
                title="Program Konseling Nutrisi & Imunitas Sehat",
                subtitle="Daftar sesi konsultasi gizi klinis gratis bersama dokter spesialis gizi RSUP Dr. Kariadi",
                badge_label="INFO RESMI RS",
                image_url="https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=800&auto=format&fit=crop&q=60",
                link_type="ARTICLE_LINK",
                target_url="ART-001",
                is_active=True,
                sort_order=1
            ),
            AppNativeBanner(
                banner_id="BAN-002",
                title="Ikuti Studi Kualitas Hidup & Dapatkan Imbalan Rp 50.000",
                subtitle="Kuesioner evaluasi terapi ARV terdaftar resmi di Komite Etik KEPK RSUP Dr. Kariadi",
                badge_label="RISET KEPK",
                image_url="https://images.unsplash.com/photo-1532938911079-1b06ac7ceec7?w=800&auto=format&fit=crop&q=60",
                link_type="SURVEY_LINK",
                target_url="SURV-2026-001",
                is_active=True,
                sort_order=2
            )
        ]
        for b in banners:
            db.add(b)

    # 4. Seed Initial Notifications if empty
    if db.query(PatientNotification).count() == 0:
        notifs = [
            PatientNotification(
                notification_id="NOTIF-INIT-001",
                target_type="ALL_PATIENTS",
                no_rekam_medik="ALL",
                title="Selamat Datang di SAPA Care Mobile",
                message="Pantau kepatuhan minum obat harian, cek hasil Viral Load & CD4, dan dapatkan edukasi klinis resmi dari tim PDP RSUP Dr. Kariadi.",
                category="EDUKASI",
                priority="NORMAL",
                action_link="health",
                created_by="Sistem SAPA Care",
                created_at=datetime.utcnow()
            ),
            PatientNotification(
                notification_id="NOTIF-INIT-002",
                target_type="ALL_PATIENTS",
                no_rekam_medik="ALL",
                title="Pemberitahuan Pelayanan Klinik PDP",
                message="Layanan pengambilan obat dan konsultasi dokter PDP RSUP Dr. Kariadi tetap buka setiap hari kerja (Senin - Jumat 08.00 - 15.00 WIB).",
                category="BROADCAST",
                priority="NORMAL",
                action_link="articles",
                created_by="Instalasi Pelayanan PDP",
                created_at=datetime.utcnow()
            )
        ]
        for n in notifs:
            db.add(n)

    db.commit()


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_initial_pwa_data(db)
    except Exception as e:
        db.rollback()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

