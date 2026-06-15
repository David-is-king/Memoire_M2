-- Schema PostgreSQL minimal pour connecter le backend FastAPI au front Flutter.
-- A lancer dans ta base smartpredict :
-- psql -U postgres -d smartpredict -f Backend/schema.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Utilisateurs de l'application.
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'technician',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Moteurs surveilles par l'application.
CREATE TABLE IF NOT EXISTS motors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('healthy', 'warning', 'critical', 'offline')),
    health_score NUMERIC(5, 4) NOT NULL CHECK (health_score >= 0 AND health_score <= 1),
    failure_probability NUMERIC(5, 4) NOT NULL CHECK (failure_probability >= 0 AND failure_probability <= 1),
    estimated_rul_days INTEGER NOT NULL CHECK (estimated_rul_days >= 0),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Historique des capteurs.
CREATE TABLE IF NOT EXISTS sensor_readings (
    id BIGSERIAL PRIMARY KEY,
    motor_id TEXT NOT NULL REFERENCES motors(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    temperature NUMERIC(8, 3) NOT NULL,
    vibration_rms NUMERIC(8, 3) NOT NULL,
    current NUMERIC(8, 3) NOT NULL,
    voltage NUMERIC(8, 3) NOT NULL,
    acoustic_db NUMERIC(8, 3) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_motor_time
ON sensor_readings (motor_id, timestamp DESC);

-- Dernieres predictions ML par moteur.
CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,
    motor_id TEXT NOT NULL REFERENCES motors(id) ON DELETE CASCADE,
    predicted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    failure_probability NUMERIC(5, 4) NOT NULL CHECK (failure_probability >= 0 AND failure_probability <= 1),
    recommended_status TEXT NOT NULL CHECK (recommended_status IN ('healthy', 'warning', 'critical', 'offline')),
    maintenance_recommendation TEXT NOT NULL,
    anomaly_features TEXT[] NOT NULL DEFAULT '{}',
    estimated_rul_days INTEGER NOT NULL CHECK (estimated_rul_days >= 0)
);

CREATE INDEX IF NOT EXISTS idx_predictions_motor_time
ON predictions (motor_id, predicted_at DESC);

-- Alertes affichees dans le centre de notifications.
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    motor_id TEXT NOT NULL REFERENCES motors(id) ON DELETE CASCADE,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_read BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_alerts_created_at
ON alerts (created_at DESC);

-- Utilisateur de demo :
-- email    : admin@example.com
-- password : admin123
-- Change ce mot de passe des que possible dans un vrai environnement.
INSERT INTO users (email, password_hash, full_name, role)
VALUES ('admin@example.com', crypt('admin123', gen_salt('bf')), 'Administrateur Demo', 'admin')
ON CONFLICT (email) DO NOTHING;

-- Donnees de demo pour lancer rapidement le front.
INSERT INTO motors (id, name, location, status, health_score, failure_probability, estimated_rul_days, last_seen)
VALUES
    ('MTR-001', 'Moteur pompe principale', 'Atelier A', 'healthy', 0.9200, 0.0800, 180, NOW()),
    ('MTR-002', 'Moteur convoyeur nord', 'Ligne 2', 'warning', 0.6400, 0.4200, 58, NOW()),
    ('MTR-003', 'Moteur compresseur', 'Salle machines', 'critical', 0.3100, 0.8100, 12, NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO sensor_readings (motor_id, timestamp, temperature, vibration_rms, current, voltage, acoustic_db)
VALUES
    ('MTR-001', NOW() - INTERVAL '20 minutes', 58.2, 1.4, 11.8, 230.0, 62.0),
    ('MTR-001', NOW() - INTERVAL '10 minutes', 59.1, 1.5, 12.1, 229.8, 63.0),
    ('MTR-002', NOW() - INTERVAL '20 minutes', 76.4, 4.7, 15.2, 228.4, 78.0),
    ('MTR-002', NOW() - INTERVAL '10 minutes', 79.0, 5.1, 15.8, 227.9, 81.0),
    ('MTR-003', NOW() - INTERVAL '20 minutes', 92.8, 8.3, 22.2, 225.1, 91.0),
    ('MTR-003', NOW() - INTERVAL '10 minutes', 96.4, 8.9, 23.0, 224.7, 94.0);

INSERT INTO predictions (
    motor_id,
    predicted_at,
    failure_probability,
    recommended_status,
    maintenance_recommendation,
    anomaly_features,
    estimated_rul_days
)
VALUES
    ('MTR-001', NOW(), 0.0800, 'healthy', 'Fonctionnement normal. Continuer la surveillance standard.', ARRAY[]::TEXT[], 180),
    ('MTR-002', NOW(), 0.4200, 'warning', 'Planifier une inspection vibration et verifier l alignement du convoyeur.', ARRAY['vibration_rms', 'temperature'], 58),
    ('MTR-003', NOW(), 0.8100, 'critical', 'Intervention recommandee sous 24h. Risque eleve de defaillance thermique et mecanique.', ARRAY['temperature', 'vibration_rms', 'acoustic_db'], 12);

INSERT INTO alerts (motor_id, severity, title, message, created_at, is_read)
VALUES
    ('MTR-002', 'warning', 'Vibration elevee', 'Le convoyeur nord depasse le seuil de vibration conseille.', NOW() - INTERVAL '15 minutes', FALSE),
    ('MTR-003', 'critical', 'Risque de panne critique', 'Le compresseur presente une temperature et une vibration anormales.', NOW() - INTERVAL '5 minutes', FALSE);
