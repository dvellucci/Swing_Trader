"""Presentation layer: Tk widgets and UI-thread event handling only."""
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from .analysis import find_new_report, normalize_ticker, parse_verdict, verdict_color_key
from .config import (APP_NAME, COLORS, MESSAGES, MIN_WINDOW_SIZE,
                     POLL_INTERVAL_MS, WINDOW_SIZE)
from .runner import ScriptRunner
from .strategy_registry import BY_LABEL, BY_ID, STRATEGIES as REGISTERED_STRATEGIES


class TradingApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_WINDOW_SIZE)
        self.bundled_script_available = any(s.script is not None and s.script.is_file() for s in REGISTERED_STRATEGIES)
        self.ticker = tk.StringVar()
        self.strategy = tk.StringVar(value=next((s.display_name for s in REGISTERED_STRATEGIES if s.script is not None), ""))
        self.status = tk.StringVar(value='Ready' if self.bundled_script_available else 'Bundled screener missing')
        self.events = Queue()
        self.runner = ScriptRunner(self.events)
        self.last_report: Path | None = None
        self._build_ui()
        self.after(POLL_INTERVAL_MS, self._poll_events)
        self.protocol('WM_DELETE_WINDOW', self._close)

    def _label(self, parent, text, **kwargs):
        return ctk.CTkLabel(parent, text=text, **kwargs)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=24, pady=(20, 10))
        self._label(header, APP_NAME, font=ctk.CTkFont(size=26, weight='bold')).pack(anchor='w')
        self._label(header, 'Run your Python strategies from one desktop dashboard', text_color='gray70').pack(anchor='w')

        controls = ctk.CTkFrame(self, corner_radius=12)
        controls.grid(row=1, column=0, sticky='ew', padx=24, pady=10)
        for column, weight in enumerate((2, 2, 1)):
            controls.grid_columnconfigure(column, weight=weight)
        for column, text, padx in ((0, 'Ticker', (18, 8)), (1, 'Strategy', 8)):
            self._label(controls, text).grid(row=0, column=column, sticky='w', padx=padx, pady=(15, 3))
        ctk.CTkEntry(controls, textvariable=self.ticker, placeholder_text='e.g. NVDA, DOL.TO').grid(row=1, column=0, sticky='ew', padx=(18, 8), pady=(0, 12))
        ctk.CTkOptionMenu(controls, variable=self.strategy, values=[strategy.display_name for strategy in REGISTERED_STRATEGIES]).grid(row=1, column=1, sticky='ew', padx=8, pady=(0, 12))
        self.run_button = ctk.CTkButton(controls, text='Run Analysis', command=self._start)
        self.run_button.grid(row=1, column=2, sticky='ew', padx=(8, 18), pady=(0, 12))
        self._label(controls, 'Darvas Strategy is bundled with this application', text_color='gray70').grid(row=2, column=0, columnspan=3, sticky='w', padx=18, pady=(0, 14))

        results = ctk.CTkFrame(self, corner_radius=12)
        results.grid(row=2, column=0, sticky='nsew', padx=24, pady=(0, 12))
        results.grid_columnconfigure(0, weight=1)
        results.grid_rowconfigure(2, weight=1)
        result_header = ctk.CTkFrame(results, fg_color='transparent')
        result_header.grid(row=0, column=0, sticky='ew', padx=16, pady=(14, 4))
        self._label(result_header, 'Analysis Results', font=ctk.CTkFont(size=18, weight='bold')).pack(side='left')
        self.verdict = self._label(result_header, 'NOT RUN', corner_radius=8, fg_color=COLORS['neutral'], width=125, height=28)
        self.verdict.pack(side='right')
        self.progress = ctk.CTkProgressBar(results, mode='indeterminate')
        self.progress.grid(row=1, column=0, sticky='ew', padx=16, pady=(6, 8))
        self.progress.set(0)
        self.output = ctk.CTkTextbox(results, font=ctk.CTkFont(family='Consolas', size=12), wrap='word')
        self.output.grid(row=2, column=0, sticky='nsew', padx=16, pady=(0, 12))
        self._append(MESSAGES['intro'] if self.bundled_script_available else MESSAGES['missing_script'])
        footer = ctk.CTkFrame(results, fg_color='transparent')
        footer.grid(row=3, column=0, sticky='ew', padx=16, pady=(0, 14))
        self._label(footer, '', textvariable=self.status, text_color='gray70').pack(side='left')
        self.report_button = ctk.CTkButton(footer, text='Open Report', command=self._open_report, state='disabled', width=120)
        self.report_button.pack(side='right')
        ctk.CTkButton(footer, text='Clear', command=self._clear, width=80, fg_color=COLORS['neutral']).pack(side='right', padx=(0, 8))

    def _clear(self):
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.configure(state='disabled')
        self.verdict.configure(text='NOT RUN', fg_color=COLORS['neutral'])

    def _append(self, text):
        self.output.configure(state='normal')
        self.output.insert('end', text)
        self.output.see('end')
        self.output.configure(state='disabled')

    def _start(self):
        selected = BY_LABEL.get(self.strategy.get())
        if selected is None:
            messagebox.showerror("Unknown strategy", "Please select a registered strategy.")
            return
        if selected.script is None:
            messagebox.showinfo('Coming soon', 'This strategy has not been implemented yet.')
            return
        try:
            ticker = normalize_ticker(self.ticker.get())
        except ValueError:
            messagebox.showerror('Invalid ticker', MESSAGES['invalid_ticker'])
            return
        script = selected.script
        if not script.is_file() or script.suffix.lower() != '.py':
            messagebox.showerror('Script not found', MESSAGES['not_found'])
            return
        self._clear()
        self.last_report = None
        self.report_button.configure(state='disabled')
        self.run_button.configure(state='disabled')
        self.status.set(f'Running {ticker}...')
        self.progress.start()
        try:
            self.runner.start(script.resolve(), ticker)
        except RuntimeError as exc:
            self._finish()
            messagebox.showerror('Cannot run', str(exc))

    def _finish(self):
        self.progress.stop()
        self.progress.set(0)
        self.run_button.configure(state='normal')

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event.kind == 'line':
                    self._append(event.data)
                    verdict = parse_verdict(event.data)
                    if verdict:
                        self._set_verdict(verdict)
                elif event.kind == 'done':
                    self._on_done(event.data)
                elif event.kind == 'error':
                    self._finish()
                    self.status.set('Error')
                    self._append(f'\nERROR: {event.data}\n')
        except Empty:
            pass
        self.after(POLL_INTERVAL_MS, self._poll_events)

    def _set_verdict(self, verdict):
        self.verdict.configure(text=verdict[:42], width=190, fg_color=COLORS[verdict_color_key(verdict)])

    def _on_done(self, result):
        self._finish()
        self.status.set('Completed' if result.code == 0 else f'Failed (exit code {result.code})')
        report = result.report_path if result.report_path and result.report_path.is_file() else find_new_report(result.script, result.ticker, result.started_at)
        if not report:
            self._append(MESSAGES['no_report'])
            return
        self.last_report = report
        self.report_button.configure(state='normal')
        self._append(f'\nReport found: {report}\n')
        try:
            report_text = report.read_text(encoding='utf-8-sig', errors='replace')
            self._append('\n' + '=' * 25 + ' REPORT ' + '=' * 25 + '\n' + report_text + '\n')
            verdict = parse_verdict(report_text)
            if verdict:
                self._set_verdict(verdict)
        except OSError as exc:
            self._append(f'Could not read report: {exc}\n')

    def _open_report(self):
        if not self.last_report or not self.last_report.exists():
            return
        try:
            if sys.platform == 'win32':
                os.startfile(str(self.last_report))
            else:
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(self.last_report)])
        except OSError as exc:
            messagebox.showerror('Cannot open report', str(exc))

    def _close(self):
        if self.runner.running:
            if not messagebox.askyesno('Analysis running', 'Close while analysis is running?'):
                return
            self.runner.stop()
        self.destroy()
