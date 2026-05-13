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

CREATE TABLE IF NOT EXISTS attendance (
    id         SERIAL PRIMARY KEY,
    student_id INT NOT NULL REFERENCES students(id),
    date       DATE NOT NULL,
    marked_at  TIMESTAMP DEFAULT NOW(),
    confidence FLOAT,
    camera_id  VARCHAR(50),
    UNIQUE (student_id, date)
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
