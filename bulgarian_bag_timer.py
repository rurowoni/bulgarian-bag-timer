#!/usr/bin/env python3
"""Bulgarian Bag interval timer — Pomodoro-style work/rest round timer for macOS."""

import math
import subprocess
import tkinter as tk
from tkinter import ttk

BG = "#1c1c1e"
PANEL = "#2c2c2e"
FG = "#f2f2f7"
MUTED = "#8e8e93"
WORK_COLOR = "#ff6b57"
REST_COLOR = "#4dabf7"
IDLE_COLOR = "#48484a"
DONE_COLOR = "#32d74b"
RING_TRACK = "#3a3a3c"

SOUND_TRANSITION = "/System/Library/Sounds/Glass.aiff"
SOUND_DONE = "/System/Library/Sounds/Hero.aiff"

CANVAS_SIZE = 300
RING_WIDTH = 14


def play_sound(path: str) -> None:
    try:
        subprocess.Popen(
            ["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        pass


def fmt_time(total_seconds: int) -> str:
    m, s = divmod(max(0, total_seconds), 60)
    return f"{m:02d}:{s:02d}"


class LabeledSpinbox(ttk.Frame):
    """A minutes:seconds pair of spinboxes with a caption."""

    def __init__(self, parent, caption, minutes=0, seconds=30):
        super().__init__(parent, style="Panel.TFrame")
        self.minutes_var = tk.IntVar(value=minutes)
        self.seconds_var = tk.IntVar(value=seconds)

        cap = tk.Label(
            self, text=caption, bg=PANEL, fg=MUTED, font=("Helvetica Neue", 12)
        )
        cap.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        self.min_box = tk.Spinbox(
            self,
            from_=0,
            to=59,
            width=3,
            textvariable=self.minutes_var,
            font=("Helvetica Neue", 16),
            justify="center",
            wrap=True,
            format="%02.0f",
            relief="flat",
        )
        self.min_box.grid(row=1, column=0)

        colon = tk.Label(self, text=":", bg=PANEL, fg=FG, font=("Helvetica Neue", 16))
        colon.grid(row=1, column=1, padx=4)

        self.sec_box = tk.Spinbox(
            self,
            from_=0,
            to=59,
            width=3,
            textvariable=self.seconds_var,
            font=("Helvetica Neue", 16),
            justify="center",
            wrap=True,
            format="%02.0f",
            relief="flat",
        )
        self.sec_box.grid(row=1, column=2)

    def total_seconds(self) -> int:
        return max(0, self.minutes_var.get()) * 60 + max(0, self.seconds_var.get())

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.min_box.configure(state=state)
        self.sec_box.configure(state=state)


class BulgarianBagTimer(tk.Tk):
    STATE_IDLE = "idle"
    STATE_WORK = "work"
    STATE_REST = "rest"
    STATE_DONE = "done"

    def __init__(self):
        super().__init__()
        self.title("Bulgarian Bag Timer")
        self.configure(bg=BG)
        self.resizable(False, False)

        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure("Panel.TFrame", background=PANEL)
        self.style.configure("Root.TFrame", background=BG)

        self.phase = self.STATE_IDLE
        self.current_round = 0
        self.remaining = 0
        self.phase_total = 0
        self.running = False
        self.timer_job = None

        self._build_ui()
        self._reset_all()

    # ---------- UI ----------

    def _build_ui(self):
        root = ttk.Frame(self, style="Root.TFrame", padding=24)
        root.pack(fill="both", expand=True)

        title = tk.Label(
            root,
            text="BULGARIAN BAG",
            bg=BG,
            fg=MUTED,
            font=("Helvetica Neue", 13, "bold"),
        )
        title.pack(pady=(0, 2))

        self.state_label = tk.Label(
            root, text="준비", bg=BG, fg=FG, font=("Helvetica Neue", 20, "bold")
        )
        self.state_label.pack(pady=(0, 16))

        self.canvas = tk.Canvas(
            root, width=CANVAS_SIZE, height=CANVAS_SIZE, bg=BG, highlightthickness=0
        )
        self.canvas.pack()

        self.round_dots_frame = tk.Frame(root, bg=BG)
        self.round_dots_frame.pack(pady=(14, 20))

        settings = ttk.Frame(root, style="Root.TFrame")
        settings.pack(pady=(0, 18))

        self.work_input = LabeledSpinbox(settings, "운동", minutes=0, seconds=30)
        self.work_input.grid(row=0, column=0, padx=8, ipadx=6, ipady=8)
        self._wrap_panel(self.work_input)

        self.rest_input = LabeledSpinbox(settings, "휴식", minutes=0, seconds=15)
        self.rest_input.grid(row=0, column=1, padx=8, ipadx=6, ipady=8)
        self._wrap_panel(self.rest_input)

        rounds_frame = ttk.Frame(settings, style="Panel.TFrame")
        rounds_frame.grid(row=0, column=2, padx=8, ipadx=6, ipady=8)
        cap = tk.Label(
            rounds_frame,
            text="라운드",
            bg=PANEL,
            fg=MUTED,
            font=("Helvetica Neue", 12),
        )
        cap.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.rounds_var = tk.IntVar(value=5)
        self.rounds_box = tk.Spinbox(
            rounds_frame,
            from_=1,
            to=99,
            width=3,
            textvariable=self.rounds_var,
            font=("Helvetica Neue", 16),
            justify="center",
            relief="flat",
        )
        self.rounds_box.grid(row=1, column=0)

        self.skip_last_rest_var = tk.BooleanVar(value=True)
        skip_check = tk.Checkbutton(
            root,
            text="마지막 휴식 생략",
            variable=self.skip_last_rest_var,
            bg=BG,
            fg=MUTED,
            selectcolor=PANEL,
            activebackground=BG,
            activeforeground=FG,
            font=("Helvetica Neue", 12),
            highlightthickness=0,
            bd=0,
        )
        skip_check.pack(pady=(0, 18))

        buttons = ttk.Frame(root, style="Root.TFrame")
        buttons.pack()

        self.start_btn = tk.Button(
            buttons,
            text="시작",
            command=self.toggle_start_pause,
            bg=WORK_COLOR,
            fg="white",
            activebackground="#ff8a78",
            activeforeground="white",
            font=("Helvetica Neue", 15, "bold"),
            relief="flat",
            width=10,
            height=2,
            bd=0,
            cursor="pointinghand",
        )
        self.start_btn.grid(row=0, column=0, padx=6)

        self.reset_btn = tk.Button(
            buttons,
            text="리셋",
            command=self._reset_all,
            bg=PANEL,
            fg=FG,
            activebackground="#3a3a3c",
            activeforeground=FG,
            font=("Helvetica Neue", 15),
            relief="flat",
            width=10,
            height=2,
            bd=0,
            cursor="pointinghand",
        )
        self.reset_btn.grid(row=0, column=1, padx=6)

    def _wrap_panel(self, widget):
        widget.configure(padding=(14, 10))

    # ---------- round dots ----------

    def _render_round_dots(self):
        for child in self.round_dots_frame.winfo_children():
            child.destroy()

        total = self.rounds_var.get()
        if total > 20:
            lbl = tk.Label(
                self.round_dots_frame,
                text=f"라운드 {self.current_round or 1} / {total}",
                bg=BG,
                fg=MUTED,
                font=("Helvetica Neue", 13),
            )
            lbl.pack()
            return

        for i in range(1, total + 1):
            color = IDLE_COLOR
            if i < self.current_round:
                color = DONE_COLOR
            elif i == self.current_round and self.phase in (
                self.STATE_WORK,
                self.STATE_REST,
            ):
                color = WORK_COLOR if self.phase == self.STATE_WORK else REST_COLOR
            dot = tk.Canvas(
                self.round_dots_frame,
                width=14,
                height=14,
                bg=BG,
                highlightthickness=0,
            )
            dot.create_oval(2, 2, 12, 12, fill=color, outline="")
            dot.pack(side="left", padx=3)

    # ---------- ring drawing ----------

    def _color_for_phase(self):
        return {
            self.STATE_WORK: WORK_COLOR,
            self.STATE_REST: REST_COLOR,
            self.STATE_DONE: DONE_COLOR,
        }.get(self.phase, IDLE_COLOR)

    def _label_for_phase(self):
        total = self.rounds_var.get()
        return {
            self.STATE_IDLE: "준비",
            self.STATE_WORK: f"운동 중 · {self.current_round}/{total}",
            self.STATE_REST: f"휴식 중 · {self.current_round}/{total}",
            self.STATE_DONE: "완료!",
        }[self.phase]

    def _draw_ring(self):
        self.canvas.delete("all")
        pad = RING_WIDTH
        x0, y0 = pad, pad
        x1, y1 = CANVAS_SIZE - pad, CANVAS_SIZE - pad

        self.canvas.create_oval(
            x0, y0, x1, y1, outline=RING_TRACK, width=RING_WIDTH
        )

        if self.phase_total > 0:
            fraction = self.remaining / self.phase_total
        else:
            fraction = 0 if self.phase == self.STATE_IDLE else 1
        fraction = max(0.0, min(1.0, fraction))
        extent = -360 * fraction

        if fraction > 0:
            self.canvas.create_arc(
                x0,
                y0,
                x1,
                y1,
                start=90,
                extent=extent,
                style="arc",
                outline=self._color_for_phase(),
                width=RING_WIDTH,
            )

        center = CANVAS_SIZE / 2
        self.canvas.create_text(
            center,
            center,
            text=fmt_time(self.remaining),
            fill=FG,
            font=("Helvetica Neue", 48, "bold"),
        )

        self.state_label.configure(text=self._label_for_phase(), fg=self._color_for_phase() if self.phase != self.STATE_IDLE else FG)
        self._render_round_dots()

    # ---------- state machine ----------

    def _set_inputs_enabled(self, enabled: bool):
        self.work_input.set_enabled(enabled)
        self.rest_input.set_enabled(enabled)
        self.rounds_box.configure(state="normal" if enabled else "disabled")

    def _reset_all(self):
        self._cancel_job()
        self.running = False
        self.phase = self.STATE_IDLE
        self.current_round = 0
        self.phase_total = self.work_input.total_seconds() or 1
        self.remaining = self.phase_total
        self._set_inputs_enabled(True)
        self.start_btn.configure(text="시작", bg=WORK_COLOR)
        self._draw_ring()

    def toggle_start_pause(self):
        if self.phase == self.STATE_DONE:
            self._reset_all()
            return

        if not self.running:
            if self.phase == self.STATE_IDLE:
                self._set_inputs_enabled(False)
                self._start_round(1, self.STATE_WORK)
            self.running = True
            self.start_btn.configure(text="일시정지", bg=PANEL, fg=FG)
            self._tick()
        else:
            self.running = False
            self._cancel_job()
            self.start_btn.configure(text="계속", bg=WORK_COLOR, fg="white")

    def _cancel_job(self):
        if self.timer_job is not None:
            self.after_cancel(self.timer_job)
            self.timer_job = None

    def _start_round(self, round_no: int, phase: str):
        self.current_round = round_no
        self.phase = phase
        duration = (
            self.work_input.total_seconds()
            if phase == self.STATE_WORK
            else self.rest_input.total_seconds()
        )
        self.phase_total = duration or 1
        self.remaining = self.phase_total
        play_sound(SOUND_TRANSITION)
        self._draw_ring()

    def _advance(self):
        total_rounds = self.rounds_var.get()
        skip_last_rest = self.skip_last_rest_var.get()

        if self.phase == self.STATE_WORK:
            is_last_round = self.current_round >= total_rounds
            if is_last_round and skip_last_rest:
                self._finish()
                return
            self._start_round(self.current_round, self.STATE_REST)
        elif self.phase == self.STATE_REST:
            if self.current_round >= total_rounds:
                self._finish()
                return
            self._start_round(self.current_round + 1, self.STATE_WORK)

    def _finish(self):
        self.running = False
        self._cancel_job()
        self.phase = self.STATE_DONE
        self.remaining = 0
        self.phase_total = 1
        play_sound(SOUND_DONE)
        self._set_inputs_enabled(True)
        self.start_btn.configure(text="다시 시작", bg=DONE_COLOR, fg="white")
        self._draw_ring()

    def _tick(self):
        if not self.running:
            return
        self.remaining -= 1
        if self.remaining < 0:
            self._advance()
        else:
            self._draw_ring()
        if self.running:
            self.timer_job = self.after(1000, self._tick)


def main():
    app = BulgarianBagTimer()
    app.mainloop()


if __name__ == "__main__":
    main()
