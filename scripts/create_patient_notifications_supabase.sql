-- ============================================================================
-- SQL DDL MIGRATION FOR SUPABASE POSTGRESQL: PATIENT NOTIFICATIONS
-- Tabel Notifikasi, Pesan Klinis, & Siaran Admin ke Pasien Mobile PWA
-- ============================================================================

CREATE TABLE IF NOT EXISTS patient_notifications (
    id SERIAL PRIMARY KEY,
    notification_id VARCHAR(50) UNIQUE NOT NULL,
    target_type VARCHAR(30) DEFAULT 'INDIVIDUAL', -- INDIVIDUAL, PRE_LTFU, ALL_PATIENTS, BROADCAST
    no_rekam_medik VARCHAR(50),
    title VARCHAR(150) NOT NULL,
    message TEXT NOT NULL,
    category VARCHAR(50) DEFAULT 'INFO_MEDIS',    -- REMINDER_OBAT, REMINDER_VL, EDUKASI, URGENT, BROADCAST
    priority VARCHAR(20) DEFAULT 'NORMAL',        -- LOW, NORMAL, HIGH, URGENT
    action_link VARCHAR(100) DEFAULT 'health',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    created_by VARCHAR(100) DEFAULT 'Konselor PDP RSUP Dr. Kariadi',
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP WITHOUT TIME ZONE
);

-- Indexing for high-performance mobile push & querying
CREATE INDEX IF NOT EXISTS idx_patient_notif_rm ON patient_notifications(no_rekam_medik);
CREATE INDEX IF NOT EXISTS idx_patient_notif_id ON patient_notifications(notification_id);
CREATE INDEX IF NOT EXISTS idx_patient_notif_created ON patient_notifications(created_at DESC);

-- Seed initial broadcast notifications if empty
INSERT INTO patient_notifications (notification_id, target_type, no_rekam_medik, title, message, category, priority, action_link, created_by)
SELECT 'NOTIF-INIT-001', 'ALL_PATIENTS', 'ALL', 'Selamat Datang di SAPA Care Mobile', 'Pantau kepatuhan minum obat harian, cek hasil Viral Load & CD4, dan dapatkan edukasi klinis resmi dari tim PDP RSUP Dr. Kariadi.', 'EDUKASI', 'NORMAL', 'health', 'Sistem SAPA Care'
WHERE NOT EXISTS (SELECT 1 FROM patient_notifications WHERE notification_id = 'NOTIF-INIT-001');

INSERT INTO patient_notifications (notification_id, target_type, no_rekam_medik, title, message, category, priority, action_link, created_by)
SELECT 'NOTIF-INIT-002', 'ALL_PATIENTS', 'ALL', 'Pemberitahuan Pelayanan Klinik PDP', 'Layanan pengambilan obat dan konsultasi dokter PDP RSUP Dr. Kariadi tetap buka setiap hari kerja (Senin - Jumat 08.00 - 15.00 WIB).', 'BROADCAST', 'NORMAL', 'articles', 'Instalasi Pelayanan PDP'
WHERE NOT EXISTS (SELECT 1 FROM patient_notifications WHERE notification_id = 'NOTIF-INIT-002');
