"""Helper for scripts/setup.bat (run setup.bat, not this file).

Subcommands (each prints what it did and exits non-zero on failure):
    check-path  fail early if the project folder is too deep for Windows' path limit
    init-env    create .env from .env.example if missing, with a random API_KEY
    check-env   validate .env and warn about settings that still need filling in
    db          create the database if it doesn't exist and apply migrations
    smoke       load the face models once to prove the pipeline works
"""
import os
import secrets
import shutil
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)


# Deepest file inside the venv is ~130 characters below the project folder, and
# Windows limits paths to 260 unless long paths are enabled.
_MAX_APP_DIR_LEN = 120


def _long_paths_enabled() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\FileSystem')
        return winreg.QueryValueEx(key, 'LongPathsEnabled')[0] == 1
    except (ImportError, OSError):
        return os.name != 'nt'  # only Windows has the limit


def check_path() -> int:
    if len(APP_DIR) <= _MAX_APP_DIR_LEN or _long_paths_enabled():
        return 0
    print(f'  ERROR: the project folder path is {len(APP_DIR)} characters long:')
    print(f'    {APP_DIR}')
    print('  Windows limits file paths to 260 characters and some Python packages have')
    print('  deep folders, so installing would fail. Either:')
    print('    - move the project to a shorter folder, e.g.  C:\\Attendance  (recommended), or')
    print('    - enable long paths, in a terminal opened "as Administrator":')
    print('        reg add HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem '
          '/v LongPathsEnabled /t REG_DWORD /d 1 /f')
    print('  then run setup.bat again.')
    return 1


def init_env() -> int:
    if os.path.exists('.env'):
        print('  .env already exists - keeping your settings')
        return 0
    shutil.copyfile('.env.example', '.env')
    with open('.env', encoding='utf-8') as f:
        lines = f.read().splitlines()
    key = secrets.token_urlsafe(32)
    lines = [f'API_KEY={key}' if line.strip() == 'API_KEY=' else line for line in lines]
    with open('.env', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('  created .env from .env.example')
    print('  generated a random API_KEY in .env - the LMS must send it in the X-API-Key header')
    return 0


def check_env() -> int:
    try:
        import config
    except SystemExit as exc:  # config validates .env and exits with the reason
        print(f'  .env is invalid:\n{exc}')
        return 1
    warnings = []
    if not config.DB_PASS:
        warnings.append('DB_PASS is empty (fine only if PostgreSQL needs no password)')
    if not config.API_KEYS:
        warnings.append('API_KEY is empty - the API will be open to anyone on the network')
    if not config.LMS_API_URL:
        warnings.append('LMS_API_URL is empty - attendance will be recorded but not sent to the LMS')
    if not config.settings.ATTENDANCE_TZ:
        warnings.append('ATTENDANCE_TZ is empty - the attendance day follows this PC\'s timezone')
    target = f'{config.DB_USER}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}'
    print(f'  mode={config.MODE}  database={target}')
    print(f'  camera={"configured" if config.CAMERA_URL else "none (frames come from clients)"}')
    for w in warnings:
        print(f'  note: {w}')
    print('  .env is valid')
    return 0


def db() -> int:
    import config
    import psycopg2
    from psycopg2 import sql

    try:
        conn = psycopg2.connect(
            host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER,
            password=config.DB_PASS, dbname='postgres', connect_timeout=5,
        )
    except psycopg2.Error as exc:
        print(f'  cannot connect to PostgreSQL at {config.DB_HOST}:{config.DB_PORT} '
              f'as {config.DB_USER!r}:\n    {str(exc).strip()}')
        print('  -> is PostgreSQL installed and running? are DB_USER / DB_PASS in .env correct?')
        return 1
    conn.autocommit = True  # CREATE DATABASE can't run inside a transaction
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', (config.DB_NAME,))
            if cur.fetchone():
                print(f'  database {config.DB_NAME!r} already exists')
            else:
                cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(config.DB_NAME)))
                print(f'  created database {config.DB_NAME!r}')
    except psycopg2.Error as exc:
        print(f'  could not create database {config.DB_NAME!r}: {str(exc).strip()}')
        print('  -> the DB_USER needs the CREATEDB privilege (the "postgres" user has it)')
        return 1
    finally:
        conn.close()

    import database
    try:
        applied = database.apply_migrations()
        with database.get_conn() as c, c.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM student_face_embeddings')
            students = cur.fetchone()[0]
    except database.StorageError as exc:
        print(f'  could not apply the schema: {exc}')
        return 1
    print(f'  tables up to date ({", ".join(applied)}); {students} student(s) registered')
    return 0


def smoke() -> int:
    import numpy as np

    from pipeline.engine import Pipeline
    try:
        pipeline = Pipeline()
    except FileNotFoundError as exc:
        print(f'  {exc}')
        return 1
    pipeline.embed_image(np.zeros((480, 640, 3), np.uint8))
    print(f'  face pipeline OK ({pipeline.model_name})')
    return 0


COMMANDS = {
    'check-path': check_path, 'init-env': init_env, 'check-env': check_env, 'db': db, 'smoke': smoke,
}

if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(f'usage: setup_helper.py {{{"|".join(COMMANDS)}}}')
        sys.exit(2)
    sys.exit(COMMANDS[sys.argv[1]]())
