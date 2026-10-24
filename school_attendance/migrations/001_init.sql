-- Base table: one averaged 512-dim float32 face embedding per student.
-- Source images are never persisted. Idempotent; applied at startup.
CREATE TABLE IF NOT EXISTS student_face_embeddings (
    registration_number VARCHAR(100) PRIMARY KEY,
    created_at          TIMESTAMP DEFAULT NOW(),
    sample_count        INT DEFAULT 0,
    vector              BYTEA NOT NULL
);
