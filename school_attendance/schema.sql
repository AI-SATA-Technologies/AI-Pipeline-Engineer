-- LMS Face Attendance — Minimal Schema
-- Stores ONLY lms_student_id + face embedding. Nothing else.

CREATE DATABASE IF NOT EXISTS lms_attendance;
USE lms_attendance;

CREATE TABLE IF NOT EXISTS student_embeddings (
    lms_student_id  VARCHAR(100)  PRIMARY KEY,        -- Unique ID from LMS
    vector          LONGBLOB      NOT NULL,            -- 512-dim float32 ArcFace embedding (raw bytes)
    sample_count    INT           DEFAULT 0,           -- Number of images used to build embedding
    registered_at   TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);
