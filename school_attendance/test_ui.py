"""
Simple Python test UI for the School Attendance API.

Run:
    python test_ui.py

Requirements (already in requirements.txt):
    pip install requests

The API server must be running first:
    python main.py
"""
import json
import os
import sys
import threading
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    import requests
except ImportError:
    print("Install requests:  pip install requests")
    sys.exit(1)

BASE_URL = 'http://localhost:8000'


def api_get(path: str, params: dict | None = None) -> dict | list:
    try:
        r = requests.get(BASE_URL + path, params=params, timeout=10)
        return r.json()
    except Exception as e:
        return {'error': str(e)}


def api_post(path: str, data: dict | None = None, files=None) -> dict:
    try:
        r = requests.post(BASE_URL + path, data=data, files=files, timeout=20)
        return r.json()
    except Exception as e:
        return {'error': str(e)}


def api_delete(path: str) -> dict:
    try:
        r = requests.delete(BASE_URL + path, timeout=10)
        return r.json()
    except Exception as e:
        return {'error': str(e)}


# ─── Reusable output widget ────────────────────────────────────────────────────

class OutputBox(scrolledtext.ScrolledText):
    def __init__(self, parent, **kw):
        kw.setdefault('height', 10)
        kw.setdefault('state', 'disabled')
        kw.setdefault('font', ('Consolas', 9))
        super().__init__(parent, **kw)

    def show(self, data):
        text = json.dumps(data, indent=2, default=str)
        self.config(state='normal')
        self.delete('1.0', 'end')
        self.insert('end', text)
        self.config(state='disabled')


# ─── Tab: Status ──────────────────────────────────────────────────────────────

class StatusTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)
        ttk.Label(self, text='Check API health and pipeline status.').pack(anchor='w')
        ttk.Button(self, text='Check Status', command=self._check).pack(pady=8, anchor='w')
        self.out = OutputBox(self)
        self.out.pack(fill='both', expand=True)

    def _check(self):
        self.out.show(api_get('/api/status'))


# ─── Tab: Register ────────────────────────────────────────────────────────────

class RegisterTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)
        self._photos: list[str] = []

        form = ttk.LabelFrame(self, text='Student Details', padding=10)
        form.pack(fill='x')

        self._vars: dict[str, tk.StringVar] = {}
        for label, key in [('Name', 'name'), ('Roll Number', 'roll_number'),
                            ('Class', 'class_name'), ('Section', 'section')]:
            row = ttk.Frame(form)
            row.pack(fill='x', pady=3)
            ttk.Label(row, text=label + ':', width=14, anchor='w').pack(side='left')
            var = tk.StringVar()
            ttk.Entry(row, textvariable=var, width=30).pack(side='left')
            self._vars[key] = var

        photo_row = ttk.Frame(self)
        photo_row.pack(fill='x', pady=8)
        ttk.Button(photo_row, text='Select Photos (5+)', command=self._pick_photos).pack(side='left')
        self._photo_lbl = ttk.Label(photo_row, text='No photos selected', foreground='grey')
        self._photo_lbl.pack(side='left', padx=10)

        ttk.Button(self, text='Register Student', command=self._register).pack(anchor='w')

        self.out = OutputBox(self)
        self.out.pack(fill='both', expand=True, pady=(8, 0))

    def _pick_photos(self):
        paths = filedialog.askopenfilenames(
            title='Select face photos',
            filetypes=[('Images', '*.jpg *.jpeg *.png')],
        )
        self._photos = list(paths)
        n = len(self._photos)
        self._photo_lbl.config(
            text=f'{n} photo(s) selected',
            foreground='green' if n >= 5 else 'red',
        )

    def _register(self):
        if not self._photos:
            messagebox.showwarning('No Photos', 'Please select at least 5 photos.')
            return
        data = {k: v.get() for k, v in self._vars.items()}
        if not data['name'] or not data['roll_number'] or not data['class_name']:
            messagebox.showwarning('Missing Fields', 'Name, Roll Number, and Class are required.')
            return

        files = [('photos', (os.path.basename(p), open(p, 'rb'), 'image/jpeg'))
                 for p in self._photos]

        def run():
            result = api_post('/api/register', data=data, files=files)
            self.out.show(result)

        threading.Thread(target=run, daemon=True).start()
        self.out.show({'status': 'uploading…'})


# ─── Tab: Attendance ──────────────────────────────────────────────────────────

class AttendanceTab(ttk.Frame):
    COLS = ('name', 'roll_number', 'class_name', 'section', 'date', 'marked_at', 'confidence')

    def __init__(self, parent):
        super().__init__(parent, padding=12)

        bar = ttk.Frame(self)
        bar.pack(fill='x', pady=(0, 8))
        ttk.Label(bar, text='Date (YYYY-MM-DD):').pack(side='left')
        self._date = tk.StringVar(value=str(date.today()))
        ttk.Entry(bar, textvariable=self._date, width=13).pack(side='left', padx=4)
        ttk.Label(bar, text='Class:').pack(side='left', padx=(8, 0))
        self._class = tk.StringVar()
        ttk.Entry(bar, textvariable=self._class, width=10).pack(side='left', padx=4)
        ttk.Button(bar, text='Fetch', command=self._fetch).pack(side='left', padx=4)
        ttk.Button(bar, text='Export CSV', command=self._export).pack(side='left', padx=4)

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill='both', expand=True)
        self._tree = ttk.Treeview(tree_frame, columns=self.COLS, show='headings', height=18)
        col_widths = {'name': 130, 'roll_number': 100, 'class_name': 80,
                      'section': 60, 'date': 90, 'marked_at': 140, 'confidence': 80}
        for c in self.COLS:
            self._tree.heading(c, text=c.replace('_', ' ').title())
            self._tree.column(c, width=col_widths.get(c, 100))
        vsb = ttk.Scrollbar(tree_frame, orient='vertical', command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient='horizontal', command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self._count_lbl = ttk.Label(self, text='')
        self._count_lbl.pack(anchor='w', pady=(4, 0))

    def _fetch(self):
        params = {}
        if self._date.get(): params['date_str'] = self._date.get()
        if self._class.get(): params['class_name'] = self._class.get()
        rows = api_get('/api/attendance', params)
        for item in self._tree.get_children():
            self._tree.delete(item)
        if isinstance(rows, list):
            for r in rows:
                self._tree.insert('', 'end', values=[r.get(c, '') for c in self.COLS])
            self._count_lbl.config(text=f'{len(rows)} record(s) found')
        else:
            self._count_lbl.config(text=f'Error: {rows.get("error", "unknown")}')

    def _export(self):
        date_val = self._date.get()
        if not date_val:
            messagebox.showwarning('Date Required', 'Enter a date to export.')
            return
        try:
            r = requests.get(f'{BASE_URL}/api/attendance/export', params={'date_str': date_val})
            save_path = filedialog.asksaveasfilename(
                defaultextension='.csv',
                initialfile=f'attendance_{date_val}.csv',
                filetypes=[('CSV', '*.csv')],
            )
            if save_path:
                with open(save_path, 'wb') as f:
                    f.write(r.content)
                messagebox.showinfo('Exported', f'Saved to {save_path}')
        except Exception as e:
            messagebox.showerror('Export Error', str(e))


# ─── Tab: Statistics ──────────────────────────────────────────────────────────

class StatsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)

        bar = ttk.Frame(self)
        bar.pack(fill='x', pady=(0, 8))
        ttk.Label(bar, text='Date (YYYY-MM-DD):').pack(side='left')
        self._date = tk.StringVar(value=str(date.today()))
        ttk.Entry(bar, textvariable=self._date, width=13).pack(side='left', padx=4)
        ttk.Label(bar, text='Class:').pack(side='left', padx=(8, 0))
        self._class = tk.StringVar()
        ttk.Entry(bar, textvariable=self._class, width=10).pack(side='left', padx=4)
        ttk.Button(bar, text='Fetch Stats', command=self._fetch).pack(side='left', padx=4)

        summ = ttk.LabelFrame(self, text='Summary', padding=10)
        summ.pack(fill='x', pady=(0, 10))
        self._lbls: dict[str, ttk.Label] = {}
        grid_items = [
            ('total_students', 'Total Students'),
            ('present', 'Present'),
            ('absent', 'Absent'),
            ('attendance_rate', 'Attendance Rate (%)'),
        ]
        for i, (key, label) in enumerate(grid_items):
            col = i % 2 * 3
            ttk.Label(summ, text=label + ':', width=22, anchor='e').grid(row=i // 2, column=col, sticky='e', padx=4, pady=4)
            lbl = ttk.Label(summ, text='—', font=('', 11, 'bold'))
            lbl.grid(row=i // 2, column=col + 1, sticky='w', padx=4)
            self._lbls[key] = lbl

        ttk.Label(self, text='Breakdown by Class:').pack(anchor='w')
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill='both', expand=True, pady=(4, 0))
        cols = ('class_name', 'total', 'present', 'absent', 'rate')
        self._tree = ttk.Treeview(tree_frame, columns=cols, show='headings', height=10)
        headers = {'class_name': 'Class', 'total': 'Total', 'present': 'Present',
                   'absent': 'Absent', 'rate': 'Rate (%)'}
        for c in cols:
            self._tree.heading(c, text=headers[c])
            self._tree.column(c, width=110)
        vsb = ttk.Scrollbar(tree_frame, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

    def _fetch(self):
        params = {}
        if self._date.get(): params['date_str'] = self._date.get()
        if self._class.get(): params['class_name'] = self._class.get()
        data = api_get('/api/stats', params)
        if 'error' in data:
            messagebox.showerror('API Error', data['error'])
            return
        for key, lbl in self._lbls.items():
            val = data.get(key, '—')
            lbl.config(text=str(val))
        for item in self._tree.get_children():
            self._tree.delete(item)
        for row in data.get('by_class', []):
            total = row.get('total', 0)
            present = row.get('present', 0)
            absent = total - present
            rate = round(present / total * 100, 1) if total else 0.0
            self._tree.insert('', 'end', values=(
                row.get('class_name', ''), total, present, absent, rate
            ))


# ─── Tab: Students ────────────────────────────────────────────────────────────

class StudentsTab(ttk.Frame):
    COLS = ('id', 'name', 'roll_number', 'class_name', 'section', 'registered_at')

    def __init__(self, parent):
        super().__init__(parent, padding=12)

        bar = ttk.Frame(self)
        bar.pack(fill='x', pady=(0, 8))
        ttk.Label(bar, text='Class filter:').pack(side='left')
        self._class = tk.StringVar()
        ttk.Entry(bar, textvariable=self._class, width=12).pack(side='left', padx=4)
        ttk.Button(bar, text='Fetch', command=self._fetch).pack(side='left', padx=4)
        ttk.Button(bar, text='Delete Selected', command=self._delete, style='Danger.TButton').pack(side='left', padx=4)

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill='both', expand=True)
        self._tree = ttk.Treeview(tree_frame, columns=self.COLS, show='headings', height=18)
        widths = {'id': 50, 'name': 140, 'roll_number': 100, 'class_name': 80,
                  'section': 60, 'registered_at': 160}
        for c in self.COLS:
            self._tree.heading(c, text=c.replace('_', ' ').title())
            self._tree.column(c, width=widths.get(c, 100))
        vsb = ttk.Scrollbar(tree_frame, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self._count_lbl = ttk.Label(self, text='')
        self._count_lbl.pack(anchor='w', pady=(4, 0))

    def _fetch(self):
        params = {}
        if self._class.get(): params['class_name'] = self._class.get()
        rows = api_get('/api/students', params)
        for item in self._tree.get_children():
            self._tree.delete(item)
        if isinstance(rows, list):
            for r in rows:
                self._tree.insert('', 'end', iid=str(r['id']),
                                  values=[r.get(c, '') for c in self.COLS])
            self._count_lbl.config(text=f'{len(rows)} student(s)')
        else:
            self._count_lbl.config(text=f'Error: {rows.get("error", "?")}')

    def _delete(self):
        selected = self._tree.selection()
        if not selected:
            messagebox.showinfo('Nothing Selected', 'Select a student row first.')
            return
        sid = selected[0]
        name = self._tree.item(sid, 'values')[1]
        if not messagebox.askyesno('Confirm', f'Deactivate student "{name}" (ID {sid})?'):
            return
        result = api_delete(f'/api/students/{sid}')
        if result.get('success'):
            self._tree.delete(sid)
            self._count_lbl.config(text='Student deactivated.')
        else:
            messagebox.showerror('Error', str(result))


# ─── Main window ──────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('School Attendance — API Test UI')
        self.geometry('900x640')
        self.minsize(700, 480)

        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=6, pady=6)
        nb.add(StatusTab(nb),     text='  Status  ')
        nb.add(RegisterTab(nb),   text='  Register  ')
        nb.add(AttendanceTab(nb), text='  Attendance  ')
        nb.add(StatsTab(nb),      text='  Statistics  ')
        nb.add(StudentsTab(nb),   text='  Students  ')

        status_bar = ttk.Label(self, text=f'API: {BASE_URL}', relief='sunken', anchor='w')
        status_bar.pack(side='bottom', fill='x')


if __name__ == '__main__':
    App().mainloop()
