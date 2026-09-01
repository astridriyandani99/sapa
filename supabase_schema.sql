-- ============================================================================
-- SKEMA LENGKAP DATABASE SUPABASE POSTGRESQL (SIHA & SIMRS ANALYTICS + PWA)
-- Salin dan jalankan skrip ini di: Supabase Dashboard -> SQL Editor -> Run
-- ============================================================================

-- 1. Tabel Master Pasien
CREATE TABLE IF NOT EXISTS pasien (
    pasien_id VARCHAR(50) PRIMARY KEY,
    no_rekam_medik VARCHAR(50),
    no_reg_nas VARCHAR(50),
    nama_pasien VARCHAR(150),
    nik VARCHAR(50),
    status_nik VARCHAR(50),
    tanggal_lahir VARCHAR(50),
    umur INTEGER,
    kategori_umur VARCHAR(50),
    jenis_kelamin VARCHAR(30),
    pekerjaan VARCHAR(100),
    suku VARCHAR(50),
    warga_negara VARCHAR(50),
    alamat_provinsi VARCHAR(100),
    alamat_kabupaten VARCHAR(100),
    alamat_kecamatan VARCHAR(100),
    alamat_kelurahan VARCHAR(100),
    alamat TEXT,
    domisili_provinsi VARCHAR(100),
    domisili_kabupaten VARCHAR(100),
    domisili_kecamatan VARCHAR(100),
    domisili_kelurahan VARCHAR(100),
    alamat_domisili TEXT,
    tanggal_register VARCHAR(50),
    kunjungan_terakhir VARCHAR(50),
    asal_rujukan VARCHAR(100),
    kelompok_populasi VARCHAR(150),
    stadium_klinis_awal VARCHAR(50),
    status_odhiv VARCHAR(50),
    status_odhiv_pdp VARCHAR(100),
    tanggal_konfirmasi_hiv VARCHAR(50),
    tanggal_masuk_perawatan VARCHAR(50),
    tanggal_mulai_art VARCHAR(50),
    tanggal_lost_to_follow_up VARCHAR(50),
    rujuk_masuk VARCHAR(20),
    rujuk_masuk_dari_upk VARCHAR(150),
    rujuk_keluar VARCHAR(20),
    rujuk_keluar_ke_upk VARCHAR(150),
    tanggal_rujuk_keluar VARCHAR(50),
    tanggal_meninggal VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pasien_rm ON pasien(no_rekam_medik);
CREATE INDEX IF NOT EXISTS idx_pasien_reg ON pasien(no_reg_nas);
CREATE INDEX IF NOT EXISTS idx_pasien_gender ON pasien(jenis_kelamin);
CREATE INDEX IF NOT EXISTS idx_pasien_status ON pasien(status_odhiv_pdp);
CREATE INDEX IF NOT EXISTS idx_pasien_populasi ON pasien(kelompok_populasi);

-- 2. Tabel Kunjungan Pasien
CREATE TABLE IF NOT EXISTS kunjungan (
    id SERIAL PRIMARY KEY,
    pasien_id VARCHAR(50) NOT NULL REFERENCES pasien(pasien_id) ON DELETE CASCADE,
    no_rekam_medik VARCHAR(50),
    tanggal_kunjungan VARCHAR(50) NOT NULL,
    alasan_kunjungan VARCHAR(100),
    berat_badan FLOAT,
    tinggi_badan FLOAT,
    imt FLOAT,
    status_imt VARCHAR(50),
    tekanan_darah VARCHAR(30),
    status_kehamilan VARCHAR(50),
    tgl_melahirkan VARCHAR(50),
    metode_kb VARCHAR(100),
    stadium_klinis VARCHAR(50),
    status_fungsional VARCHAR(50),
    nama_rejimen VARCHAR(150),
    kategori_rejimen VARCHAR(100),
    paduan_pengobatan VARCHAR(100),
    jumlah_hari_arv INTEGER,
    sisa_hari_arv INTEGER,
    kepatuhan_art VARCHAR(50),
    efek_samping_arv TEXT,
    tanggal_rencana_kunjungan VARCHAR(50),
    afu_otomatis VARCHAR(50),
    profilaksis_kotrimoksazol VARCHAR(100),
    profilaksis_tpt VARCHAR(100),
    skrining_tb VARCHAR(100),
    hasil_tb VARCHAR(100),
    infeksi_oportunistik TEXT,
    batch_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_kunjungan_tgl ON kunjungan(tanggal_kunjungan);
CREATE INDEX IF NOT EXISTS idx_kunjungan_rej ON kunjungan(nama_rejimen);
CREATE INDEX IF NOT EXISTS idx_kunjungan_alasan ON kunjungan(alasan_kunjungan);

-- 3. Tabel Laboratorium Viral Load
CREATE TABLE IF NOT EXISTS lab_viral_load (
    id SERIAL PRIMARY KEY,
    pasien_id VARCHAR(50) NOT NULL REFERENCES pasien(pasien_id) ON DELETE CASCADE,
    no_rekam_medik VARCHAR(50),
    tanggal_pemeriksaan VARCHAR(50) NOT NULL,
    upk_asal VARCHAR(150),
    no_order VARCHAR(100),
    hasil_raw VARCHAR(150),
    hasil_numerik FLOAT,
    kategori_vl VARCHAR(100),
    is_suppressed BOOLEAN DEFAULT FALSE,
    is_undetectable BOOLEAN DEFAULT FALSE,
    tanggal_hasil_keluar VARCHAR(50),
    pemeriksa VARCHAR(150),
    penanggung_jawab VARCHAR(150),
    status_pemeriksaan VARCHAR(50),
    diulang VARCHAR(20),
    batch_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vl_tgl ON lab_viral_load(tanggal_pemeriksaan);
CREATE INDEX IF NOT EXISTS idx_vl_kat ON lab_viral_load(kategori_vl);
CREATE INDEX IF NOT EXISTS idx_vl_supp ON lab_viral_load(is_suppressed);

-- 4. Tabel Laboratorium CD4
CREATE TABLE IF NOT EXISTS lab_cd4 (
    id SERIAL PRIMARY KEY,
    pasien_id VARCHAR(50) NOT NULL REFERENCES pasien(pasien_id) ON DELETE CASCADE,
    no_rekam_medik VARCHAR(50),
    tanggal_pemeriksaan VARCHAR(50) NOT NULL,
    nilai_cd4 FLOAT NOT NULL,
    kategori_cd4 VARCHAR(100),
    persen_cd4 FLOAT,
    keterangan VARCHAR(255),
    batch_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cd4_tgl ON lab_cd4(tanggal_pemeriksaan);
CREATE INDEX IF NOT EXISTS idx_cd4_kat ON lab_cd4(kategori_cd4);

-- 5. Tabel Resep Farmasi SIMRS
CREATE TABLE IF NOT EXISTS simrs_resep (
    id SERIAL PRIMARY KEY,
    bill_number VARCHAR(100),
    bill_date VARCHAR(50),
    no_rekam_medik VARCHAR(50),
    nama_pasien VARCHAR(150),
    tanggal_lahir VARCHAR(50),
    item_code VARCHAR(50),
    item_code_desc VARCHAR(255),
    qty FLOAT,
    uom VARCHAR(50),
    depo_name VARCHAR(150),
    nama_dokter VARCHAR(150),
    alamat TEXT,
    periode_sheet VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_simrs_rm ON simrs_resep(no_rekam_medik);
CREATE INDEX IF NOT EXISTS idx_simrs_date ON simrs_resep(bill_date);
CREATE INDEX IF NOT EXISTS idx_simrs_item ON simrs_resep(item_code_desc);
CREATE INDEX IF NOT EXISTS idx_simrs_doc ON simrs_resep(nama_dokter);

-- 6. Tabel Riwayat Upload Berkas
CREATE TABLE IF NOT EXISTS upload_history (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rows_processed INTEGER DEFAULT 0,
    rows_inserted INTEGER DEFAULT 0,
    rows_updated INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'SUCCESS',
    details TEXT
);

-- 7. Tabel Sesi Perangkat PWA Pasien
CREATE TABLE IF NOT EXISTS patient_device_sessions (
    session_id VARCHAR(100) PRIMARY KEY,
    no_rekam_medik VARCHAR(50) NOT NULL,
    device_token VARCHAR(255) NOT NULL,
    pin_hash VARCHAR(255),
    is_biometric_enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pwa_session_rm ON patient_device_sessions(no_rekam_medik);

-- 8. Tabel Log Kepatuhan Minum Obat Harian
CREATE TABLE IF NOT EXISTS patient_adherence_logs (
    log_id SERIAL PRIMARY KEY,
    no_rekam_medik VARCHAR(50) NOT NULL,
    target_date VARCHAR(30) NOT NULL,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    log_type VARCHAR(30) DEFAULT 'ON_TIME',
    delay_minutes INTEGER DEFAULT 0,
    remaining_pills INTEGER,
    side_effects_reported TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_adherence_rm_date ON patient_adherence_logs(no_rekam_medik, target_date);

-- 9. Tabel Katalog Kuesioner Riset Resmi KEPK
CREATE TABLE IF NOT EXISTS patient_research_surveys (
    survey_id VARCHAR(100) PRIMARY KEY,
    judul_penelitian VARCHAR(255) NOT NULL,
    no_etik_kepk VARCHAR(150),
    nama_peneliti VARCHAR(150),
    reward_amount INTEGER DEFAULT 50000,
    informed_consent_text TEXT NOT NULL,
    questions_schema TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    quota_limit INTEGER DEFAULT 200,
    quota_filled INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. Tabel Respon Kuesioner & Persetujuan Digital KEPK
CREATE TABLE IF NOT EXISTS patient_survey_responses (
    response_id VARCHAR(100) PRIMARY KEY,
    survey_id VARCHAR(100) NOT NULL REFERENCES patient_research_surveys(survey_id),
    no_rekam_medik VARCHAR(50) NOT NULL,
    answers_json TEXT NOT NULL,
    consent_signed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    consent_device_hash VARCHAR(255),
    payment_channel VARCHAR(50) NOT NULL,
    payment_account_no VARCHAR(100) NOT NULL,
    payment_account_name VARCHAR(150) NOT NULL,
    status_verifikasi VARCHAR(30) DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_survey_resp_rm ON patient_survey_responses(no_rekam_medik);
CREATE INDEX IF NOT EXISTS idx_survey_resp_stat ON patient_survey_responses(status_verifikasi);

-- 11. Tabel Audit Pembayaran Imbalan Manual Peneliti
CREATE TABLE IF NOT EXISTS patient_research_payouts (
    payout_id SERIAL PRIMARY KEY,
    response_id VARCHAR(100) NOT NULL REFERENCES patient_survey_responses(response_id),
    no_rekam_medik VARCHAR(50) NOT NULL,
    amount_paid INTEGER NOT NULL,
    bank_reference_no VARCHAR(150) NOT NULL,
    transferred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified_by_admin VARCHAR(150) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. Tabel Artikel Edukasi Gizi & Kepatuhan ARV
CREATE TABLE IF NOT EXISTS patient_articles (
    article_id VARCHAR(100) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    thumbnail_url VARCHAR(255),
    content_markdown TEXT NOT NULL,
    author_name VARCHAR(150) DEFAULT 'Tim Medis RSUP Dr. Kariadi',
    read_time_minutes INTEGER DEFAULT 3,
    is_featured BOOLEAN DEFAULT FALSE,
    published_at VARCHAR(50)
);

-- 13. Tabel Banner Native In-Feed
CREATE TABLE IF NOT EXISTS app_native_banners (
    banner_id VARCHAR(100) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    subtitle VARCHAR(255),
    badge_label VARCHAR(100) DEFAULT 'INFO RESMI',
    image_url VARCHAR(255),
    link_type VARCHAR(50) DEFAULT 'INTERNAL_PAGE',
    target_url VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 1
);

-- ============================================================================
-- SEED DATA AWAL: KUESIONER KEPK, ARTIKEL EDUKASI, DAN BANNER NATIVE
-- ============================================================================

INSERT INTO patient_research_surveys (survey_id, judul_penelitian, no_etik_kepk, nama_peneliti, reward_amount, informed_consent_text, questions_schema, is_active, quota_limit)
VALUES (
    'SURV-2026-001',
    'Studi Kualitas Hidup & Aksesibilitas Terapi ARV Pasien Rawat Jalan',
    'KEPK-RSDK/2026/08/0412',
    'Dr. dr. Muchlis, Sp.PD-KPTI / Tim Peneliti PDP RSUP Dr. Kariadi',
    50000,
    'Saya secara sukarela bersedia berpartisipasi dalam penelitian ini. Data saya dilindungi oleh Kode Etik Penelitian Kedokteran KEPK RSUP Dr. Kariadi dan UU Perlindungan Data Pribadi (UU PDP No. 27/2022). Jawaban saya semata-mata digunakan untuk evaluasi mutu layanan dan perbaikan akses obat.',
    '[{"id":"q1","question":"Seberapa mudah Anda mengakses layanan pengambilan obat ARV di RSUP Dr. Kariadi?","type":"scale_5","options":["1 - Sangat Sulit","2 - Sulit","3 - Cukup","4 - Mudah","5 - Sangat Mudah"]},{"id":"q2","question":"Apakah Anda pernah mengalami keterlambatan minum obat karena kehabisan stok di rumah?","type":"single_choice","options":["Tidak pernah sama sekali","Pernah 1-2 kali","Sering (lebih dari 3 kali)"]},{"id":"q3","question":"Bagaimana penilaian Anda terhadap kenyamanan dan privasi ruang tunggu Poli PDP?","type":"scale_5","options":["1 - Sangat Buruk","2 - Buruk","3 - Cukup","4 - Baik","5 - Sangat Prima"]},{"id":"q4","question":"Saran atau masukan Anda untuk peningkatan layanan kesehatan di RSUP Dr. Kariadi:","type":"text_area"}]',
    TRUE,
    200
) ON CONFLICT (survey_id) DO NOTHING;

INSERT INTO patient_articles (article_id, title, category, thumbnail_url, content_markdown, author_name, read_time_minutes, is_featured, published_at)
VALUES 
(
    'art-01',
    'Konsep U=U (Undetectable = Untransmittable): Menatap Masa Depan Sehat & Bebas Stigma',
    'KESEHATAN & U=U',
    'https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=600&auto=format&fit=crop&q=80',
    'Ketika hasil tes Viral Load Anda menunjukkan < 50 kopi/mL (Undetectable / Tidak Terdeteksi), virus dalam tubuh Anda tertidur pulas dan tidak dapat menularkan kepada pasangan maupun keluarga. Kuncinya adalah satu: Disiplin minum ARV tepat waktu setiap hari.',
    'Tim Medis PDP RSUP Dr. Kariadi',
    3,
    TRUE,
    '31 Agustus 2026'
),
(
    'art-02',
    'Panduan Nutrisi & Gizi Seimbang untuk Meningkatkan Kadar Sel CD4',
    'GIZI & NUTRISI',
    'https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=600&auto=format&fit=crop&q=80',
    'Kekebalan tubuh (CD4) dapat meningkat optimal jika didukung oleh konsumsi protein berkualitas (ikan, telur, tahu, tempe), sayuran berantioksidan tinggi, serta hidrasi air putih minimal 2 liter setiap hari. Hindari makanan mentah atau setengah matang.',
    'Instalasi Gizi RSUP Dr. Kariadi',
    4,
    FALSE,
    '30 Agustus 2026'
) ON CONFLICT (article_id) DO NOTHING;

INSERT INTO app_native_banners (banner_id, title, subtitle, badge_label, image_url, link_type, target_url, is_active, sort_order)
VALUES (
    'ban-01',
    'Ikuti Studi Kualitas Hidup Pasien & Dapatkan Imbalan Rp 50.000',
    'Kuesioner resmi terdaftar di Komite Etik KEPK RSUP Dr. Kariadi. Waktu pengisian 3 menit.',
    'RISET KEPK BERHADIAH',
    'https://images.unsplash.com/photo-1532938911079-1b06ac7ceec7?w=400&auto=format&fit=crop&q=60',
    'SURVEY_LINK',
    'SURV-2026-001',
    TRUE,
    1
) ON CONFLICT (banner_id) DO NOTHING;
