-- PostgreSQL schema for School Face Attendance System
-- No extensions required — embeddings stored as BYTEA, searched in Python.
--
-- Run once:
--   psql -U postgres -f schema.sql

CREATE DATABASE school_attendance;
\c school_attendance;

-- LMS-integrated students: store only the registration number + embedding.
-- Source images are never persisted; only the 512-dim averaged float32 vector.
CREATE TABLE IF NOT EXISTS student_face_embeddings (
    registration_number VARCHAR(100) PRIMARY KEY,
    created_at          TIMESTAMP DEFAULT NOW(),
    sample_count        INT DEFAULT 0,
    vector              BYTEA NOT NULL
);
