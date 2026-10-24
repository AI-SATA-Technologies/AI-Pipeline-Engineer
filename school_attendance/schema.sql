-- PostgreSQL setup for School Face Attendance System
-- No extensions required — embeddings stored as BYTEA, searched in Python.
--
-- Run once to create the database:
--   psql -U postgres -f schema.sql
--
-- The tables themselves live in migrations/*.sql. The server applies them at
-- startup (AUTO_MIGRATE=true, the default). With AUTO_MIGRATE=false, apply them
-- by hand, in order:
--   psql -U postgres -d school_attendance -f migrations/001_init.sql
--   psql -U postgres -d school_attendance -f migrations/002_attendance.sql

CREATE DATABASE school_attendance;
\c school_attendance;

\ir migrations/001_init.sql
\ir migrations/002_attendance.sql
