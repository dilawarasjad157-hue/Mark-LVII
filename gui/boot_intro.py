"""gui/boot_intro.py — the opening sequence.

Plays assets/boot_intro.mp4 (picture and sound) over the window when the HUD
first appears: the flare, the rings assembling, the J.A.R.V.I.S title, the
monochrome ring core and its readouts, and the eyes lighting up. When it ends —
or on a click, Esc or Space — it fades out and the HUD's own rings run their
start-up animation, so the intro hands over to the live interface.

The microphone is muted while it plays (the soundtrack must not be heard as
speech) and put back afterwards. Everything is optional: no multimedia plugin,
no file, an error while playing, or "boot_intro": false in config/api_keys.json
(or the JARVIS_NO_INTRO environment variable) and the app simply starts as it
always did.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QPropertyAnimation, Qt, QUrl, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from gui.theme import BASE_DIR, HAVE_VIDEO, _read_full_config

INTRO_FILE = BASE_DIR / "assets" / "boot_intro.mp4"


def intro_enabled() -> bool:
    if os.environ.get("JARVIS_NO_INTRO"):
        return False
    if not HAVE_VIDEO or not INTRO_FILE.exists():
        return False
    return bool(_read_full_config().get("boot_intro", True))


class BootIntro(QWidget):
    def __init__(self, win, path: Path = INTRO_FILE):
        host = win.centralWidget()
        super().__init__(host)
        from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PyQt6.QtMultimediaWidgets import QVideoWidget

        self._win, self._host = win, host
        self._done = False
        self._we_muted = False
        self.setStyleSheet("background: #000000;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._video = QVideoWidget(self)
        self._video.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(0.85)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video)
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.errorOccurred.connect(lambda *_a: self._finish())

        self._hint = QLabel("CLICK  /  ESC  TO SKIP", self)
        self._hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        f = QFont()
        f.setPixelSize(10)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        self._hint.setFont(f)
        self._hint.setStyleSheet("color: rgba(160,210,230,150); background: transparent;")
        self._hint.adjustSize()

        host.installEventFilter(self)
        self._fit()
        self.show()
        self.raise_()
        self.setFocus()

        try:
            if not win._muted:
                win._set_muted(True, "Intro playing.")
                self._we_muted = True
        except Exception:
            pass

        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()
        # Whatever happens, the intro cannot outlive its own length by much.
        QTimer.singleShot(45000, self._finish)

    # ── layout ───────────────────────────────────────────────────────────────
    def _fit(self) -> None:
        r = self._host.rect()
        self.setGeometry(r)
        self._video.setGeometry(self.rect())
        self._hint.move(self.width() - self._hint.width() - 18,
                        self.height() - self._hint.height() - 14)
        self._hint.raise_()

    def eventFilter(self, obj, ev):
        if obj is self._host and ev.type() == QEvent.Type.Resize:
            self._fit()
        return False

    # ── ending ───────────────────────────────────────────────────────────────
    def _on_status(self, status) -> None:
        try:
            from PyQt6.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                self._finish()
            elif status == QMediaPlayer.MediaStatus.InvalidMedia:
                self._finish(fade=False)
        except Exception:
            self._finish(fade=False)

    def mousePressEvent(self, e):
        self._finish()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Space, Qt.Key.Key_Return):
            self._finish()
        else:
            super().keyPressEvent(e)

    def _finish(self, fade: bool = True) -> None:
        if self._done:
            return
        self._done = True
        try:
            self._host.removeEventFilter(self)
        except Exception:
            pass
        if self._we_muted:
            try:
                self._win._set_muted(False)
            except Exception:
                pass
        # restart the HUD's own ring animation so the intro hands over to it
        try:
            fx = getattr(self._win.hud, "_fx", None)
            if fx is not None:
                fx._t0 = time.time()
        except Exception:
            pass
        if not fade:
            self._teardown()
            return
        try:
            eff = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(eff)
            self._anim = QPropertyAnimation(eff, b"opacity", self)
            self._anim.setDuration(600)
            self._anim.setStartValue(1.0)
            self._anim.setEndValue(0.0)
            self._anim.finished.connect(self._teardown)
            self._anim.start()
        except Exception:
            self._teardown()

    def _teardown(self) -> None:
        try:
            self._player.stop()
            self._player.setVideoOutput(None)
        except Exception:
            pass
        self.hide()
        self.deleteLater()


def play_intro(win):
    """Start the intro over `win` if it is enabled and can run. Never raises."""
    try:
        if intro_enabled():
            return BootIntro(win)
    except Exception as e:               # noqa: BLE001 — cosmetic, never fatal
        print(f"[Intro] skipped ({e})")
    return None
