import os
import sys

# Pin the settings tests depend on BEFORE config is imported, so a developer's
# .env (camera URL, API key, LMS URL…) never leaks into test runs. python-dotenv
# does not override variables that are already set.
os.environ.update({
    'CAMERA_URL': '',
    'LMS_API_URL': '',
    'LMS_API_TOKEN': '',
    'API_KEY': '',
    'ALLOWED_ORIGINS': '',
    'ATTENDANCE_TZ': 'UTC',
    'MODE': 'heavy',
    'SIMILARITY_THRESHOLD': '0.40',
    'REQUIRED_UPLOAD': '15',
    'REQUIRED_VALID': '7',
    'REVEAL_DUPLICATE_MATCH': 'false',
})

# Make the application package importable (config, auth, pipeline, database)
# regardless of the directory pytest is invoked from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
