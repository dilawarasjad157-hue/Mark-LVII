"""gui/jarvis_fx.py — the cinematic layer of the HUD.

What it adds, all painted with QPainter (no new dependency, no GPU):

  * the circular interface behind the centrepiece — concentric rings with
    graduations and bearings, segmented bands, long counter-rotating arcs,
    cardinal markers, a sweeping scanner and a spectrum ring that is the REAL
    audio level;
  * a boot sequence — the rings expand and light up when the HUD first appears;
  * corner telemetry — clock and date, and live CPU / memory / battery / network
    figures read from psutil, plus edge rulers whose cursors follow the real CPU
    load and the real audio level;
  * a radar and a scrolling data link in the lower corners;
  * a glass finish — fine scan lines, a slow light sweep and a vignette.

Everything reads the palette at paint time, so the accent picker retints it.
Nothing here may ever stop the HUD from drawing: HudCanvas wraps every call and
switches the layer off for good if one raises.
"""
from __future__ import annotations

import math
import random
import time

import psutil
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QConicalGradient, QFont, QLinearGradient,
                         QPainter, QPen, QPixmap, QPolygonF, QRadialGradient)

from gui.style import px_font, tint, with_alpha

_AL = Qt.AlignmentFlag
_DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1.0 - (1.0 - x) ** 3


class JarvisFX:
    """State + renderer for the cinematic layer. `step()` advances it,
    the `paint_*` methods draw one frame each."""

    BOOT_SECONDS = 3.0

    def __init__(self):
        self._t0 = time.time()
        self.phase = 0.0                # integrated, so a rate change never jumps the rings
        self._sample_t = 0.0
        self._cpu = 0.0
        self._mem = 0.0
        self._bat = -1.0
        self._plugged = False
        self._net_dn = 0.0
        self._net_up = 0.0
        self._net_last = None
        self._cpu_disp = 0.0
        self._rng = random.Random(57)
        self._blips = [(self._rng.uniform(0, 360), self._rng.uniform(0.25, 0.9),
                        self._rng.uniform(0, 6.0)) for _ in range(7)]
        self._stream = [self._hex_line() for _ in range(7)]
        self._stream_t = 0.0
        self._side = False
        self._glass: QPixmap | None = None
        self._glass_key = None
        try:
            psutil.cpu_percent(None)    # prime the non-blocking reading
        except Exception:
            pass

    # ── data ─────────────────────────────────────────────────────────────────
    def _hex_line(self) -> str:
        r = self._rng
        return "%04X  %04X %04X  %02X" % (r.randrange(0x10000), r.randrange(0x10000),
                                           r.randrange(0x10000), r.randrange(0x100))

    def _sample(self, now: float) -> None:
        """Once a second: cheap, non-blocking, never raises."""
        if now - self._sample_t < 1.0:
            return
        dt = max(0.2, now - self._sample_t) if self._sample_t else 1.0
        self._sample_t = now
        try:
            self._cpu = float(psutil.cpu_percent(None))
            self._mem = float(psutil.virtual_memory().percent)
        except Exception:
            pass
        try:
            b = psutil.sensors_battery()
            if b is not None:
                self._bat, self._plugged = float(b.percent), bool(b.power_plugged)
        except Exception:
            self._bat = -1.0
        try:
            n = psutil.net_io_counters()
            if self._net_last is not None:
                self._net_dn = max(0.0, (n.bytes_recv - self._net_last[0]) / dt)
                self._net_up = max(0.0, (n.bytes_sent - self._net_last[1]) / dt)
            self._net_last = (n.bytes_recv, n.bytes_sent)
        except Exception:
            pass

    @staticmethod
    def _rate(bps: float) -> str:
        if bps < 1024:
            return "%d B/s" % bps
        if bps < 1024 * 1024:
            return "%.0f KB/s" % (bps / 1024)
        return "%.1f MB/s" % (bps / 1024 / 1024)

    # ── layout ───────────────────────────────────────────────────────────────
    SIDE_MIN_W = 900        # narrower than this the corner blocks are dropped
    SIDE_MARGIN = 250       # width each corner block may take beside the rings

    def layout(self, W: float, band_h: float) -> float:
        """Ring radius for a canvas of this size. On a wide canvas the rings are
        held clear of the corner blocks; on a narrow one the blocks are dropped
        and the rings take the room."""
        R = min(W * 0.47, band_h * 0.50)
        self._side = W >= self.SIDE_MIN_W
        if self._side:
            R = min(R, (W - 2 * self.SIDE_MARGIN) / 2.0)
        return max(40.0, R)

    # ── motion ───────────────────────────────────────────────────────────────
    def step(self, dt: float, rate: float) -> None:
        dt = min(0.10, max(0.0, dt))
        self.phase += dt * rate
        self._cpu_disp += (self._cpu - self._cpu_disp) * min(1.0, dt * 3.0)
        now = time.time()
        self._sample(now)
        self._stream_t += dt
        if self._stream_t > 0.16:
            self._stream_t = 0.0
            self._stream.pop(0)
            self._stream.append(self._hex_line())

    @property
    def boot(self) -> float:
        """0 → 1 over the boot sequence, then stays at 1."""
        return _ease((time.time() - self._t0) / self.BOOT_SECONDS)

    @property
    def booting(self) -> bool:
        return (time.time() - self._t0) < self.BOOT_SECONDS

    # ── the circular interface ───────────────────────────────────────────────
    def paint_rings(self, p: QPainter, cx: float, cy: float, R: float,
                    main: QColor, acc: QColor, amp: float, live: bool,
                    full: bool = True) -> None:
        """The concentric interface. `full` draws the inner rings too; with the
        3-D reactor as centrepiece only the outer bands are drawn so the two
        do not fight."""
        b = self.boot
        if b <= 0.01 or R < 60:
            return
        R = R * (0.78 + 0.22 * b)
        t = self.phase
        A = b                                   # master alpha during boot
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)

        def circle(k, a, w=1.0, style=None):
            rad = R * k
            pen = QPen(with_alpha(main, a * A), w)
            if style is not None:
                pen.setStyle(style)
            p.setPen(pen)
            p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))

        # outer edge, with a soft halo outside it
        circle(1.00, 0.55, 1.4)
        circle(1.012, 0.14, 1.0)

        # 1. graduated bezel: 120 ticks, a long one every 10, bearings every 30
        rot = (t * 4.0) % 360.0
        minor, major = [], []
        for i in range(120):
            a = math.radians(i * 3.0 + rot - 90.0)
            ca, sa = math.cos(a), math.sin(a)
            r0 = R * (0.955 if i % 10 == 0 else 0.972 if i % 5 == 0 else 0.982)
            ln = QLineF(cx + ca * r0, cy + sa * r0, cx + ca * R * 0.995, cy + sa * R * 0.995)
            (major if i % 5 == 0 else minor).append(ln)
        p.setPen(QPen(with_alpha(main, 0.22 * A), 1))
        p.drawLines(minor)
        p.setPen(QPen(with_alpha(main, 0.70 * A), 1.3))
        p.drawLines(major)
        if R > 150:
            p.setFont(px_font(max(8, R * 0.032), QFont.Weight.DemiBold, mono=True, spacing=1))
            p.setPen(QPen(with_alpha(main, 0.62 * A)))
            for k in range(12):
                deg = k * 30
                p.save()
                p.translate(cx, cy)
                p.rotate(deg + rot)
                p.drawText(QRectF(-22, -R * 0.905 - 7, 44, 14), _AL.AlignCenter, "%03d" % deg)
                p.restore()

        # 2. segmented band — 36 plates, a few lit in the accent
        rad = R * 0.885
        box = QRectF(cx - rad, cy - rad, rad * 2, rad * 2)
        base = (-t * 10.0) % 360.0
        for i in range(36):
            lit = (i % 9 == int(t * 0.6) % 9)
            p.setPen(QPen(with_alpha(acc if lit else main, (0.85 if lit else 0.30) * A),
                          3.2 if lit else 2.2))
            p.drawArc(box, int((base + i * 10.0) * 16), int(7.0 * 16))

        # 3. dotted ring
        circle(0.83, 0.28, 1.0, Qt.PenStyle.DotLine)

        # 4. long arcs, each at its own speed and direction
        for k, (kr, span, cnt, sp, col, a, w) in enumerate((
                (0.790, 96, 2, +14, main, 0.95, 3.6),
                (0.745, 54, 3, -22, main, 0.50, 1.6),
                (0.700, 140, 1, +9, main, 0.40, 1.4))):
            rad = R * kr
            box = QRectF(cx - rad, cy - rad, rad * 2, rad * 2)
            p.setPen(QPen(with_alpha(col, a * A), w))
            for s in range(cnt):
                p.drawArc(box, int(((t * sp) + s * 360.0 / cnt) * 16 % (360 * 16)), int(span * 16))

        # 5. cardinal markers riding the 0.665 ring
        rad = R * 0.665
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(with_alpha(acc, 0.9 * A)))
        for k in range(4):
            a = math.radians(k * 90.0 + t * 18.0)
            ca, sa = math.cos(a), math.sin(a)
            tip = QPointF(cx + ca * (rad + 7), cy + sa * (rad + 7))
            l = QPointF(cx + math.cos(a + 0.05) * (rad - 4), cy + math.sin(a + 0.05) * (rad - 4))
            r = QPointF(cx + math.cos(a - 0.05) * (rad - 4), cy + math.sin(a - 0.05) * (rad - 4))
            p.drawPolygon(QPolygonF([tip, l, r]))
        p.setBrush(Qt.BrushStyle.NoBrush)
        circle(0.665, 0.30, 1.0)

        # 6. fixed crosshair ticks outside the bezel — the frame the rings turn in
        p.setPen(QPen(with_alpha(main, 0.55 * A), 1.4))
        for k in range(4):
            a = math.radians(k * 90.0)
            ca, sa = math.cos(a), math.sin(a)
            p.drawLine(QLineF(cx + ca * R * 1.02, cy + sa * R * 1.02,
                              cx + ca * R * 1.07, cy + sa * R * 1.07))

        if full:
            # 7. scanner sweep — a conical wash that trails a bright leading edge
            rad = R * 0.62
            ang = (t * 55.0) % 360.0
            g = QConicalGradient(QPointF(cx, cy), ang)
            g.setColorAt(0.00, with_alpha(main, 0.34 * A))
            g.setColorAt(0.02, with_alpha(main, 0.0))
            g.setColorAt(0.78, with_alpha(main, 0.0))
            g.setColorAt(1.00, with_alpha(main, 0.34 * A))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            a = math.radians(-ang)
            p.setPen(QPen(with_alpha(main, 0.55 * A), 1.2))
            p.drawLine(QLineF(cx, cy, cx + math.cos(a) * rad, cy + math.sin(a) * rad))
            circle(0.62, 0.30, 1.0)

            # 8. the voice: 72 spokes whose length is the real audio level
            ring = R * 0.545
            spikes = []
            for i in range(72):
                a = math.radians(i * 5.0)
                ca, sa = math.cos(a), math.sin(a)
                wob = 0.5 + 0.5 * math.sin(t * 2.6 + i * 0.5)
                idle = 0.006 + 0.004 * math.sin(t * 1.1 + i * 0.7)
                h = R * (idle + (amp * 0.10 * wob if live else 0.0))
                spikes.append(QLineF(cx + ca * ring, cy + sa * ring,
                                     cx + ca * (ring + h), cy + sa * (ring + h)))
            p.setPen(QPen(with_alpha(acc if live else main, (0.30 + 0.55 * amp) * A), 1.5))
            p.drawLines(spikes)
            circle(0.545, 0.22, 1.0)
        p.restore()

    # ── the centrepiece of the opening sequence ──────────────────────────────
    def paint_core_video(self, p: QPainter, cx: float, cy: float, R: float,
                         main: QColor, acc: QColor, amp: float, live: bool,
                         glow: QColor | None = None) -> None:
        """The monochrome ring core from the opening sequence: hairline rings
        with a fine tick edge, a dark teal wavering band, thick white arcs that
        turn at different speeds, hollow triangle markers left and right, two
        tilted orbit ellipses and a bright centre. The spokes between the
        arcs are the real audio level."""
        b = self.boot
        if b <= 0.01 or R < 40:
            return
        R = R * (0.80 + 0.20 * b)
        t = self.phase
        A = b
        glow = glow or QColor(tint())
        NO = Qt.BrushStyle.NoBrush
        p.save()
        p.setBrush(NO)

        def circle(k, a, w=1.0, col=None, style=None):
            rad = R * k
            pen = QPen(with_alpha(col or main, a * A), w)
            if style is not None:
                pen.setStyle(style)
            p.setPen(pen)
            p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))

        def arcs(k, span, count, speed, a, w, col=None, off=0.0):
            rad = R * k
            box = QRectF(cx - rad, cy - rad, rad * 2, rad * 2)
            p.setPen(QPen(with_alpha(col or main, a * A), w))
            for s in range(count):
                start = (t * speed + off + s * 360.0 / count) % 360.0
                p.drawArc(box, int(start * 16), int(span * 16))

        # 1. the light behind the rings — a dark teal body, brightest at the centre
        lift = 1.0 + 0.9 * amp
        g = QRadialGradient(cx, cy, R * 0.80)
        g.setColorAt(0.00, with_alpha(glow, min(0.55, 0.30 * lift) * A))
        g.setColorAt(0.45, with_alpha(glow, min(0.40, 0.15 * lift) * A))
        g.setColorAt(0.85, with_alpha(glow, 0.05 * A))
        g.setColorAt(1.00, with_alpha(glow, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QRectF(cx - R * 0.80, cy - R * 0.80, R * 1.6, R * 1.6))
        p.setBrush(NO)

        # 2. tilted orbit ellipses — the video turns its rings through space
        for k, (base, spd, wide) in enumerate(((24.0, 3.2, 1.0), (-38.0, -2.4, 0.94))):
            tilt = 0.20 + 0.20 * abs(math.sin(t * 0.22 + k * 1.7))
            p.save()
            p.translate(cx, cy)
            p.rotate(base + t * spd)
            p.setPen(QPen(with_alpha(main, 0.11 * A), 1.0))
            p.drawEllipse(QRectF(-R * wide, -R * wide * tilt, R * wide * 2, R * wide * tilt * 2))
            p.restore()

        # 3. outer hairlines and the fine tick edge
        circle(1.000, 0.55, 1.3)
        circle(0.925, 0.26, 1.0)
        circle(0.870, 0.50, 1.8)
        rot = (t * 3.0) % 360.0
        minor, major = [], []
        for i in range(180):
            a = math.radians(i * 2.0 + rot - 90.0)
            ca, sa = math.cos(a), math.sin(a)
            r0 = R * (0.955 if i % 15 == 0 else 0.972 if i % 5 == 0 else 0.981)
            ln = QLineF(cx + ca * r0, cy + sa * r0, cx + ca * R * 0.992, cy + sa * R * 0.992)
            (major if i % 5 == 0 else minor).append(ln)
        p.setPen(QPen(with_alpha(main, 0.20 * A), 1))
        p.drawLines(minor)
        p.setPen(QPen(with_alpha(main, 0.65 * A), 1.2))
        p.drawLines(major)

        # 4. the wavering teal band — the textured ring of the video
        for rr, ph, a, w in ((0.765, 0.0, 0.24, 2.8), (0.735, 2.1, 0.14, 1.2)):
            pts = []
            for i in range(241):
                th = i * (2.0 * math.pi / 240.0)
                wob = (0.011 * math.sin(14 * th + t * 0.9 + ph)
                       + 0.006 * math.sin(33 * th - t * 1.4 + ph)
                       + 0.010 * amp * math.sin(9 * th + t * 3.0))
                rad = R * (rr + wob)
                pts.append(QPointF(cx + math.cos(th) * rad, cy + math.sin(th) * rad))
            p.setPen(QPen(with_alpha(glow, a * A), w))
            p.drawPolyline(QPolygonF(pts))

        # 5. the thick white arcs, each at its own speed and direction
        arcs(0.805, 64, 2, +9.0, 0.80, 3.0)
        arcs(0.640, 118, 1, +13.0, 0.97, 4.6)
        arcs(0.640, 16, 1, +13.0, 0.60, 4.6, off=134.0)
        arcs(0.575, 205, 1, -17.0, 0.55, 1.6)
        arcs(0.505, 44, 3, +27.0, 0.85, 3.0)
        arcs(0.430, 92, 2, -36.0, 0.60, 1.8)
        arcs(0.345, 150, 1, +21.0, 0.92, 3.8)

        # 6. the inner rings and the centre
        circle(0.300, 0.85, 2.4)
        circle(0.245, 0.34, 1.0)
        circle(0.165, 0.70, 1.6)
        circle(0.075, 0.90, 1.4)
        cg = QRadialGradient(cx, cy, R * 0.07)
        cg.setColorAt(0.0, with_alpha(main, 0.95 * A))
        cg.setColorAt(0.35, with_alpha(main, 0.55 * A))
        cg.setColorAt(1.0, with_alpha(main, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(cg))
        p.drawEllipse(QRectF(cx - R * 0.07, cy - R * 0.07, R * 0.14, R * 0.14))
        p.setBrush(NO)

        # 7. hollow triangle markers, left and right, drifting together
        drift = 7.0 * math.sin(t * 0.35)
        p.setPen(QPen(with_alpha(main, 0.80 * A), 1.2))
        rad = R * 0.585
        for side in (0.0, 180.0):
            a = math.radians(side + drift)
            tip = QPointF(cx + math.cos(a) * (rad - R * 0.03), cy + math.sin(a) * (rad - R * 0.03))
            l = QPointF(cx + math.cos(a + 0.045) * (rad + R * 0.025), cy + math.sin(a + 0.045) * (rad + R * 0.025))
            r = QPointF(cx + math.cos(a - 0.045) * (rad + R * 0.025), cy + math.sin(a - 0.045) * (rad + R * 0.025))
            p.drawPolygon(QPolygonF([tip, l, r]))

        # 8. the voice — spokes between the arcs and the inner ring
        ring = R * 0.385
        spokes = []
        for i in range(72):
            a = math.radians(i * 5.0)
            ca, sa = math.cos(a), math.sin(a)
            wob = 0.5 + 0.5 * math.sin(t * 2.6 + i * 0.5)
            idle = 0.005 + 0.003 * math.sin(t * 1.1 + i * 0.7)
            h = R * (idle + (amp * 0.085 * wob if live else 0.0))
            spokes.append(QLineF(cx + ca * ring, cy + sa * ring,
                                 cx + ca * (ring + h), cy + sa * (ring + h)))
        p.setPen(QPen(with_alpha(acc if live else main, (0.28 + 0.60 * amp) * A), 1.3))
        p.drawLines(spokes)
        p.restore()

    # ── telemetry ────────────────────────────────────────────────────────────
    def paint_telemetry(self, p: QPainter, W: float, H: float, main: QColor,
                        acc: QColor, amp: float) -> None:
        """Clock, live system figures and the two edge rulers."""
        b = self.boot
        if b <= 0.02 or not self._side or H < 360:
            return
        p.save()
        m = 26.0
        x = m + 8
        y = m + 22
        lt = time.localtime()
        p.setPen(QPen(with_alpha(main, 0.55 * b)))
        p.setFont(px_font(9.5, QFont.Weight.DemiBold, mono=True, spacing=2))
        p.drawText(QRectF(x, y, 220, 14), _AL.AlignVCenter, "LOCAL TIME")
        p.setPen(QPen(with_alpha(main, 0.95 * b)))
        p.setFont(px_font(30, QFont.Weight.Light, mono=True, spacing=1))
        p.drawText(QRectF(x, y + 12, 220, 36), _AL.AlignVCenter,
                   "%02d:%02d:%02d" % (lt.tm_hour, lt.tm_min, lt.tm_sec))
        p.setPen(QPen(with_alpha(acc, 0.85 * b)))
        p.setFont(px_font(11, QFont.Weight.DemiBold, mono=True, spacing=2))
        p.drawText(QRectF(x, y + 50, 240, 16), _AL.AlignVCenter,
                   "%s  %02d %s %d" % (_DAYS[lt.tm_wday], lt.tm_mday, _MONTHS[lt.tm_mon - 1], lt.tm_year))
        p.setPen(QPen(with_alpha(main, 0.30 * b), 1))
        p.drawLine(QLineF(x, y + 70, x + 170, y + 70))

        # right block — live figures
        rx = W - m - 8 - 190
        rows = [("CPU", "%3.0f%%" % self._cpu, self._cpu / 100.0),
                ("MEM", "%3.0f%%" % self._mem, self._mem / 100.0)]
        if self._bat >= 0:
            rows.append(("PWR", ("%3.0f%%%s" % (self._bat, " +" if self._plugged else "")),
                         self._bat / 100.0))
        rows.append(("NET", "%s" % self._rate(self._net_dn), min(1.0, self._net_dn / (2 * 1024 * 1024))))
        p.setFont(px_font(9.5, QFont.Weight.DemiBold, mono=True, spacing=2))
        for i, (lab, val, frac) in enumerate(rows):
            yy = y + i * 22
            p.setPen(QPen(with_alpha(main, 0.55 * b)))
            p.drawText(QRectF(rx, yy, 40, 14), _AL.AlignVCenter, lab)
            p.setPen(QPen(with_alpha(main, 0.95 * b)))
            p.drawText(QRectF(rx + 40, yy, 74, 14), _AL.AlignVCenter | _AL.AlignRight, val)
            bx = rx + 122
            p.setPen(QPen(with_alpha(main, 0.25 * b), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(bx, yy + 3, 66, 8))
            hot = frac > 0.85
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(with_alpha(acc if hot else main, 0.85 * b)))
            p.drawRect(QRectF(bx + 1, yy + 4, max(1.0, 64 * max(0.0, min(1.0, frac))), 6))
        p.setBrush(Qt.BrushStyle.NoBrush)

        # edge rulers — left follows CPU load, right follows the voice
        top, bot = H * 0.30, H * 0.66
        for side, val, col in ((0, self._cpu_disp / 100.0, main), (1, amp, acc)):
            ex = 12.0 if side == 0 else W - 12.0
            sgn = 1 if side == 0 else -1
            p.setPen(QPen(with_alpha(main, 0.30 * b), 1))
            p.drawLine(QLineF(ex, top, ex, bot))
            ticks = []
            n = 21
            for i in range(n):
                ty = top + (bot - top) * i / (n - 1)
                ln = 9.0 if i % 5 == 0 else 5.0
                ticks.append(QLineF(ex, ty, ex + sgn * ln, ty))
            p.drawLines(ticks)
            cy = bot - (bot - top) * max(0.0, min(1.0, val))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(with_alpha(col, 0.95 * b)))
            p.drawPolygon(QPolygonF([QPointF(ex + sgn * 3, cy), QPointF(ex + sgn * 14, cy - 5),
                                     QPointF(ex + sgn * 14, cy + 5)]))
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.restore()

    # ── radar + data link ────────────────────────────────────────────────────
    def paint_radar(self, p: QPainter, W: float, H: float, main: QColor, acc: QColor) -> None:
        b = self.boot
        if b <= 0.05 or not self._side or H < 430:
            return
        rad = 56.0
        cx, cy = 26.0 + 14 + rad, H - 26.0 - 14 - rad
        t = self.phase
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k in (1.0, 0.66, 0.33):
            p.setPen(QPen(with_alpha(main, (0.50 if k == 1.0 else 0.22) * b), 1))
            p.drawEllipse(QRectF(cx - rad * k, cy - rad * k, rad * 2 * k, rad * 2 * k))
        p.setPen(QPen(with_alpha(main, 0.22 * b), 1))
        p.drawLine(QLineF(cx - rad, cy, cx + rad, cy))
        p.drawLine(QLineF(cx, cy - rad, cx, cy + rad))
        ang = (t * 70.0) % 360.0
        g = QConicalGradient(QPointF(cx, cy), ang)
        g.setColorAt(0.00, with_alpha(main, 0.45 * b))
        g.setColorAt(0.04, with_alpha(main, 0.0))
        g.setColorAt(0.70, with_alpha(main, 0.0))
        g.setColorAt(1.00, with_alpha(main, 0.45 * b))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))
        p.setBrush(QBrush(with_alpha(acc, 0.95 * b)))
        for deg, k, off in self._blips:
            # a contact brightens as the beam passes over it, then fades
            lag = (ang - deg) % 360.0
            if lag > 200.0:
                continue
            a = (1.0 - lag / 200.0)
            r = rad * k
            bx = cx + math.cos(math.radians(-deg)) * r
            by = cy + math.sin(math.radians(-deg)) * r
            p.setBrush(QBrush(with_alpha(acc, 0.9 * a * b)))
            p.drawEllipse(QPointF(bx, by), 2.2, 2.2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(with_alpha(main, 0.55 * b)))
        p.setFont(px_font(9, QFont.Weight.DemiBold, mono=True, spacing=2))
        p.drawText(QRectF(cx - rad, cy + rad + 4, rad * 2, 12), _AL.AlignCenter, "PROXIMITY SCAN")
        p.restore()

    def paint_datalink(self, p: QPainter, W: float, H: float, main: QColor, acc: QColor) -> None:
        b = self.boot
        if b <= 0.05 or not self._side or H < 430:
            return
        x = W - 26.0 - 14 - 170
        y = H - 26.0 - 14 - 7 * 13 - 16
        p.save()
        p.setFont(px_font(9, QFont.Weight.DemiBold, mono=True, spacing=2))
        p.setPen(QPen(with_alpha(main, 0.55 * b)))
        p.drawText(QRectF(x, y, 170, 12), _AL.AlignVCenter, "DATA LINK  //  ENCRYPTED")
        p.setFont(px_font(9.5, mono=True))
        n = len(self._stream)
        for i, line in enumerate(self._stream):
            a = (0.25 + 0.6 * (i + 1) / n) * b
            p.setPen(QPen(with_alpha(acc if i == n - 1 else main, a)))
            p.drawText(QRectF(x, y + 16 + i * 13, 190, 13), _AL.AlignVCenter, line)
        p.restore()

    # ── readout box (the "KC // ENGINE" panel of the opening sequence) ─────────
    def paint_tag(self, p: QPainter, W: float, H: float, main: QColor, acc: QColor,
                  code: str, title: str, state: str) -> None:
        b = self.boot
        if b <= 0.05 or not self._side or H < 470:
            return
        x, y, w = 38.0, 150.0, 205.0
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(with_alpha(main, 0.75 * b), 1))
        p.drawRect(QRectF(x, y, w, 30))
        p.drawLine(QLineF(x + 46, y, x + 46, y + 30))
        p.setPen(QPen(with_alpha(main, 0.98 * b)))
        p.setFont(px_font(17, QFont.Weight.Bold, spacing=1))
        p.drawText(QRectF(x, y, 46, 30), _AL.AlignCenter, code)
        p.setFont(px_font(14, QFont.Weight.DemiBold, spacing=1))
        p.drawText(QRectF(x + 54, y, w - 58, 30), _AL.AlignVCenter, title)
        p.setPen(QPen(with_alpha(main, 0.45 * b), 1))
        p.drawLine(QLineF(x, y + 36, x + w, y + 36))
        p.setPen(QPen(with_alpha(acc, 0.9 * b), 3))
        p.drawLine(QLineF(x + 54, y + 36, x + 54 + 0.55 * (w - 54), y + 36))
        p.setFont(px_font(8.5, mono=True))
        for i, line in enumerate(self._stream):
            p.setPen(QPen(with_alpha(main, (0.18 + 0.5 * (i + 1) / len(self._stream)) * b)))
            p.drawText(QRectF(x, y + 44 + i * 11, w, 11), _AL.AlignVCenter,
                       "%s  %s" % (line, state[:10]))
        p.restore()

    # ── glass finish ─────────────────────────────────────────────────────────
    def _make_glass(self, W: int, H: int) -> QPixmap:
        pm = QPixmap(max(1, W), max(1, H))
        pm.fill(Qt.GlobalColor.transparent)
        g = QPainter(pm)
        g.setPen(QPen(QColor(0, 0, 0, 16), 1))
        y = 0
        while y < H:
            g.drawLine(QLineF(0, y, W, y))
            y += 3
        vg = QRadialGradient(W / 2, H / 2, max(W, H) * 0.72)
        vg.setColorAt(0.0, QColor(0, 0, 0, 0))
        vg.setColorAt(0.62, QColor(0, 0, 0, 0))
        vg.setColorAt(1.0, QColor(0, 0, 0, 150))
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(QBrush(vg))
        g.drawRect(QRectF(0, 0, W, H))
        g.end()
        return pm

    def paint_glass(self, p: QPainter, W: int, H: int, main: QColor) -> None:
        key = (W, H)
        if self._glass is None or self._glass_key != key:
            self._glass = self._make_glass(W, H)
            self._glass_key = key
        p.drawPixmap(0, 0, self._glass)
        # a slow band of light travelling down the screen
        per = 7.0
        k = ((time.time() % per) / per)
        y = -80 + (H + 160) * k
        lg = QLinearGradient(0, y - 60, 0, y + 60)
        lg.setColorAt(0.0, with_alpha(main, 0.0))
        lg.setColorAt(0.5, with_alpha(main, 0.022))
        lg.setColorAt(1.0, with_alpha(main, 0.0))
        p.fillRect(QRectF(0, y - 60, W, 120), QBrush(lg))
