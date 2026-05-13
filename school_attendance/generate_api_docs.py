"""
generate_api_docs.py
Generates the School Face Attendance System API Reference PDF for the web team.

Run:
    python generate_api_docs.py
Output:
    School_Attendance_API_Reference.pdf
"""
from datetime import date as today_date

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, KeepTogether, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ─── Colour palette ───────────────────────────────────────────────────────────
C_BLUE      = HexColor('#2563eb')
C_DARK      = HexColor('#1e3a5f')
C_SLATE     = HexColor('#1e293b')
C_GRAY      = HexColor('#64748b')
C_LIGHT     = HexColor('#f8fafc')
C_BORDER    = HexColor('#e2e8f0')
C_CODE_BG   = HexColor('#f1f5f9')
C_CODE_LINE = HexColor('#cbd5e1')
C_GREEN     = HexColor('#059669')
C_AMBER     = HexColor('#d97706')
C_RED       = HexColor('#dc2626')
C_PURPLE    = HexColor('#7c3aed')
C_WHITE     = HexColor('#ffffff')
C_BLUE_SOFT = HexColor('#eff6ff')
C_BLUE_TEXT = HexColor('#bfdbfe')

METHOD_COLOR = {
    'GET':    C_GREEN,
    'POST':   C_AMBER,
    'DELETE': C_RED,
    'WS':     C_PURPLE,
}

PW, PH = A4
MARGIN = 2.0 * cm
INNER  = PW - 2 * MARGIN


# ─── Styles ───────────────────────────────────────────────────────────────────
def S():
    return {
        'cover_title': ParagraphStyle('ct', fontName='Helvetica-Bold', fontSize=30,
            textColor=C_WHITE, alignment=TA_CENTER, leading=36, spaceAfter=8),
        'cover_sub': ParagraphStyle('cs', fontName='Helvetica', fontSize=13,
            textColor=C_BLUE_TEXT, alignment=TA_CENTER, spaceAfter=4),
        'cover_meta': ParagraphStyle('cm', fontName='Helvetica', fontSize=10,
            textColor=C_BLUE_TEXT, alignment=TA_CENTER),

        'h1': ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=17,
            textColor=C_DARK, spaceBefore=16, spaceAfter=6),
        'h2': ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=13,
            textColor=C_DARK, spaceBefore=12, spaceAfter=4),
        'h3': ParagraphStyle('h3', fontName='Helvetica-Bold', fontSize=10,
            textColor=C_SLATE, spaceBefore=8, spaceAfter=3),

        'body': ParagraphStyle('body', fontName='Helvetica', fontSize=10,
            textColor=C_SLATE, leading=15, spaceAfter=6, alignment=TA_JUSTIFY),
        'body_l': ParagraphStyle('body_l', fontName='Helvetica', fontSize=10,
            textColor=C_SLATE, leading=15, spaceAfter=4),
        'bullet': ParagraphStyle('bullet', fontName='Helvetica', fontSize=10,
            textColor=C_SLATE, leading=15, spaceAfter=3, leftIndent=14),
        'note': ParagraphStyle('note', fontName='Helvetica-Oblique', fontSize=9,
            textColor=C_GRAY, leading=13, spaceAfter=4, leftIndent=8),
        'label': ParagraphStyle('label', fontName='Helvetica-Bold', fontSize=9,
            textColor=C_GRAY),
        'code': ParagraphStyle('code', fontName='Courier', fontSize=8.5,
            textColor=C_SLATE, leading=13),
        'tag': ParagraphStyle('tag', fontName='Helvetica-Bold', fontSize=9,
            textColor=C_WHITE, alignment=TA_CENTER),
        'caption': ParagraphStyle('caption', fontName='Helvetica', fontSize=9,
            textColor=C_GRAY, leading=12),
        'toc': ParagraphStyle('toc', fontName='Helvetica', fontSize=10,
            textColor=C_SLATE, leading=20),
        'toc_num': ParagraphStyle('toc_num', fontName='Helvetica-Bold', fontSize=10,
            textColor=C_BLUE, leading=20),
    }


# ─── Helper components ────────────────────────────────────────────────────────
def hr(color=C_BORDER, thick=0.5):
    return HRFlowable(width='100%', thickness=thick, color=color,
                      spaceAfter=6, spaceBefore=2)


def gap(h=6):
    return Spacer(1, h)


def method_pill(method, path, s):
    color = METHOD_COLOR.get(method, C_BLUE)
    t = Table([[
        Paragraph(method, s['tag']),
        Paragraph('<font name="Courier" size="10.5"><b>' + path + '</b></font>', s['body_l']),
    ]], colWidths=[1.5 * cm, INNER - 1.5 * cm], hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (0, 0), color),
        ('BACKGROUND',    (1, 0), (1, 0), C_BLUE_SOFT),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',         (0, 0), (0, 0),  'CENTER'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (1, 0), (1, 0), 10),
        ('LEFTPADDING',   (0, 0), (0, 0), 4),
        ('BOX',           (0, 0), (-1, -1), 0.5, color),
    ]))
    return t


def params_table(rows, s):
    hdr = [Paragraph('<b>' + h + '</b>', s['label'])
           for h in ('Parameter', 'Type', 'Required', 'Description')]
    data = [hdr]
    for name, typ, req, desc in rows:
        req_color = '#059669' if req == 'Yes' else '#94a3b8'
        data.append([
            Paragraph('<font name="Courier" size="9">' + name + '</font>', s['body_l']),
            Paragraph('<i>' + typ + '</i>', s['caption']),
            Paragraph('<font color="' + req_color + '"><b>' + req + '</b></font>', s['label']),
            Paragraph(desc, s['caption']),
        ])
    col_w = [3.4 * cm, 2.2 * cm, 1.9 * cm, INNER - 7.5 * cm]
    t = Table(data, colWidths=col_w)
    ts = [
        ('BACKGROUND',    (0, 0), (-1, 0),  C_LIGHT),
        ('LINEBELOW',     (0, 0), (-1, 0),  0.5, C_BORDER),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('BOX',           (0, 0), (-1, -1), 0.5, C_BORDER),
        ('LINEBELOW',     (0, 1), (-1, -1), 0.3, C_BORDER),
    ]
    for i in range(1, len(data)):
        bg = C_WHITE if i % 2 == 1 else C_LIGHT
        ts.append(('BACKGROUND', (0, i), (-1, i), bg))
    t.setStyle(TableStyle(ts))
    return t


def code_box(text, s):
    lines = text.strip().splitlines()
    def esc(l):
        return l.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    rows = [[Paragraph(esc(l) or ' ', s['code'])] for l in lines]
    inner = Table(rows, colWidths=[INNER - 1.4 * cm])
    inner.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))
    outer = Table([[inner]], colWidths=[INNER])
    outer.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_CODE_BG),
        ('BOX',           (0, 0), (-1, -1), 0.5, C_CODE_LINE),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    return outer


def info_box(text, s):
    t = Table([[Paragraph('i  ' + text, s['note'])]], colWidths=[INNER])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), HexColor('#eff6ff')),
        ('BOX',           (0, 0), (-1, -1), 0.5, C_BLUE),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


def section_title(text, s):
    return [gap(8), Paragraph(text, s['h1']), hr(C_BLUE, 1.2)]


def endpoint(method, path, description, params, req, resp, notes, s):
    items = [
        gap(6),
        method_pill(method, path, s),
        gap(5),
        Paragraph(description, s['body']),
    ]
    if params:
        items += [Paragraph('Parameters', s['h3']), params_table(params, s), gap(4)]
    if req:
        items += [Paragraph('Request Example', s['h3']), code_box(req, s), gap(4)]
    if resp:
        items += [Paragraph('Response', s['h3']), code_box(resp, s), gap(4)]
    for n in notes:
        items.append(info_box(n, s))
    items.append(hr())
    return KeepTogether(items)


# ─── Cover page ───────────────────────────────────────────────────────────────
def cover_page(s):
    # Blue header band
    band = Table(
        [[Paragraph('School Face Attendance System', s['cover_title'])],
         [Paragraph('API Reference for Web Integration Team', s['cover_sub'])],
         [gap(6)],
         [Paragraph('Version 3.0   |   ' + today_date.today().strftime('%B %Y'),
                    s['cover_meta'])]],
        colWidths=[INNER],
    )
    band.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_DARK),
        ('TOPPADDING',    (0, 0), (-1, -1), 28),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 28),
        ('LEFTPADDING',   (0, 0), (-1, -1), 20),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 20),
    ]))

    intro = Table([[Paragraph(
        'This document describes the REST and WebSocket APIs exposed by the '
        'School Face Attendance backend. It is intended for the website '
        'development team who will build the UI that consumes these endpoints. '
        'The backend runs on Python / FastAPI and stores data in PostgreSQL.',
        s['body'])]], colWidths=[INNER])
    intro.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_LIGHT),
        ('BOX',           (0, 0), (-1, -1), 0.5, C_BORDER),
        ('TOPPADDING',    (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING',   (0, 0), (-1, -1), 14),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 14),
    ]))

    # Quick-ref legend
    legend_rows = [
        [Paragraph('<b>Method</b>', s['label']), Paragraph('<b>Colour</b>', s['label'])],
        [Paragraph('GET',    s['body_l']), Paragraph('Green  - read data',   s['body_l'])],
        [Paragraph('POST',   s['body_l']), Paragraph('Amber  - send data',   s['body_l'])],
        [Paragraph('DELETE', s['body_l']), Paragraph('Red    - remove data', s['body_l'])],
        [Paragraph('WS',     s['body_l']), Paragraph('Purple - WebSocket',   s['body_l'])],
    ]
    legend = Table(legend_rows, colWidths=[3 * cm, INNER - 3 * cm])
    legend.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), C_LIGHT),
        ('LINEBELOW',     (0, 0), (-1, 0), 0.5, C_BORDER),
        ('BOX',           (0, 0), (-1, -1), 0.5, C_BORDER),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
    ]))

    return [
        band, gap(20), intro, gap(16),
        Paragraph('Method Legend', s['h2']), legend,
        PageBreak(),
    ]


# ─── System overview ──────────────────────────────────────────────────────────
def system_overview(s):
    items = section_title('1.  System Overview', s)
    items += [
        Paragraph('How it works end-to-end', s['h2']),
        Paragraph(
            'The School Face Attendance System is a Python / FastAPI backend that uses '
            'computer-vision AI to identify students from a live camera and automatically '
            'record their attendance in a PostgreSQL database. Your website integrates '
            'with it through the REST and WebSocket APIs documented in this file.', s['body']),
        gap(4),
        Paragraph('Step-by-step flow:', s['h3']),
        Paragraph('1.  Camera sends a live video frame to the server (via WebSocket or HTTP).', s['bullet']),
        Paragraph('2.  SCRFD 500M face detector locates every face in the frame.', s['bullet']),
        Paragraph('3.  MiniFASNet V2 liveness check rejects photos / screen replays.', s['bullet']),
        Paragraph('4.  ArcFace R50 converts the aligned face crop into a 512-number vector (embedding).', s['bullet']),
        Paragraph('5.  The embedding is compared against all stored student embeddings using cosine '
                  'similarity. The closest match above a confidence threshold is identified.', s['bullet']),
        Paragraph('6.  Attendance is written to the database (one record per student per day).', s['bullet']),
        Paragraph('7.  The website reads attendance and statistics through the Dashboard APIs.', s['bullet']),
        gap(10),
        Paragraph('Architecture', s['h2']),
    ]

    arch = Table([
        [Paragraph('Camera / Browser', s['body_l']),
         Paragraph('-->  WebSocket /ws/camera  OR  GET /api/camera/stream', s['code'])],
        [Paragraph('Edge device (IP cam)', s['body_l']),
         Paragraph('-->  POST /api/camera/process-frame', s['code'])],
        [Paragraph('Registration form', s['body_l']),
         Paragraph('-->  POST /api/register', s['code'])],
        [Paragraph('Attendance view', s['body_l']),
         Paragraph('-->  GET /api/attendance', s['code'])],
        [Paragraph('Dashboard / Stats', s['body_l']),
         Paragraph('-->  GET /api/stats', s['code'])],
    ], colWidths=[4.5 * cm, INNER - 4.5 * cm])
    arch.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_LIGHT),
        ('BOX',           (0, 0), (-1, -1), 0.5, C_BORDER),
        ('LINEBELOW',     (0, 0), (-1, -2), 0.3, C_BORDER),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    items += [arch, gap(8)]

    items += [
        Paragraph('Base URL', s['h2']),
        Paragraph('All HTTP endpoints are relative to:', s['body_l']),
        code_box('http://<server-host>:8000', s),
        gap(4),
        Paragraph('Authentication', s['h2']),
        Paragraph(
            'No authentication is required for this version. CORS is open (allow-all). '
            'If the system is exposed to the internet, place it behind a reverse proxy '
            '(nginx / Caddy) and add your own auth layer.', s['body']),
        PageBreak(),
    ]
    return items


# ─── Embedding technology ─────────────────────────────────────────────────────
def embedding_section(s):
    items = section_title('2.  Face Embedding Technology', s)
    items += [
        Paragraph('What is a face embedding?', s['h2']),
        Paragraph(
            'A face embedding is a compact numerical representation of a person\'s face. '
            'The AI model converts a face image into a list of 512 numbers (a vector). '
            'People who look similar produce vectors that are close together; different '
            'people produce vectors that are far apart. This is how the system tells '
            'students apart without storing any raw photos in the database.', s['body']),
        gap(6),
        Paragraph('Model used', s['h2']),
    ]

    model_rows = [
        [Paragraph('<b>Property</b>', s['label']), Paragraph('<b>Value</b>', s['label'])],
        [Paragraph('Model name',        s['body_l']), Paragraph('ArcFace R50  (InsightFace buffalo_l)', s['body_l'])],
        [Paragraph('Input',             s['body_l']), Paragraph('112 x 112 pixel aligned face crop (BGR)', s['body_l'])],
        [Paragraph('Output',            s['body_l']), Paragraph('512-dimensional float32 vector, L2-normalised', s['body_l'])],
        [Paragraph('Similarity metric', s['body_l']), Paragraph('Cosine similarity  (range -1.0 to 1.0; higher = more similar)', s['body_l'])],
        [Paragraph('Threshold',         s['body_l']), Paragraph('0.55  (configurable in .env via SIMILARITY_THRESHOLD)', s['body_l'])],
        [Paragraph('Memory per student',s['body_l']), Paragraph('512 x 4 bytes = 2 048 bytes (~2 KB)', s['body_l'])],
        [Paragraph('Liveness check',    s['body_l']), Paragraph('MiniFASNet V2 ONNX  (rejects printed photos / screen replays)', s['body_l'])],
    ]
    model_t = Table(model_rows, colWidths=[4.5 * cm, INNER - 4.5 * cm])
    model_t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), C_LIGHT),
        ('LINEBELOW',     (0, 0), (-1, 0), 0.5, C_BORDER),
        ('BOX',           (0, 0), (-1, -1), 0.5, C_BORDER),
        ('LINEBELOW',     (0, 1), (-1, -1), 0.3, C_BORDER),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    for i in range(1, len(model_rows)):
        bg = C_WHITE if i % 2 == 1 else C_LIGHT
        model_t.setStyle(TableStyle([('BACKGROUND', (0, i), (-1, i), bg)]))
    items += [model_t, gap(10)]

    items += [
        Paragraph('How embeddings are stored', s['h2']),
        Paragraph(
            'After registration the 512 float32 values are serialised to raw bytes '
            '(numpy tobytes()) and saved in the PostgreSQL embeddings table as a BYTEA '
            'column. Each student has exactly one row in that table containing their '
            'averaged embedding across all registration photos. No face images are '
            'stored in the database.', s['body']),
        code_box(
            '-- PostgreSQL embeddings table\n'
            'CREATE TABLE embeddings (\n'
            '    id           SERIAL PRIMARY KEY,\n'
            '    student_id   INT  NOT NULL REFERENCES students(id) UNIQUE,\n'
            '    created_at   TIMESTAMP DEFAULT NOW(),\n'
            '    sample_count INT  DEFAULT 0,   -- number of photos used\n'
            '    vector       BYTEA NOT NULL    -- 512 x float32 = 2048 bytes\n'
            ');', s),
        gap(10),
        Paragraph('How embeddings are retrieved for attendance verification', s['h2']),
        Paragraph(
            'When a face is detected during live recognition the following steps happen '
            'entirely in the backend -- the web team does not need to handle any of this:', s['body']),
        Paragraph('1.  All student embeddings are loaded from PostgreSQL into memory as numpy arrays.', s['bullet']),
        Paragraph('2.  The live face embedding is compared to every stored embedding using '
                  'cosine similarity:  score = stored_vector dot live_vector', s['bullet']),
        Paragraph('3.  The student with the highest score is selected. If that score is '
                  'below the threshold (0.55) the face is reported as Unknown.', s['bullet']),
        Paragraph('4.  If a match is found, one attendance record is written for today (duplicates '
                  'are silently ignored -- each student is marked once per day).', s['bullet']),
        gap(4),
        info_box(
            'Re-registration: submitting new photos for an existing student replaces their stored '
            'embedding (ON CONFLICT DO UPDATE). The old embedding is overwritten automatically.', s),
        PageBreak(),
    ]
    return items


# ─── API sections ─────────────────────────────────────────────────────────────
def camera_api(s):
    items = section_title('3.  Live Camera API', s)
    items.append(Paragraph(
        'Two ways to receive the live camera feed. Use whichever fits your frontend.', s['body']))
    items.append(gap(4))

    items.append(endpoint(
        'GET', '/api/camera/stream',
        'MJPEG live feed with face-detection bounding boxes and name labels drawn on each frame. '
        'The simplest integration: drop an &lt;img&gt; tag pointing at this URL and the browser '
        'streams the video automatically. This endpoint is view-only -- it does NOT mark attendance.',
        [],
        None,
        None,
        [
            'Content-Type: multipart/x-mixed-replace; boundary=frame',
            'Usage in HTML:  &lt;img src="http://server:8000/api/camera/stream"&gt;',
            'The stream runs until the client disconnects. Each JPEG frame has face boxes '
            'and confidence labels overlaid by the server.',
        ], s))

    items.append(endpoint(
        'WS', '/ws/camera',
        'WebSocket live feed. The server pushes two types of messages:\n'
        '  Binary frames  -- raw JPEG bytes to display as video.\n'
        '  Text frames    -- JSON attendance events when a known student is recognised.\n'
        'Attendance IS marked automatically through this endpoint (once per student per 30 seconds).',
        [],
        None,
        '// Binary message: render as video frame\n'
        'blob -> ImageBitmap or <canvas> draw\n\n'
        '// Text message: attendance event (JSON)\n'
        '{\n'
        '  "type":       "attendance",\n'
        '  "name":       "Ali Abbas",\n'
        '  "status":     "marked",          // or "already_marked"\n'
        '  "confidence": 0.91\n'
        '}',
        [
            'Connect with:  new WebSocket("ws://server:8000/ws/camera")',
            'The server opens the webcam on its own machine. Suitable when the camera is '
            'physically connected to the server PC.',
            'Cooldown: the same student triggers at most one attendance event every 30 seconds.',
        ], s))

    items.append(endpoint(
        'POST', '/api/camera/process-frame',
        'Submit a single JPEG frame captured by an external camera (IP camera, Raspberry Pi, etc.). '
        'The server detects faces, identifies students, marks attendance, and returns the results. '
        'Intended for edge devices that poll on their own schedule.',
        [
            ('file',      'JPEG file (multipart)', 'Yes', 'The captured frame image.'),
            ('camera_id', 'string (form field)',   'No',  'Identifier for this camera, stored in the attendance record. Default: cam_01.'),
        ],
        'curl -X POST http://server:8000/api/camera/process-frame \\\n'
        '  -F "file=@frame.jpg" \\\n'
        '  -F "camera_id=entrance_cam"',
        '{\n'
        '  "faces_detected": 2,\n'
        '  "results": [\n'
        '    { "name": "Ali Abbas", "status": "marked",        "confidence": 0.91 },\n'
        '    { "name": "Unknown",   "status": "unknown",       "confidence": 0.21 }\n'
        '  ]\n'
        '}',
        [
            'status values:  "marked" (new record), "already_marked" (duplicate today), '
            '"unknown" (face not recognised), "db_missing" (FAISS match but no DB row).',
        ], s))
    items.append(PageBreak())
    return items


def registration_api(s):
    items = section_title('4.  Student Registration API', s)
    items.append(Paragraph(
        'Endpoints for registering students, listing them, and deactivating them. '
        'Registration collects face photos, computes the ArcFace embedding, and stores '
        'it in PostgreSQL.', s['body']))

    items.append(endpoint(
        'POST', '/api/register',
        'Register a new student. Upload at least 5 clear face photos. The server detects '
        'the face in each photo, computes a 512-dim embedding, averages all valid embeddings '
        'into one representative vector, and stores it. Duplicate roll numbers are rejected.',
        [
            ('name',        'string (form field)',    'Yes', 'Full name of the student.'),
            ('roll_number', 'string (form field)',    'Yes', 'Unique roll / student ID. Duplicate is rejected.'),
            ('class_name',  'string (form field)',    'Yes', 'Class or grade (e.g. "10A").'),
            ('section',     'string (form field)',    'No',  'Section label (e.g. "B"). Default: empty.'),
            ('photos',      'JPEG files (multipart)', 'Yes', 'One or more face photos. Minimum 5 valid face detections required across all photos.'),
        ],
        '// HTML form example\n'
        '<form enctype="multipart/form-data"\n'
        '      action="http://server:8000/api/register" method="POST">\n'
        '  <input name="name"        type="text">\n'
        '  <input name="roll_number" type="text">\n'
        '  <input name="class_name"  type="text">\n'
        '  <input name="section"     type="text">\n'
        '  <input name="photos"      type="file" multiple accept="image/*">\n'
        '  <button type="submit">Register</button>\n'
        '</form>',
        '// Success\n'
        '{ "success": true,  "student_id": 7, "samples_used": 8 }\n\n'
        '// Failure -- duplicate roll number\n'
        '{ "success": false, "error": "Roll number already registered" }\n\n'
        '// Failure -- too few valid face photos\n'
        '{ "success": false, "error": "Only 3 valid face samples found. Need at least 5." }',
        [
            'Upload at least 5-10 photos per student for best recognition accuracy.',
            'Photos should be well-lit, front-facing, with the face clearly visible.',
            'Re-submitting the same roll_number will be rejected. Deactivate the student '
            'first (DELETE endpoint below) then re-register to update their embedding.',
        ], s))

    items.append(endpoint(
        'GET', '/api/students',
        'Returns the list of all active (non-deactivated) students.',
        [('class_name', 'string (query)', 'No', 'Filter by class name. Omit to return all classes.')],
        None,
        '[\n'
        '  {\n'
        '    "id":            3,\n'
        '    "name":          "Ali Abbas",\n'
        '    "roll_number":   "2024-CS-031",\n'
        '    "class_name":    "10A",\n'
        '    "section":       "B",\n'
        '    "registered_at": "2026-05-13 09:15:22"\n'
        '  },\n'
        '  ...\n'
        ']',
        ['Deactivated students (soft-deleted) are excluded from this list.'], s))

    items.append(endpoint(
        'DELETE', '/api/students/{id}',
        'Soft-deletes a student by setting is_active = FALSE. The student\'s data and '
        'embedding remain in the database but they are excluded from recognition and '
        'all list endpoints. Returns 404 if the ID does not exist.',
        [('id', 'integer (path)', 'Yes', 'The numeric student ID from GET /api/students.')],
        'DELETE http://server:8000/api/students/3',
        '{ "success": true }\n\n'
        '// If not found:\n'
        '{ "detail": "Student not found" }   // HTTP 404',
        ['This is a soft delete. Data is preserved for historical attendance records.'], s))

    items.append(PageBreak())
    return items


def attendance_api(s):
    items = section_title('5.  Attendance / Validation API', s)
    items.append(Paragraph(
        'Endpoints for reading attendance records and exporting them. '
        'Attendance is written automatically by the Camera APIs -- '
        'these endpoints are for reading and reporting only.', s['body']))

    items.append(endpoint(
        'GET', '/api/attendance',
        'Returns attendance records. Filter by date and/or class. '
        'Results are ordered by most recent first.',
        [
            ('date_str',   'string YYYY-MM-DD (query)', 'No', 'Filter to a specific date. Omit for all dates.'),
            ('class_name', 'string (query)',             'No', 'Filter to a specific class. Omit for all classes.'),
        ],
        'GET /api/attendance?date_str=2026-05-13&class_name=10A',
        '[\n'
        '  {\n'
        '    "name":        "Ali Abbas",\n'
        '    "roll_number": "2024-CS-031",\n'
        '    "class_name":  "10A",\n'
        '    "section":     "B",\n'
        '    "date":        "2026-05-13",\n'
        '    "marked_at":   "2026-05-13 08:03:44",\n'
        '    "confidence":  0.91,\n'
        '    "camera_id":   "entrance_cam"\n'
        '  },\n'
        '  ...\n'
        ']',
        [
            'Each student appears at most once per date (enforced at DB level by UNIQUE(student_id, date)).',
            'confidence is the cosine similarity score (0.0 - 1.0) at the moment of identification.',
        ], s))

    items.append(endpoint(
        'GET', '/api/attendance/export',
        'Downloads attendance for a specific date as a CSV file. '
        'Useful for generating Excel reports or printing registers.',
        [('date_str', 'string YYYY-MM-DD (query)', 'Yes', 'The date to export.')],
        'GET /api/attendance/export?date_str=2026-05-13',
        '// Response: Content-Type: text/csv\n'
        '// Content-Disposition: attachment; filename=attendance_2026-05-13.csv\n\n'
        'name,roll_number,class_name,section,date,marked_at,confidence,camera_id\n'
        'Ali Abbas,2024-CS-031,10A,B,2026-05-13,2026-05-13 08:03:44,0.91,entrance_cam\n'
        '...',
        ['Columns match exactly those returned by GET /api/attendance.'], s))

    items.append(PageBreak())
    return items


def dashboard_api(s):
    items = section_title('6.  Dashboard / Statistics API', s)
    items.append(Paragraph(
        'High-level summary endpoints for building dashboards, charts, and reports.', s['body']))

    items.append(endpoint(
        'GET', '/api/stats',
        'Returns a summary of attendance for a given date (defaults to today). '
        'Includes total students, present, absent, attendance rate, and a per-class breakdown. '
        'Use this endpoint to power the main dashboard widgets.',
        [
            ('date_str',   'string YYYY-MM-DD (query)', 'No', 'Target date. Defaults to today.'),
            ('class_name', 'string (query)',             'No', 'Scope stats to one class. Omit for school-wide totals.'),
        ],
        'GET /api/stats\n'
        'GET /api/stats?date_str=2026-05-13\n'
        'GET /api/stats?class_name=10A',
        '{\n'
        '  "date":            "2026-05-13",\n'
        '  "total_students":  120,\n'
        '  "present":         98,\n'
        '  "absent":          22,\n'
        '  "attendance_rate": 81.7,          // percentage\n'
        '  "by_class": [\n'
        '    { "class_name": "10A", "total": 35, "present": 30 },\n'
        '    { "class_name": "10B", "total": 32, "present": 28 },\n'
        '    { "class_name": "11A", "total": 53, "present": 40 }\n'
        '  ]\n'
        '}',
        [
            'attendance_rate = (present / total_students) x 100, rounded to 1 decimal place.',
            'by_class lists every class that has at least one active student.',
            'absent = total_students - present (students with no attendance record for the date).',
        ], s))

    items.append(endpoint(
        'GET', '/api/status',
        'Health-check endpoint. Returns whether the pipeline is loaded and how many '
        'students have registered embeddings in the database. '
        'Call this on page load to confirm the backend is reachable.',
        [],
        None,
        '{\n'
        '  "status":          "running",\n'
        '  "mode":            "heavy",       // ArcFace R50\n'
        '  "liveness_enabled": true,\n'
        '  "students_in_db":  120\n'
        '}',
        ['If this returns an error, the backend server is down.'], s))

    items.append(PageBreak())
    return items


# ─── Quick reference table ────────────────────────────────────────────────────
def quick_ref(s):
    items = section_title('7.  Quick Reference', s)

    rows = [
        [Paragraph('<b>Method</b>', s['label']),
         Paragraph('<b>Endpoint</b>', s['label']),
         Paragraph('<b>Purpose</b>', s['label'])],
        ['GET',    '/api/status',                     'Health check and pipeline status'],
        ['GET',    '/api/camera/stream',               'MJPEG live feed (view only, no attendance)'],
        ['WS',     '/ws/camera',                       'WebSocket live feed + attendance marking'],
        ['POST',   '/api/camera/process-frame',        'Submit single JPEG frame from edge camera'],
        ['POST',   '/api/register',                    'Register student with face photos'],
        ['GET',    '/api/students',                    'List active students'],
        ['DELETE', '/api/students/{id}',               'Deactivate a student (soft delete)'],
        ['GET',    '/api/attendance',                  'List attendance records (filterable)'],
        ['GET',    '/api/attendance/export',           'Download attendance CSV'],
        ['GET',    '/api/stats',                       'Dashboard summary (present / absent / rate)'],
    ]

    col_w = [1.5 * cm, 6.5 * cm, INNER - 8 * cm]
    data = []
    for i, row in enumerate(rows):
        if i == 0:
            data.append(row)
        else:
            method, path, desc = row
            color = METHOD_COLOR.get(method, C_BLUE)
            data.append([
                Paragraph(method, ParagraphStyle('m', fontName='Helvetica-Bold',
                    fontSize=8, textColor=color, alignment=TA_CENTER)),
                Paragraph('<font name="Courier" size="9">' + path + '</font>', s['body_l']),
                Paragraph(desc, s['caption']),
            ])

    t = Table(data, colWidths=col_w)
    ts = [
        ('BACKGROUND',    (0, 0), (-1, 0),  C_LIGHT),
        ('LINEBELOW',     (0, 0), (-1, 0),  0.5, C_BORDER),
        ('BOX',           (0, 0), (-1, -1), 0.5, C_BORDER),
        ('LINEBELOW',     (0, 1), (-1, -1), 0.3, C_BORDER),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]
    for i in range(1, len(data)):
        bg = C_WHITE if i % 2 == 1 else C_LIGHT
        ts.append(('BACKGROUND', (0, i), (-1, i), bg))
    t.setStyle(TableStyle(ts))
    items += [t, gap(16)]

    items += [
        Paragraph('Notes for the development team', s['h2']),
        Paragraph('1.  CORS is open -- all origins are allowed. No preflight issues.', s['bullet']),
        Paragraph('2.  All timestamps are in server local time. Convert to your timezone if needed.', s['bullet']),
        Paragraph('3.  All POST bodies use multipart/form-data (not JSON). '
                  'File uploads require the photos field as an array of files.', s['bullet']),
        Paragraph('4.  The WebSocket binary frames are JPEG bytes. '
                  'Draw them to a <canvas> or use createObjectURL for display.', s['bullet']),
        Paragraph('5.  Swagger / interactive docs are available at:  http://server:8000/docs', s['bullet']),
    ]
    return items


# ─── Page numbering ────────────────────────────────────────────────────────────
def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(C_GRAY)
    # Footer line
    canvas.setStrokeColor(C_BORDER)
    canvas.setLineWidth(0.5)
    y_line = doc.bottomMargin - 6
    canvas.line(doc.leftMargin, y_line, PW - doc.rightMargin, y_line)
    # Page number
    canvas.drawRightString(PW - doc.rightMargin, y_line - 10,
                           f'Page {doc.page}')
    # Footer text
    canvas.drawString(doc.leftMargin, y_line - 10,
                      'School Face Attendance System  |  API Reference  |  Confidential')
    canvas.restoreState()


# ─── Main ─────────────────────────────────────────────────────────────────────
def build():
    out = 'School_Attendance_API_Reference.pdf'
    doc = SimpleDocTemplate(
        out, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN + 0.8 * cm,
    )
    s = S()
    story = []
    story += cover_page(s)
    story += system_overview(s)
    story += embedding_section(s)
    story += camera_api(s)
    story += registration_api(s)
    story += attendance_api(s)
    story += dashboard_api(s)
    story += quick_ref(s)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print('PDF generated: ' + out)


if __name__ == '__main__':
    build()
