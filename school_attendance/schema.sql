-- PostgreSQL schema for School Face Attendance System
-- No extensions required — embeddings stored as BYTEA, searched in Python.
--
-- Run once:
--   psql -U postgres -f schema.sql

CREATE DATABASE school_attendance;
\c school_attendance;

CREATE TABLE IF NOT EXISTS students (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    roll_number   VARCHAR(50) UNIQUE NOT NULL,
    class_name    VARCHAR(50),
    section       VARCHAR(10),
    registered_at TIMESTAMP DEFAULT NOW(),
    is_active     BOOLEAN DEFAULT TRUE
);

-- One averaged 512-dim float32 embedding per student stored as raw bytes.
-- UNIQUE(student_id) lets re-registration update the existing row cleanly.
CREATE TABLE IF NOT EXISTS embeddings (
    id           SERIAL PRIMARY KEY,
    student_id   INT NOT NULL REFERENCES students(id) UNIQUE,
    created_at   TIMESTAMP DEFAULT NOW(),
    sample_count INT DEFAULT 0,
    vector       BYTEA NOT NULL
);

-- LMS-integrated students: store only the LMS-issued unique ID + embedding.
-- No reference to the students table; student_id comes directly from the LMS.
CREATE TABLE IF NOT EXISTS lms_embeddings (
    lms_student_id VARCHAR(100) PRIMARY KEY,
    created_at     TIMESTAMP DEFAULT NOW(),
    sample_count   INT DEFAULT 0,
    vector         BYTEA NOT NULL
);
