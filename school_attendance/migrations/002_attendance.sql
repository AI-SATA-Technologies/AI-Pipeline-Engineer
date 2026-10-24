-- v3.2: tag embeddings with the model that produced them, and record attendance.
-- Idempotent; applied at startup (AUTO_MIGRATE=true) or by hand with psql.

-- Embeddings from different recognition models are not comparable. Rows created
-- before this column existed came from the default heavy model (w600k_r50).
ALTER TABLE student_face_embeddings
    ADD COLUMN IF NOT EXISTS model VARCHAR(50) NOT NULL DEFAULT 'w600k_r50';

-- One row per student per attendance day. Doubles as the LMS outbox:
-- rows stay 'pending' until the LMS accepts them (retried with backoff).
-- No foreign key on purpose: history survives deletion of a student's face data.
CREATE TABLE IF NOT EXISTS attendance_events (
    id                  BIGSERIAL PRIMARY KEY,
    registration_number VARCHAR(100) NOT NULL,
    attendance_date     DATE         NOT NULL,
    detected_at         TIMESTAMPTZ  NOT NULL,
    source              VARCHAR(50)  NOT NULL,          -- 'api' or a CAMERA_ID
    score               REAL,
    lms_status          VARCHAR(10)  NOT NULL DEFAULT 'pending',  -- pending|sent|failed|skipped
    lms_attempts        INT          NOT NULL DEFAULT 0,
    lms_last_error      TEXT,
    next_attempt_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (registration_number, attendance_date)
);

CREATE INDEX IF NOT EXISTS attendance_events_pending
    ON attendance_events (next_attempt_at) WHERE lms_status = 'pending';
