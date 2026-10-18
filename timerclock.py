import calendar
import json
import math
import sys
import threading
from datetime import datetime

from PySide6.QtCore import (
    Qt,
    QElapsedTimer,
    QSettings,
    QTimer,
    QPoint,
    QPointF,
    QRectF,
    QSysInfo,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QConicalGradient,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSystemTrayIcon,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

IS_ANDROID = QSysInfo.productType() == "android"

if not IS_ANDROID:
    import winsound

MAX_MIN = 240
BG, SURF, BORD = "#0d1017", "#151a23", "#2a3242"
FG, SUB, TRACK = "#eef1f7", "#98a2b3", "#232b39"
ACC, ACC2, RED, RED_DIM = "#34d399", "#22d3ee", "#f87171", "#7c2d34"
ARC_COLORS = ["#5b8dff", "#ffb86b", "#c792ea", "#4dd0e1", "#ff8fab", "#a5d6a7"]
WD = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def beep_seq():
    if IS_ANDROID:
        QApplication.beep()
        return
    try:
        for f in (900, 1200, 900):
            winsound.Beep(f, 200)
    except Exception:
        winsound.MessageBeep()


def fmt_min(m):
    h, r = divmod(m, 60)
    if not h:
        return f"{r}分"
    return f"{h}小时" + (f"{r}分" if r else "")


def make_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ACC), 6))
    p.drawEllipse(7, 7, 50, 50)
    p.setPen(QPen(QColor(FG), 5, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(32, 34, 32, 15)
    p.drawLine(32, 34, 44, 41)
    p.end()
    return QIcon(pm)


class Dial(QWidget):
    picked = Signal(int)

    def __init__(self):
        super().__init__()
        self.mode = "timer"
        self.fraction = 0.0
        self.blink = False
        self.blink_on = True
        self.warn = False
        self.pickable = False
        self.arcs_show = False
        self.arcs = []
        self.setMouseTracking(True)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r = min(self.width(), self.height()) / 2 - 14
        halo = QColor(ACC)
        halo.setAlpha(10)
        p.setPen(QPen(QColor(BORD), 1))
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), r + 12, r + 12)
        card = QRadialGradient(QPointF(cx, cy - r * 0.3), r + 12)
        card.setColorAt(0.0, QColor("#1c2331"))
        card.setColorAt(1.0, QColor("#12161f"))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(card))
        p.drawEllipse(QPointF(cx, cy), r + 11, r + 11)
        if self.mode == "clock":
            self._clock(p, cx, cy, r)
        elif self.mode == "week":
            self._week(p, cx, cy, r)
        elif self.mode == "month":
            self._month(p, cx, cy, r)
        elif self.mode == "year":
            self._year(p, cx, cy, r)
        else:
            self._timer(p, cx, cy, r)

    def _ticks(self, p, cx, cy, r, n, per, off=0):
        for i in range(n):
            a = math.radians(off + i * 360 / n - 90)
            major = i % per == 0
            r1 = r - 16 if major else r - 10
            p.setPen(
                QPen(
                    QColor("#d8dfeb" if major else "#333d4e"),
                    2.5 if major else 1,
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )
            p.drawLine(
                QPointF(cx + math.cos(a) * r1, cy + math.sin(a) * r1),
                QPointF(cx + math.cos(a) * r, cy + math.sin(a) * r),
            )

    def _timer(self, p, cx, cy, r):
        self._ticks(p, cx, cy, r, 60, 5)
        r0 = r - 30
        rect = QRectF(cx - r0, cy - r0, r0 * 2, r0 * 2)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(TRACK), 9, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 90 * 16, -360 * 16)
        frac = max(0.0, min(1.0, self.fraction))
        if frac > 0:
            if self.blink:
                col = QColor(RED if self.blink_on else RED_DIM)
            else:
                glow = QColor(RED if self.warn else ACC)
                glow.setAlpha(30)
                p.setPen(QPen(glow, 16, Qt.SolidLine, Qt.RoundCap))
                p.drawArc(rect, 90 * 16, int(-360 * 16 * frac))
                if self.warn:
                    col = QColor(RED)
                else:
                    g = QConicalGradient(QPointF(cx, cy), 90 - 360 * frac)
                    g.setColorAt(0.0, QColor(ACC2))
                    g.setColorAt(frac, QColor(ACC))
                    col = QBrush(g)
            p.setPen(QPen(col, 9, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, 90 * 16, int(-360 * 16 * frac))
        a = math.radians(-90 + 360 * frac)
        ln = r0 - 8
        p.setPen(QPen(QColor(FG), 2.5, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(
            QPointF(cx, cy), QPointF(cx + math.cos(a) * ln, cy + math.sin(a) * ln)
        )
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(FG)))
        p.drawEllipse(QPointF(cx, cy), 4, 4)

    def _ring(self, p, cx, cy, r, frac, start=-90):
        r0 = r - 30
        rect = QRectF(cx - r0, cy - r0, r0 * 2, r0 * 2)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(TRACK), 9, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, start * 16, -360 * 16)
        if frac > 0:
            glow = QColor(ACC)
            glow.setAlpha(28)
            p.setPen(QPen(glow, 16, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, start * 16, -int(360 * 16 * frac))
            g = QConicalGradient(QPointF(cx, cy), start - 360 * frac)
            g.setColorAt(0.0, QColor(ACC2))
            g.setColorAt(min(frac, 1.0), QColor(ACC))
            p.setPen(QPen(QBrush(g), 9, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, start * 16, -int(360 * 16 * frac))
        return r0 - 10

    def _hand(self, p, cx, cy, ln, rot):
        p.save()
        p.translate(cx, cy)
        p.rotate(rot)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(FG)))
        p.drawRoundedRect(QRectF(-2.5, -ln, 5, ln), 2.5, 2.5)
        p.restore()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(FG)))
        p.drawEllipse(QPointF(cx, cy), 4.5, 4.5)
        p.setBrush(QBrush(QColor(ACC)))
        p.drawEllipse(QPointF(cx, cy), 2, 2)

    def _clock(self, p, cx, cy, r):
        self._ticks(p, cx, cy, r, 48, 2)
        now = datetime.now()
        m = now.minute + (now.second + now.microsecond / 1e6) / 60
        h = now.hour + m / 60
        ln = self._ring(p, cx, cy, r, h * 3600 / 86400)
        self._arcs(p, cx, cy, r)
        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        p.setPen(QColor(FG))
        for val in range(2, 25, 2):
            a = math.radians((val - 12) * 15 - 90)
            x, y = cx + math.cos(a) * (r - 58), cy + math.sin(a) * (r - 58)
            p.drawText(QRectF(x - 18, y - 10, 36, 20), Qt.AlignCenter, str(val))
        self._hand(p, cx, cy, ln - 32, (h - 12) / 24 * 360)

    def _arcs(self, p, cx, cy, r):
        if not self.arcs_show:
            return
        rs = r - 42
        for i, a in enumerate(self.arcs):
            d = (a["to"] - a["from"]) % 1440
            if not d:
                continue
            col = QColor(ARC_COLORS[i % len(ARC_COLORS)])
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(col, 6, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(
                QRectF(cx - rs, cy - rs, rs * 2, rs * 2),
                int((270 - a["from"] / 4) * 16),
                -d * 4,
            )

    def _week(self, p, cx, cy, r):
        self._ticks(p, cx, cy, r, 28, 4, 180)
        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        p.setPen(QColor(FG))
        for d in range(7):
            a = math.radians(90 + d * 360 / 7)
            x, y = cx + math.cos(a) * (r - 54), cy + math.sin(a) * (r - 54)
            p.drawText(QRectF(x - 20, y - 10, 40, 20), Qt.AlignCenter, WD[d])
        now = datetime.now()
        secs = (
            (now.weekday() * 24 + now.hour) * 3600
            + now.minute * 60
            + now.second
            + now.microsecond / 1e6
        )
        frac = secs / (7 * 86400)
        ln = self._ring(p, cx, cy, r, frac)
        self._hand(p, cx, cy, ln - 26, 180 + frac * 360)

    def _month(self, p, cx, cy, r):
        now = datetime.now()
        dim = calendar.monthrange(now.year, now.month)[1]
        day_deg = 360 / dim
        frac = (
            (now.day - 1) * 86400
            + now.hour * 3600
            + now.minute * 60
            + now.second
            + now.microsecond / 1e6
        ) / (dim * 86400)
        r0 = r - 30
        hi = QColor(ACC)
        hi.setAlpha(26)
        p.setPen(Qt.NoPen)
        p.setBrush(hi)
        p.drawPie(
            QRectF(cx - r0, cy - r0, r0 * 2, r0 * 2),
            int((90 - (now.day - 1) * day_deg) * 16),
            -int(round(day_deg * 16)),
        )
        self._ticks(p, cx, cy, r, dim, 5)
        p.setFont(QFont("Segoe UI", 8, QFont.DemiBold))
        fm = p.fontMetrics()
        for d in range(1, dim + 1):
            a = math.radians(-90 + (d - 0.5) * day_deg)
            x, y = cx + math.cos(a) * (r - 56), cy + math.sin(a) * (r - 56)
            col = ACC if d == now.day else (FG if d <= now.day else SUB)
            p.setPen(QColor(col))
            p.drawText(
                QRectF(x - 14, y - fm.height() / 2 - 1, 28, fm.height() + 2),
                Qt.AlignCenter,
                str(d),
            )
        ln = self._ring(p, cx, cy, r, frac, start=90)
        self._hand(p, cx, cy, ln - 26, frac * 360)

    def _year(self, p, cx, cy, r):
        now = datetime.now()
        y = now.year
        diy = 366 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 365
        elapsed = (
            (now.timetuple().tm_yday - 1) * 86400
            + now.hour * 3600
            + now.minute * 60
            + now.second
            + now.microsecond / 1e6
        )
        frac = elapsed / (diy * 86400)
        sec = min(23, int(frac * 24))
        r0 = r - 30
        hi = QColor(ACC)
        hi.setAlpha(26)
        p.setPen(Qt.NoPen)
        p.setBrush(hi)
        p.drawPie(
            QRectF(cx - r0, cy - r0, r0 * 2, r0 * 2),
            int((90 - sec * 15) * 16),
            -15 * 16,
        )
        self._ticks(p, cx, cy, r, 48, 2)
        p.setFont(QFont("Segoe UI", 8, QFont.DemiBold))
        fm = p.fontMetrics()
        for s in range(24):
            a = math.radians(-90 + (s + 0.5) * 15)
            x, y = cx + math.cos(a) * (r - 58), cy + math.sin(a) * (r - 58)
            col = ACC if s == sec else (FG if s < sec else SUB)
            p.setPen(QColor(col))
            p.drawText(
                QRectF(x - 14, y - fm.height() / 2 - 1, 28, fm.height() + 2),
                Qt.AlignCenter,
                f"{s // 2 + 1}{'上' if s % 2 == 0 else '下'}",
            )
        ln = self._ring(p, cx, cy, r, frac, start=90)
        self._hand(p, cx, cy, ln - 26, frac * 360)

    def _pick(self, pos):
        dx, dy = pos.x() - self.width() / 2, pos.y() - self.height() / 2
        if dx * dx + dy * dy < 1600:
            return None
        deg = math.degrees(math.atan2(dx, -dy)) % 360
        return max(5, min(MAX_MIN, int(round(deg / 360 * MAX_MIN / 5)) * 5))

    def mousePressEvent(self, e):
        if self.mode == "timer" and self.pickable and e.button() == Qt.LeftButton:
            m = self._pick(e.position())
            if m:
                self.picked.emit(m)

    def _arc_tip(self, pos):
        dx, dy = pos.x() - self.width() / 2, pos.y() - self.height() / 2
        rs = min(self.width(), self.height()) / 2 - 56
        if abs(math.hypot(dx, dy) - rs) > 12:
            return None
        deg = math.degrees(math.atan2(dx, -dy)) % 360
        m = (deg * 4 + 720) % 1440
        for i, a in enumerate(self.arcs):
            d = (a["to"] - a["from"]) % 1440
            if d and (m - a["from"]) % 1440 < d:
                nm = (a["name"].strip() or f"时段{i + 1}")[:6]
                return (
                    f"{nm} {a['from'] // 60:02d}:{a['from'] % 60:02d}"
                    f"–{a['to'] // 60:02d}:{a['to'] % 60:02d}"
                )
        return None

    def mouseMoveEvent(self, e):
        if self.mode == "timer" and self.pickable and e.buttons() & Qt.LeftButton:
            m = self._pick(e.position())
            if m:
                self.picked.emit(m)
        elif self.mode == "clock" and self.arcs_show and not e.buttons():
            tip = self._arc_tip(e.position())
            if tip:
                QToolTip.showText(e.globalPosition().toPoint(), tip, self)
            else:
                QToolTip.hideText()


class ArcDialog(QDialog):
    """自定义时段弧线：名称 + 起止时间，可增删多行。"""

    def __init__(self, parent, arcs):
        super().__init__(parent)
        self.setWindowTitle("自定义时段")
        self.setModal(True)
        self.setFixedWidth(420)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)
        self.rows = []
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(8)
        v.addLayout(self.rows_box)
        if arcs:
            for a in arcs:
                self._add_row(a["name"], a["from"], a["to"])
        else:
            self._add_row("睡眠", 23 * 60, 7 * 60)
        tip = QLabel("时间直接键入 4 位数字，如 0730 → 07:30")
        tip.setObjectName("hint")
        v.addWidget(tip)
        v.addStretch(1)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        add = QPushButton("+ 添加")
        add.setObjectName("mini")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self._add_clicked)
        ok = QPushButton("确定")
        ok.setProperty("primary", True)
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.setObjectName("mini")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        btns.addWidget(add)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        v.addLayout(btns)

    def _add_clicked(self):
        if len(self.rows) >= 12:
            return
        self._add_row("", 12 * 60, 13 * 60)

    def _add_row(self, name, f, t):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        ne = QLineEdit(name)
        ne.setPlaceholderText("名称")
        ne.setMaxLength(8)
        ne.setFixedWidth(100)
        t1 = self._time_edit(f)
        t2 = self._time_edit(t)
        dash = QLabel("–")
        dash.setObjectName("hint")
        de = QPushButton("✕")
        de.setObjectName("xdel")
        de.setFixedWidth(30)
        de.setCursor(Qt.PointingHandCursor)
        de.clicked.connect(lambda: self._del_row(row))
        h.addWidget(ne)
        h.addStretch(1)
        h.addWidget(t1)
        h.addWidget(dash)
        h.addWidget(t2)
        h.addWidget(de)
        self.rows_box.addWidget(row)
        self.rows.append({"name": ne, "t1": t1, "t2": t2, "w": row})

    def _time_edit(self, minutes):
        e = QLineEdit(f"{minutes // 60:02d}:{minutes % 60:02d}")
        e.setInputMask("00:00")
        e.setAlignment(Qt.AlignCenter)
        e.setFixedWidth(76)
        e.setProperty("min", max(0, min(1439, minutes)))
        e.editingFinished.connect(lambda: self._fix_time(e))
        return e

    @staticmethod
    def _time_val(e):
        txt = e.text()
        try:
            return min(int(txt[:2]), 23) * 60 + min(int(txt[3:]), 59)
        except ValueError:
            return e.property("min") or 0

    def _fix_time(self, e):
        v = self._time_val(e)
        e.setProperty("min", v)
        e.setText(f"{v // 60:02d}:{v % 60:02d}")

    def _del_row(self, w):
        for i, r in enumerate(self.rows):
            if r["w"] is w:
                r["w"].setParent(None)
                r["w"].deleteLater()
                del self.rows[i]
                return

    def arcs(self):
        out = []
        for r in self.rows:
            out.append(
                {
                    "name": r["name"].text().strip()[:8],
                    "from": self._time_val(r["t1"]),
                    "to": self._time_val(r["t2"]),
                }
            )
        return out


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.mode = "timer"
        self.state = "idle"
        self.total_ms = 25 * 60000
        self.remain_ms = self.total_ms
        self.used_ms = 0
        self.elapsed = QElapsedTimer()
        self.rings = 0

        self.setWindowTitle("时钟计时器")
        if IS_ANDROID:
            self.setMinimumSize(360, 560)
        else:
            self.setFixedSize(404, 648)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        seg = QWidget()
        seg.setObjectName("seg")
        seg.setAttribute(Qt.WA_StyledBackground, True)
        tabs = QHBoxLayout(seg)
        tabs.setContentsMargins(3, 3, 3, 3)
        tabs.setSpacing(3)
        self.tab_timer = QPushButton("⏱ 计时")
        self.tab_clock = QPushButton("🕒 时钟")
        for b in (self.tab_timer, self.tab_clock):
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
        self.tab_timer.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.tab_timer)
        grp.addButton(self.tab_clock)
        grp.setExclusive(True)
        self.tab_timer.clicked.connect(lambda: self.set_mode("timer"))
        self.tab_clock.clicked.connect(lambda: self.set_mode("clock"))
        tabs.addWidget(self.tab_timer, 1)
        tabs.addWidget(self.tab_clock, 1)
        head.addWidget(seg, 1)
        self.btn_gear = QPushButton("⚙")
        self.btn_gear.setObjectName("gear")
        self.btn_gear.setCursor(Qt.PointingHandCursor)
        self.btn_gear.setFixedSize(38, 38)
        self.btn_gear.setToolTip("设置")
        self.btn_gear.clicked.connect(self._open_menu)
        head.addWidget(self.btn_gear)
        root.addLayout(head)

        self.clock_sw = QWidget()
        cw = QVBoxLayout(self.clock_sw)
        cw.setContentsMargins(0, 0, 0, 0)
        cw.setSpacing(8)
        seg2 = QWidget()
        seg2.setObjectName("seg")
        seg2.setAttribute(Qt.WA_StyledBackground, True)
        srow = QHBoxLayout(seg2)
        srow.setContentsMargins(3, 3, 3, 3)
        srow.setSpacing(3)
        self.sw_day = QPushButton("24小时")
        self.sw_week = QPushButton("一周")
        self.sw_month = QPushButton("一月")
        self.sw_year = QPushButton("一年")
        for b in (self.sw_day, self.sw_week, self.sw_month, self.sw_year):
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
        self.sw_day.setChecked(True)
        sgrp = QButtonGroup(self)
        sgrp.addButton(self.sw_day)
        sgrp.addButton(self.sw_week)
        sgrp.addButton(self.sw_month)
        sgrp.addButton(self.sw_year)
        sgrp.setExclusive(True)
        self.sw_day.clicked.connect(lambda: self.set_clock_style("clock"))
        self.sw_week.clicked.connect(lambda: self.set_clock_style("week"))
        self.sw_month.clicked.connect(lambda: self.set_clock_style("month"))
        self.sw_year.clicked.connect(lambda: self.set_clock_style("year"))
        for b in (self.sw_day, self.sw_week, self.sw_month, self.sw_year):
            srow.addWidget(b, 1)
        cw.addWidget(seg2)

        self.settings = QSettings("PyApps", "TimerClock")
        self.arcs = self.load_arcs(self.settings)
        self.arcs_bar = QWidget()
        av = QHBoxLayout(self.arcs_bar)
        av.setContentsMargins(0, 0, 0, 0)
        av.setSpacing(6)
        self.cb_arcs = QCheckBox("时段弧线")
        self.btn_arcs = QPushButton("编辑时段")
        self.btn_arcs.setObjectName("mini")
        self.btn_arcs.setCursor(Qt.PointingHandCursor)
        self.cb_arcs.setChecked(
            self.settings.value(
                "arcs_on", self.settings.value("sleep_on", False, type=bool), type=bool
            )
        )
        av.addWidget(self.cb_arcs)
        av.addStretch(1)
        av.addWidget(self.btn_arcs)
        cw.addWidget(self.arcs_bar)
        self.clock_sw.setVisible(False)
        root.addWidget(self.clock_sw)

        self.dial = Dial()
        self.dial.picked.connect(self.set_minutes)
        root.addWidget(self.dial, 1)
        self.cb_arcs.toggled.connect(self._arcs_changed)
        self.btn_arcs.clicked.connect(self._edit_arcs)
        self._arcs_changed()

        self.big = QLabel("0:25:00")
        self.big.setObjectName("big")
        self.big.setAlignment(Qt.AlignCenter)
        root.addWidget(self.big)

        self.hint = QLabel("")
        self.hint.setObjectName("hint")
        self.hint.setAlignment(Qt.AlignCenter)
        root.addWidget(self.hint)

        self.controls = QWidget()
        cv = QVBoxLayout(self.controls)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(8)
        cust = QHBoxLayout()
        cust.setSpacing(4)
        self.ed_h = self._dur_edit(0, 23)
        self.ed_m = self._dur_edit(25, 59)
        lab_h = QLabel("时")
        lab_m = QLabel("分")
        lab_h.setObjectName("hint")
        lab_m.setObjectName("hint")
        self.btn_savep = QPushButton("保存")
        self.btn_savep.setObjectName("mini")
        self.btn_savep.setToolTip(
            "把当前时长存为预设（最多6个，长按删除）"
            if IS_ANDROID
            else "把当前时长存为预设（最多6个，右键删除）"
        )
        self.btn_savep.setCursor(Qt.PointingHandCursor)
        self.btn_savep.clicked.connect(self._save_preset)
        cust.addWidget(self.ed_h)
        cust.addWidget(lab_h)
        cust.addSpacing(8)
        cust.addWidget(self.ed_m)
        cust.addWidget(lab_m)
        cust.addStretch(1)
        cust.addWidget(self.btn_savep)
        cv.addLayout(cust)
        self.presets = []
        self._lp_btn = None
        self._lp_m = None
        self._lp_t = QTimer(self, singleShot=True, interval=800, timeout=self._lp_fire)
        self.prow = QHBoxLayout()
        self.prow.setSpacing(5)
        cv.addLayout(self.prow)
        self.user_presets = self._load_presets()
        self._rebuild_presets()
        brow = QHBoxLayout()
        brow.setSpacing(8)
        self.btn_main = QPushButton("开始")
        self.btn_main.setProperty("primary", True)
        self.btn_main.setCursor(Qt.PointingHandCursor)
        self.btn_main.clicked.connect(self.toggle)
        self.btn_reset = QPushButton("重置")
        self.btn_reset.setProperty("ghost", True)
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self.reset)
        self.auto = QCheckBox("到点自动重复")
        brow.addWidget(self.btn_main)
        brow.addWidget(self.btn_reset)
        brow.addWidget(self.auto)
        cv.addLayout(brow)
        root.addWidget(self.controls)

        self.setStyleSheet(
            f"""
            QWidget {{ background:{BG}; color:{FG}; font-size:14px;
                       font-family:'Segoe UI Variable Text','Segoe UI','Microsoft YaHei UI'; }}
            QLabel#big {{ font-size:42px; font-weight:800; letter-spacing:2px; }}
            QLabel#hint {{ color:{SUB}; font-size:12px; letter-spacing:0.5px; }}
            QWidget#seg {{ background:#12161f; border:1px solid #232b39; border-radius:12px; }}
            QWidget#seg QPushButton {{ background:transparent; border:none; border-radius:9px;
                                       color:{SUB}; padding:6px 10px; font-weight:600; }}
            QWidget#seg QPushButton:hover {{ color:{FG}; }}
            QWidget#seg QPushButton:checked {{ background:#28324a; color:{FG}; font-weight:700; }}
            QPushButton#gear {{ background:{SURF}; border:1px solid {BORD}; border-radius:12px;
                                color:#c6cede; font-size:16px; }}
            QPushButton#gear:hover {{ background:#1d2430; border-color:#3a465c; color:{FG}; }}
            QPushButton {{ background:{SURF}; border:1px solid {BORD}; border-radius:10px;
                           padding:6px 12px; color:#c6cede; font-weight:600; }}
            QPushButton:hover {{ background:#1c2330; color:{FG}; border-color:#3a465c; }}
            QPushButton[ghost="true"] {{ background:{SURF}; border:1px solid {BORD};
                                         border-radius:12px; color:#c6cede;
                                         padding:0 18px; min-height:42px; }}
            QPushButton[ghost="true"]:hover {{ background:#1c2330; border-color:#3a465c;
                                               color:{FG}; }}
            QPushButton[primary="true"] {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                                          stop:0 #3ee6a0, stop:1 #17b978);
                                          color:#06281a; border:none; border-radius:12px;
                                          font-size:15px; font-weight:800;
                                          padding:0 24px; min-height:42px; }}
            QPushButton[primary="true"]:hover {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                                                stop:0 #52efac, stop:1 #1fca86); }}
            QPushButton[primary="true"]:pressed {{ background:#14a86f; }}
            QPushButton#mini {{ background:{SURF}; border:1px solid {BORD}; border-radius:10px;
                                padding:6px 14px; color:#aeb8c8; font-weight:600; font-size:13px; }}
            QPushButton#mini:hover {{ background:#1c2330; color:{FG}; border-color:#3a465c; }}
            QPushButton#chip {{ background:#141922; border:1px solid {BORD}; border-radius:999px;
                                padding:5px 11px; color:#aeb8c8; font-size:13px; }}
            QPushButton#chip:hover {{ background:#1a2029; color:{FG}; border-color:#3a465c; }}
            QPushButton#chip:checked {{ background:#24363d; border-color:{ACC};
                                        color:#4ee6a5; font-weight:700; }}
            QPushButton#xdel {{ background:transparent; border:1px solid {BORD};
                                border-radius:8px; color:{SUB}; padding:0; }}
            QPushButton#xdel:hover {{ color:{RED}; border-color:{RED}; }}
            QPushButton:disabled {{ color:#5a6579; background:#12161f; border-color:#202836; }}
            QLineEdit {{ background:{SURF}; border:1px solid {BORD}; border-radius:10px;
                         padding:5px 8px; color:{FG}; selection-background-color:#2b5df0; }}
            QLineEdit:focus {{ border-color:{ACC}; background:#181f2a; }}
            QCheckBox {{ spacing:6px; color:{SUB}; font-size:13px; background:transparent; }}
            QCheckBox:hover {{ color:{FG}; }}
            QCheckBox::indicator {{ width:16px; height:16px; border:1px solid #3a4454;
                                    border-radius:5px; background:#141922; }}
            QCheckBox::indicator:hover {{ border-color:#4a5870; }}
            QCheckBox::indicator:checked {{ background:{ACC}; border-color:{ACC}; }}
            QMenu {{ background:#161b24; border:1px solid {BORD}; border-radius:10px; padding:6px; }}
            QMenu::item {{ padding:7px 26px 7px 10px; border-radius:7px; color:#c6cede; }}
            QMenu::item:selected {{ background:#28324a; color:{FG}; }}
            QMenu::indicator {{ width:16px; height:16px; border:1px solid #3a4454;
                                border-radius:5px; background:#141922; margin-left:4px; }}
            QMenu::indicator:checked {{ background:{ACC}; border-color:{ACC}; }}
            QMenu::separator {{ height:1px; background:#232b39; margin:5px 8px; }}
            QToolTip {{ background:#1c2330; color:{FG}; border:1px solid #3a465c;
                        padding:5px 9px; font-size:12px; }}
        """
        )

        self.setWindowIcon(make_icon())

        # 托盘 + 设置菜单（托盘右键与 ⚙ 共用）
        self.menu = QMenu()
        a_open = self.menu.addAction("打开主窗口")
        a_open.triggered.connect(self._restore)
        self.menu.addSeparator()
        self.act_close_tray = self.menu.addAction("关闭(X)最小化到托盘")
        self.act_close_tray.setCheckable(True)
        self.act_close_tray.setChecked(self.settings.value("close_tray", True, bool))
        self.act_close_tray.toggled.connect(
            lambda v: self.settings.setValue("close_tray", v)
        )
        self.act_sound = self.menu.addAction("到点提示音")
        self.act_sound.setCheckable(True)
        self.act_sound.setChecked(self.settings.value("sound_on", True, bool))
        self.act_sound.toggled.connect(lambda v: self.settings.setValue("sound_on", v))
        self.menu.addSeparator()
        a_quit = self.menu.addAction("退出程序")
        a_quit.triggered.connect(self._quit)

        self._tray_tip_shown = False
        if not IS_ANDROID:
            self.tray = QSystemTrayIcon(make_icon(), self)
            self.tray.setToolTip("时钟计时器")
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(self._tray_activated)
            self.tray.show()

        self.blink_t = QTimer(self, interval=450, timeout=self._blink)
        self.ring_t = QTimer(self, interval=1200, timeout=self._ring)
        self.tick_t = QTimer(self, interval=100, timeout=self._tick)
        self.tick_t.start()
        style = self.settings.value("clock_style", "", str) or ""
        if style not in ("clock", "week", "month", "year"):
            style = (
                "week"
                if self.settings.value("clock_week", False, type=bool)
                else "clock"
            )
        self.clock_style = style
        btn = {
            "clock": self.sw_day,
            "week": self.sw_week,
            "month": self.sw_month,
            "year": self.sw_year,
        }[style]
        btn.setChecked(True)
        if self.settings.value("mode", "timer") == "clock":
            self.tab_clock.setChecked(True)
            self.set_mode("clock")
        self._sync()
        self._tick()

    def set_mode(self, mode):
        if mode == self.mode:
            return
        self.mode = mode
        if mode == "timer":
            self.dial.mode = "timer"
        else:
            self.dial.mode = self.clock_style
        self.controls.setVisible(mode == "timer")
        self.clock_sw.setVisible(mode == "clock")
        self.arcs_bar.setVisible(mode == "clock" and self.clock_style == "clock")
        self.settings.setValue("mode", mode)
        self._tick()
        self._sync()

    def set_clock_style(self, style):
        self.clock_style = style
        if self.mode == "clock":
            self.dial.mode = style
        self.arcs_bar.setVisible(self.mode == "clock" and style == "clock")
        self.settings.setValue("clock_style", style)
        self._tick()

    @staticmethod
    def load_arcs(settings):
        raw = settings.value("arcs", "", str) or ""
        if raw:
            try:
                out = [
                    {
                        "name": str(a.get("name", ""))[:8],
                        "from": int(a.get("from", 0)) % 1440,
                        "to": int(a.get("to", 0)) % 1440,
                    }
                    for a in json.loads(raw)
                ]
                if out:
                    return out
            except Exception:
                pass
        if settings.contains("sleep_from"):
            return [
                {
                    "name": "睡眠",
                    "from": settings.value("sleep_from", 1380, type=int) % 1440,
                    "to": settings.value("sleep_to", 420, type=int) % 1440,
                }
            ]
        return [{"name": "睡眠", "from": 23 * 60, "to": 7 * 60}]

    def _arcs_changed(self):
        self.dial.arcs_show = self.cb_arcs.isChecked()
        self.dial.arcs = self.arcs
        self.settings.setValue("arcs_on", self.cb_arcs.isChecked())
        self.settings.setValue("arcs", json.dumps(self.arcs, ensure_ascii=False))
        self.dial.update()

    def _edit_arcs(self):
        dlg = ArcDialog(self, self.arcs)
        if dlg.exec() == QDialog.Accepted:
            self.arcs = dlg.arcs()
            self._arcs_changed()

    def _current_arc_name(self, m):
        for i, a in enumerate(self.arcs):
            d = (a["to"] - a["from"]) % 1440
            if d and (m - a["from"]) % 1440 < d:
                return a["name"] or f"时段{i + 1}"
        return ""

    def toggle(self):
        if self.state == "running":
            self.state = "paused"
        elif self.state == "paused":
            self.elapsed.restart()
            self.state = "running"
        else:
            self._go()
        self._sync()

    def _go(self):
        self._stop_alarm()
        if self.state in ("idle", "done"):
            self.remain_ms = self.total_ms
        self.used_ms = self.total_ms - self.remain_ms
        self.elapsed.start()
        self.state = "running"

    def reset(self):
        self._stop_alarm()
        self.state = "idle"
        self.remain_ms = self.total_ms
        self.used_ms = 0
        self._sync()

    def set_minutes(self, m):
        self._stop_alarm()
        self.total_ms = m * 60000
        self.remain_ms = self.total_ms
        self.used_ms = 0
        if self.state != "idle":
            self.elapsed.start()
            self.state = "running"
        self._sync()

    def _dur_edit(self, v, hi):
        e = QLineEdit(f"{v:02d}")
        e.setInputMask("00")
        e.setAlignment(Qt.AlignCenter)
        e.setFixedWidth(42)
        e.setProperty("v", v)
        e.setProperty("hi", hi)
        e.editingFinished.connect(lambda: self._dur_done(e))
        return e

    def _dur_done(self, e):
        txt = e.text().strip()
        v = int(txt) if txt.isdigit() else e.property("v")
        v = max(0, min(e.property("hi"), v))
        e.setProperty("v", v)
        e.setText(f"{v:02d}")
        self._dur_changed()

    def _dur_changed(self):
        self.set_minutes(self.ed_h.property("v") * 60 + self.ed_m.property("v"))

    def _load_presets(self):
        try:
            v = json.loads(self.settings.value("presets", "", str) or "[]")
            v = sorted({int(x) for x in v if 0 < int(x) <= 1439})
            if v:
                return v
        except Exception:
            pass
        return [10, 25, 45, 60, 120, 240]

    def _rebuild_presets(self):
        while self.presets:
            b = self.presets.pop()
            b.setParent(None)
            b.deleteLater()
        for m in self.user_presets:
            h, r = divmod(m, 60)
            b = QPushButton(f"{h}时" if not r else f"{m}分")
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setProperty("ms", m)
            b.setToolTip("长按删除" if IS_ANDROID else fmt_min(m))
            b.setCursor(Qt.PointingHandCursor)
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(
                lambda _p, mm=m: self._del_preset(mm)
            )
            b.clicked.connect(
                lambda _, mm=m, bb=b: None if bb.property("lp") else self.set_minutes(mm)
            )
            if IS_ANDROID:
                b.pressed.connect(lambda bb=b, mm=m: self._lp_start(bb, mm))
                b.released.connect(self._lp_cancel)
            self.prow.addWidget(b)
            self.presets.append(b)
        if hasattr(self, "btn_main"):
            self._sync()

    def _save_preset(self):
        m = self.total_ms // 60000
        if m in self.user_presets:
            QToolTip.showText(self.btn_savep.mapToGlobal(QPoint(0, -30)), "已有该预设")
            return
        if len(self.user_presets) >= 6:
            QToolTip.showText(
                self.btn_savep.mapToGlobal(QPoint(0, -30)),
                "最多6个，长按删除后再存" if IS_ANDROID else "最多6个，右键删除后再存",
            )
            return
        self.user_presets.append(m)
        self.user_presets.sort()
        self.settings.setValue("presets", json.dumps(self.user_presets))
        self._rebuild_presets()

    def _del_preset(self, m):
        self.user_presets.remove(m)
        self.settings.setValue("presets", json.dumps(self.user_presets))
        self._rebuild_presets()

    def _lp_start(self, b, m):
        self._lp_btn = b
        self._lp_m = m
        self._lp_t.start()

    def _lp_cancel(self):
        self._lp_t.stop()
        self._lp_btn = None

    def _lp_fire(self):
        b, m = self._lp_btn, self._lp_m
        self._lp_btn = None
        if b is None or m not in self.user_presets:
            return
        try:
            b.setProperty("lp", True)
        except RuntimeError:
            pass
        self._del_preset(m)

    def _tick(self):
        if self.mode == "clock":
            now = datetime.now()
            self.big.setText(now.strftime("%H:%M:%S"))
            self.big.setStyleSheet("")
            if self.dial.mode == "week":
                eh = now.weekday() * 24 + now.hour + now.minute / 60
                sec = int(eh // 6) % 28
                hr = (sec % 4) * 6
                self.hint.setText(
                    f"{WD[sec // 4]} {hr}时–{hr + 6}时"
                    f" · 本周已过{eh / 168 * 100:.0f}%"
                )
            elif self.dial.mode == "month":
                dim = calendar.monthrange(now.year, now.month)[1]
                pct = (
                    (
                        (now.day - 1) * 86400
                        + now.hour * 3600
                        + now.minute * 60
                        + now.second
                    )
                    / (dim * 86400)
                    * 100
                )
                self.hint.setText(
                    f"{now.year}年{now.month}月{now.day}日 · {WD[now.weekday()]}"
                    f" · 本月已过{pct:.0f}%"
                )
            elif self.dial.mode == "year":
                y = now.year
                diy = 366 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 365
                frac = (
                    (now.timetuple().tm_yday - 1) * 86400
                    + now.hour * 3600
                    + now.minute * 60
                    + now.second
                ) / (diy * 86400)
                sec = min(23, int(frac * 24))
                self.hint.setText(
                    f"{y}年{now.month}月{now.day}日 · 第{sec + 1}节"
                    f"({sec // 2 + 1}月{'上' if sec % 2 == 0 else '下'}半月)"
                    f" · 一年已过{frac * 100:.0f}%"
                )
            else:
                txt = f"{now.year}年{now.month}月{now.day}日 · {WD[now.weekday()]}"
                if self.dial.arcs_show:
                    nm = self._current_arc_name(now.hour * 60 + now.minute)
                    if nm:
                        txt += " · " + nm
                self.hint.setText(txt)
        else:
            if self.state == "running":
                self.remain_ms = max(
                    0, self.total_ms - self.used_ms - self.elapsed.elapsed()
                )
                if self.remain_ms == 0:
                    self._finish()
            if self.state == "done":
                self.big.setText("时间到")
                self.big.setStyleSheet(f"color:{RED};")
            else:
                s = self.remain_ms // 1000
                self.big.setText(f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}")
                red = self.state == "running" and self.remain_ms <= 60000
                self.big.setStyleSheet(f"color:{RED};" if red else "")
            self.hint.setText("点击表盘设定（5分步进，一圈最多4小时）")
            frac = 0 if not self.total_ms else 1 - self.remain_ms / self.total_ms
            self.dial.fraction = frac
            self.dial.warn = self.state == "running" and self.remain_ms <= 60000
        self.dial.update()

    def _finish(self):
        self.state = "done"
        self.dial.blink = True
        self.dial.blink_on = True
        self.rings = 3
        if self.act_sound.isChecked():
            threading.Thread(target=beep_seq, daemon=True).start()
        self.blink_t.start()
        self.ring_t.start()
        if self.auto.isChecked():
            QTimer.singleShot(2500, self._auto_restart)

    def _auto_restart(self):
        if self.state == "done":
            self._go()
            self._sync()

    def _ring(self):
        if self.act_sound.isChecked():
            threading.Thread(target=beep_seq, daemon=True).start()
        self.rings -= 1
        if self.rings <= 0:
            self.ring_t.stop()

    def _blink(self):
        self.dial.blink_on = not self.dial.blink_on
        self.dial.update()

    def _stop_alarm(self):
        self.ring_t.stop()
        self.blink_t.stop()
        self.dial.blink = False
        self.dial.blink_on = True

    def _sync(self):
        self.btn_main.setText(
            {"idle": "开始", "running": "暂停", "paused": "继续", "done": "再来一轮"}[
                self.state
            ]
        )
        self.btn_reset.setEnabled(self.state != "idle")
        self.dial.pickable = self.state == "idle" and self.mode == "timer"
        m = self.total_ms // 60000
        for e, val in ((self.ed_h, m // 60), (self.ed_m, m % 60)):
            e.setProperty("v", val)
            if not e.hasFocus():
                e.setText(f"{val:02d}")
        for b in self.presets:
            b.setChecked(self.total_ms == b.property("ms") * 60000)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space and self.mode == "timer":
            self.toggle()
        else:
            super().keyPressEvent(e)

    def _open_menu(self):
        self.menu.exec(self.btn_gear.mapToGlobal(QPoint(0, self.btn_gear.height() + 4)))

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._restore()

    def _restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self):
        if not IS_ANDROID:
            self.tray.hide()
        QApplication.quit()

    def closeEvent(self, e):
        if not IS_ANDROID and self.act_close_tray.isChecked():
            e.ignore()
            self.hide()
            if not self._tray_tip_shown:
                self._tray_tip_shown = True
                self.tray.showMessage(
                    "时钟计时器", "已最小化到托盘，点击图标恢复窗口", msecs=2000
                )
        else:
            e.accept()


def main():
    app = QApplication(sys.argv)
    w = App()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
