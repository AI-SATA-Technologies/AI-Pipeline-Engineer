CREATE DATABASE IF NOT EXISTS school_attendance;
USE school_attendance;

CREATE TABLE IF NOT EXISTS students (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    roll_number  VARCHAR(50) UNIQUE NOT NULL,
    class_name   VARCHAR(50),
    section      VARCHAR(10),
    photo_path   VARCHAR(255),
    registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active    BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS attendance (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    student_id   INT NOT NULL,
    date         DATE NOT NULL,
    marked_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    confidence   FLOAT,
    camera_id    VARCHAR(50),
    FOREIGN KEY (student_id) REFERENCES students(id),
    UNIQUE KEY unique_daily (student_id, date)
);

CREATE TABLE IF NOT EXISTS embeddings (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    student_id   INT NOT NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    sample_count INT DEFAULT 0,
    FOREIGN KEY (student_id) REFERENCES students(id)
);
