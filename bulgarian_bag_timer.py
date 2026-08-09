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
DIAL_TRACK = "#3a3a3c"
DIAL_TRACK_DISABLED = "#2a2a2c"

SOUND_TRANSITION = "/System/Library/Sounds/Glass.aiff"
SOUND_DONE = "/System/Library/Sounds/Hero.aiff"

CANVAS_SIZE = 300
RING_WIDTH = 14

FLASH_FRAMES = 6
FLASH_FRAME_MS = 45


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


class CircleButton(tk.Canvas):
    """A clean circular button: white fill, black text."""

    def __init__(self, parent, text, command, diameter=104, font_size=14):
        super().__init__(parent, width=diameter, height=diameter, bg=BG, highlightthickness=0)
        self.diameter = diameter
        self.command = command
        self.font = ("Helvetica Neue", font_size, "bold")
        self.fill_color = "white"

        pad = 2
        self.oval_id = self.create_oval(
            pad, pad, diameter - pad, diameter - pad, fill=self.fill_color, outline=""
        )
        self.text_id = self.create_text(
            diameter / 2, diameter / 2, text=text, fill="black", font=self.font
        )

        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda e: self.itemconfig(self.oval_id, fill="#e5e5e5"))
        self.bind("<Leave>", lambda e: self.itemconfig(self.oval_id, fill="white"))

    def _on_click(self, _event):
        if self.command:
            self.command()

    def set_text(self, text):
        self.itemconfig(self.text_id, text=text)


class Dial(tk.Frame):
    """A rotary dial control: drag around the ring (or scroll) to set a value."""

    def __init__(self, parent, caption, minimum, maximum, value, unit, accent, diameter=112):
        super().__init__(parent, bg=BG)
        self.minimum = minimum
        self.maximum = maximum
        self.value = value
        self.unit = unit
        self.accent = accent
        self.diameter = diameter
        self.enabled = True
        self.on_change = None

        cap = tk.Label(self, text=caption, bg=BG, fg=MUTED, font=("Helvetica Neue", 12))
        cap.pack(pady=(2, 6))

        self.canvas = tk.Canvas(
            self, width=diameter, height=diameter, bg=BG, highlightthickness=0
        )
        self.canvas.pack(pady=(0, 4))
        self.canvas.bind("<Button-1>", self._on_drag)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<MouseWheel>", self._on_wheel)

        self._draw()

    def _draw(self):
        self.canvas.delete("all")
        pad = 12
        x0, y0, x1, y1 = pad, pad, self.diameter - pad, self.diameter - pad
        track_color = DIAL_TRACK if self.enabled else DIAL_TRACK_DISABLED
        self.canvas.create_oval(x0, y0, x1, y1, outline=track_color, width=8)

        span = self.maximum - self.minimum
        fraction = (self.value - self.minimum) / span if span else 0
        color = self.accent if self.enabled else MUTED

        if fraction >= 0.999:
            self.canvas.create_oval(x0, y0, x1, y1, outline=color, width=8)
        elif fraction > 0:
            self.canvas.create_arc(
                x0, y0, x1, y1,
                start=90, extent=-360 * fraction,
                style="arc", outline=color, width=8,
            )

        cx = cy = self.diameter / 2
        r = (self.diameter - 2 * pad) / 2
        angle = math.radians(90 - 360 * fraction)
        hx, hy = cx + r * math.cos(angle), cy - r * math.sin(angle)
        self.canvas.create_oval(hx - 7, hy - 7, hx + 7, hy + 7, fill=color, outline=BG, width=2)

        text_color = FG if self.enabled else MUTED
        self.canvas.create_text(
            cx, cy, text=f"{self.value}{self.unit}",
            fill=text_color, font=("Helvetica Neue", 18, "bold"),
        )

    def _value_from_point(self, x, y):
        cx = cy = self.diameter / 2
        dx, dy = x - cx, y - cy
        angle = math.atan2(dx, -dy)
        if angle < 0:
            angle += 2 * math.pi
        fraction = angle / (2 * math.pi)
        value = round(self.minimum + fraction * (self.maximum - self.minimum))
        return max(self.minimum, min(self.maximum, value))

    def _apply_value(self, value):
        if value == self.value:
            return
        self.value = value
        self._draw()
        if self.on_change:
            self.on_change(self.value)

    def _on_drag(self, event):
        if not self.enabled:
            return
        self._apply_value(self._value_from_point(event.x, event.y))

    def _on_wheel(self, event):
        if not self.enabled:
            return
        step = 1 if event.delta > 0 else -1
        self._apply_value(max(self.minimum, min(self.maximum, self.value + step)))

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self._draw()


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
        self.total_elapsed = 0
        self.running = False
        self.timer_job = None
        self.flash_job = None

        self._build_ui()
        self._reset_all()

    # ---------- UI ----------

    def _build_ui(self):
        root = ttk.Frame(self, style="Root.TFrame", padding=24)
        root.pack(fill="both", expand=True)

        self.state_label = tk.Label(
            root, text="준비", bg=BG, fg=FG, font=("Helvetica Neue", 22, "bold")
        )
        self.state_label.pack(pady=(4, 2))

        self.progress_label = tk.Label(
            root, text="00:00 / 00:00", bg=BG, fg=MUTED, font=("Helvetica Neue", 13)
        )
        self.progress_label.pack(pady=(0, 14))

        self.canvas = tk.Canvas(
            root, width=CANVAS_SIZE, height=CANVAS_SIZE, bg=BG, highlightthickness=0
        )
        self.canvas.pack()

        self.round_dots_frame = tk.Frame(root, bg=BG)
        self.round_dots_frame.pack(pady=(14, 20))

        settings = ttk.Frame(root, style="Root.TFrame")
        settings.pack(pady=(0, 18))

        self.work_dial = Dial(
            settings, "운동", minimum=0, maximum=60, value=30, unit="초", accent=WORK_COLOR
        )
        self.work_dial.grid(row=0, column=0, padx=14)

        self.rest_dial = Dial(
            settings, "휴식", minimum=0, maximum=60, value=15, unit="초", accent=REST_COLOR
        )
        self.rest_dial.grid(row=0, column=1, padx=14)

        self.rounds_dial = Dial(
            settings, "라운드", minimum=1, maximum=60, value=5, unit="회", accent=FG
        )
        self.rounds_dial.grid(row=0, column=2, padx=14)

        self.work_dial.on_change = lambda _v: self._on_settings_changed()
        self.rest_dial.on_change = lambda _v: self._on_settings_changed()
        self.rounds_dial.on_change = lambda _v: self._on_settings_changed()

        self.skip_last_rest_var = tk.BooleanVar(value=True)
        skip_check = tk.Checkbutton(
            root,
            text="마지막 휴식 생략",
            variable=self.skip_last_rest_var,
            command=self._on_settings_changed,
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

        self.start_btn = CircleButton(buttons, "시작", self.toggle_start_pause)
        self.start_btn.grid(row=0, column=0, padx=10)

        self.reset_btn = CircleButton(buttons, "리셋", self._reset_all)
        self.reset_btn.grid(row=0, column=1, padx=10)

    def _on_settings_changed(self):
        if self.phase == self.STATE_IDLE:
            self.phase_total = self.work_dial.value or 1
            self.remaining = self.phase_total
            self._draw_ring()
        else:
            self._update_progress_label()

    def _total_planned_seconds(self):
        rounds = self.rounds_dial.value
        work_rounds_seconds = rounds * self.work_dial.value
        rest_rounds = rounds - 1 if self.skip_last_rest_var.get() else rounds
        rest_rounds = max(0, rest_rounds)
        return work_rounds_seconds + rest_rounds * self.rest_dial.value

    def _update_progress_label(self):
        self.progress_label.configure(
            text=f"{fmt_time(self.total_elapsed)} / {fmt_time(self._total_planned_seconds())}"
        )

    # ---------- round dots ----------

    def _render_round_dots(self):
        for child in self.round_dots_frame.winfo_children():
            child.destroy()

        total = self.rounds_dial.value
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
        total = self.rounds_dial.value
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

        if fraction >= 0.999:
            # Tk's create_arc silently draws nothing for a full 360° sweep
            # (start == end point), so a full ring needs a plain circle.
            self.canvas.create_oval(
                x0, y0, x1, y1, outline=self._color_for_phase(), width=RING_WIDTH
            )
        elif fraction > 0:
            self.canvas.create_arc(
                x0,
                y0,
                x1,
                y1,
                start=90,
                extent=-360 * fraction,
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

        self.state_label.configure(
            text=self._label_for_phase(),
            fg=self._color_for_phase() if self.phase != self.STATE_IDLE else FG,
        )
        self._render_round_dots()
        self._update_progress_label()

    # ---------- completion flash animation ----------
    # Purely cosmetic overlay drawn on top of the already-advanced ring.
    # It never delays or reschedules the tick loop, so it cannot push the
    # actual work/rest timing off schedule.

    def _cancel_flash(self):
        if self.flash_job is not None:
            self.after_cancel(self.flash_job)
            self.flash_job = None
        self.canvas.delete("flash")

    def _draw_flash_overlay(self, frame, total):
        self.canvas.delete("flash")
        center = CANVAS_SIZE / 2
        max_r = CANVAS_SIZE / 2 - RING_WIDTH / 2
        fraction = 1 - frame / (total - 1)
        r = max_r * fraction
        if r <= 0:
            return
        self.canvas.create_oval(
            center - r, center - r, center + r, center + r,
            fill="white", outline="", tags="flash",
        )
        if fraction >= 0.4:
            self.canvas.create_text(
                center, center, text="00:00", fill="black",
                font=("Helvetica Neue", 48, "bold"), tags="flash",
            )

    def _play_completion_flash(self, frame=0):
        self._draw_flash_overlay(frame, FLASH_FRAMES)
        if frame + 1 < FLASH_FRAMES:
            self.flash_job = self.after(
                FLASH_FRAME_MS, lambda: self._play_completion_flash(frame + 1)
            )
        else:
            self.flash_job = None
            self.canvas.delete("flash")

    # ---------- state machine ----------

    def _set_inputs_enabled(self, enabled: bool):
        self.work_dial.set_enabled(enabled)
        self.rest_dial.set_enabled(enabled)
        self.rounds_dial.set_enabled(enabled)

    def _reset_all(self):
        self._cancel_job()
        self._cancel_flash()
        self.running = False
        self.phase = self.STATE_IDLE
        self.current_round = 0
        self.phase_total = self.work_dial.value or 1
        self.remaining = self.phase_total
        self.total_elapsed = 0
        self._set_inputs_enabled(True)
        self.start_btn.set_text("시작")
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
            self.start_btn.set_text("일시정지")
            self.timer_job = self.after(1000, self._tick)
        else:
            self.running = False
            self._cancel_job()
            self.start_btn.set_text("계속")

    def _cancel_job(self):
        if self.timer_job is not None:
            self.after_cancel(self.timer_job)
            self.timer_job = None

    def _start_round(self, round_no: int, phase: str):
        self.current_round = round_no
        self.phase = phase
        duration = (
            self.work_dial.value if phase == self.STATE_WORK else self.rest_dial.value
        )
        self.phase_total = duration or 1
        self.remaining = self.phase_total
        play_sound(SOUND_TRANSITION)
        self._draw_ring()
        self._play_completion_flash()

    def _advance(self):
        total_rounds = self.rounds_dial.value
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
        self.start_btn.set_text("다시 시작")
        self._draw_ring()
        self._play_completion_flash()

    def _tick(self):
        if not self.running:
            return
        self.remaining -= 1
        self.total_elapsed += 1
        if self.remaining <= 0:
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
