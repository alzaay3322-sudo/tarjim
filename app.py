"""ترجمان - مترجم ودبلج ألعاب فوري (مجاني). Windows + Python 3.10+"""
import sys, os, asyncio, tempfile, uuid
import numpy as np
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QFont
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QComboBox, QPushButton, QFrame, QSlider)

VOICES = {"خليجي": "ar-SA-HamedNeural", "مصري": "ar-EG-ShakirNeural",
          "شامي": "ar-SY-AmanyNeural", "فصحى": "ar-AE-HamdanNeural"}
MODES = ["صوتي + كتابي", "كتابي فقط", "صوتي فقط", "صوت اللعبة الأصلي + ترجمة مكتوبة"]
SRC = {"تلقائي": None, "English": "en", "日本語": "ja", "한국어": "ko", "中文": "zh",
       "Español": "es", "Français": "fr", "Deutsch": "de", "Русский": "ru"}

STYLE = """
* { font-family: 'Segoe UI', 'Tajawal'; color: #ECE8F5; }
QWidget#root { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0B0B14, stop:1 #17102B); }
QFrame#card { background: rgba(255,255,255,0.05); border: 1px solid rgba(212,175,95,0.25); border-radius: 16px; }
QLabel#title { font-size: 30px; font-weight: 700; color: #D4AF5F; }
QLabel#sub { color: #9C97B5; font-size: 13px; }
QLabel#h { color: #D4AF5F; font-size: 12px; font-weight: 600; }
QComboBox { background: #1E1836; border: 1px solid #3A2F66; border-radius: 10px; padding: 8px 12px; min-height: 22px; }
QComboBox QAbstractItemView { background: #1E1836; selection-background-color: #5B3FD0; }
QPushButton#go { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #D4AF5F, stop:1 #F0D58A);
  color: #1A1204; font-size: 17px; font-weight: 700; border-radius: 14px; padding: 14px; }
QPushButton#go:hover { background: #F5DE9A; }
QPushButton#stop { background: #8B2A3F; font-size: 17px; font-weight: 700; border-radius: 14px; padding: 14px; }
QSlider::groove:horizontal { height: 6px; background: #2C2350; border-radius: 3px; }
QSlider::handle:horizontal { background: #D4AF5F; width: 16px; margin: -5px 0; border-radius: 8px; }
"""


class Worker(QThread):
    """التقاط صوت اللعبة -> Whisper -> ترجمة. يرسل النتائج كإشارات (مخرجات مستقلة)."""
    result = Signal(str, str)   # الأصل، الترجمة
    status = Signal(str)

    def __init__(self, src):
        super().__init__()
        self.src, self.running, self.muted = src, True, False

    def _translate(self, text, lang):
        import argostranslate.translate as t
        if lang != "en":
            text = t.translate(text, lang, "en")
        return t.translate(text, "en", "ar")

    def _ensure_packs(self, lang):
        import argostranslate.package as pkg
        pkg.update_package_index()
        have = {(p.from_code, p.to_code) for p in pkg.get_installed_packages()}
        for pair in {(lang, "en"), ("en", "ar")} if lang != "en" else {("en", "ar")}:
            if pair not in have:
                self.status.emit(f"تحميل حزمة الترجمة {pair[0]}→{pair[1]} (مرة وحدة)...")
                for p in pkg.get_available_packages():
                    if (p.from_code, p.to_code) == pair:
                        pkg.install_from_path(p.download()); break

    def run(self):
        try:
            import pyaudiowpatch as pa
            from faster_whisper import WhisperModel
            self.status.emit("تحميل نموذج الصوت (أول مرة يأخذ وقت)...")
            model = WhisperModel("small", compute_type="int8")
            if self.src:
                self._ensure_packs(self.src)
            p = pa.PyAudio()
            api = p.get_host_api_info_by_type(pa.paWASAPI)
            dev = p.get_device_info_by_index(api["defaultOutputDevice"])
            if not dev.get("isLoopbackDevice"):
                for lb in p.get_loopback_device_info_generator():
                    if dev["name"] in lb["name"]:
                        dev = lb; break
            rate, ch = int(dev["defaultSampleRate"]), dev["maxInputChannels"]
            stream = p.open(format=pa.paInt16, channels=ch, rate=rate, input=True,
                            input_device_index=dev["index"], frames_per_buffer=2048)
            self.status.emit("🎧 جاهز... شغّل اللعبة")
            buf, silent, speaking = [], 0, False
            while self.running:
                raw = stream.read(2048, exception_on_overflow=False)
                if self.muted:           # لا نلتقط صوت الدبلجة نفسها
                    buf, speaking, silent = [], False, 0
                    continue
                x = np.frombuffer(raw, np.int16).reshape(-1, ch).mean(1) / 32768.0
                loud = np.sqrt((x ** 2).mean()) > 0.01
                if loud:
                    speaking, silent = True, 0
                elif speaking:
                    silent += 1
                if speaking:
                    buf.append(x)
                dur = len(buf) * 2048 / rate
                if speaking and (silent * 2048 / rate > 0.7 or dur > 12):
                    if dur > 0.8:
                        audio = np.concatenate(buf)
                        audio = np.interp(np.linspace(0, len(audio), int(len(audio) * 16000 / rate)),
                                          np.arange(len(audio)), audio).astype(np.float32)
                        segs, info = model.transcribe(audio, language=self.src, vad_filter=True)
                        text = " ".join(s.text for s in segs).strip()
                        if text:
                            lang = info.language
                            if not self.src and lang != "ar":
                                self._ensure_packs(lang)
                            ar = text if lang == "ar" else self._translate(text, lang)
                            self.result.emit(text, ar)
                    buf, speaking, silent = [], False, 0
        except Exception as e:
            self.status.emit(f"خطأ: {e}")


class TTSWorker(QThread):
    done = Signal(str)

    def __init__(self, text, voice, rate):
        super().__init__()
        self.text, self.voice, self.rate = text, voice, rate

    def run(self):
        import edge_tts
        path = os.path.join(tempfile.gettempdir(), f"tarjim_{uuid.uuid4().hex}.mp3")
        asyncio.run(edge_tts.Communicate(self.text, self.voice, rate=self.rate).save(path))
        self.done.emit(path)


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.label = QLabel("", self)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setLayoutDirection(Qt.RightToLeft)
        self.label.setStyleSheet("background: rgba(10,8,20,200); color: white; padding: 14px 24px;"
                                 "border-radius: 14px; border: 1px solid rgba(212,175,95,120);")
        self.label.setFont(QFont("Segoe UI", 20, QFont.DemiBold))
        lay = QVBoxLayout(self); lay.addWidget(self.label)
        self.hide()
        self.timer = None

    def show_text(self, text):
        from PySide6.QtCore import QTimer
        scr = QApplication.primaryScreen().geometry()
        w = int(scr.width() * 0.6)
        self.setGeometry((scr.width() - w) // 2, scr.height() - 220, w, 160)
        self.label.setText(text)
        self.show()
        if self.timer: self.timer.stop()
        self.timer = QTimer(self, singleShot=True, interval=max(3000, len(text) * 70))
        self.timer.timeout.connect(self.hide); self.timer.start()


class Main(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root"); self.setStyleSheet(STYLE)
        self.setWindowTitle("ترجمان"); self.resize(560, 700)
        self.setLayoutDirection(Qt.RightToLeft)
        self.overlay, self.worker = Overlay(), None
        self.player = QMediaPlayer(self); self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.mediaStatusChanged.connect(self._media)

        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 24); root.setSpacing(14)
        t = QLabel("ترجمان"); t.setObjectName("title")
        s = QLabel("دبلجة وترجمة الألعاب فورياً · مجاني بالكامل"); s.setObjectName("sub")
        root.addWidget(t); root.addWidget(s)

        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card); cl.setContentsMargins(20, 18, 20, 18); cl.setSpacing(8)
        self.mode = self._combo(cl, "وضع العرض", MODES)
        self.dialect = self._combo(cl, "لهجة الصوت", list(VOICES))
        self.src = self._combo(cl, "لغة اللعبة", list(SRC))
        h = QLabel("سرعة النطق"); h.setObjectName("h"); cl.addWidget(h)
        self.speed = QSlider(Qt.Horizontal); self.speed.setRange(-30, 50); self.speed.setValue(10)
        cl.addWidget(self.speed)
        h = QLabel("مستوى صوت الدبلجة"); h.setObjectName("h"); cl.addWidget(h)
        self.vol = QSlider(Qt.Horizontal); self.vol.setRange(0, 100); self.vol.setValue(90)
        cl.addWidget(self.vol)
        root.addWidget(card)

        self.go = QPushButton("▶  ابدأ الترجمة"); self.go.setObjectName("go")
        self.go.clicked.connect(self.toggle); root.addWidget(self.go)

        self.status = QLabel("جاهز"); self.status.setObjectName("sub"); root.addWidget(self.status)
        self.log = QLabel(""); self.log.setWordWrap(True)
        self.log.setStyleSheet("font-size:15px;")
        root.addWidget(self.log); root.addStretch()
        tip = QLabel("نصيحة: شغّل اللعبة بوضع Borderless Windowed عشان يظهر النص فوقها.")
        tip.setObjectName("sub"); tip.setWordWrap(True); root.addWidget(tip)

    def _combo(self, lay, label, items):
        h = QLabel(label); h.setObjectName("h"); lay.addWidget(h)
        c = QComboBox(); c.addItems(items); lay.addWidget(c); return c

    def toggle(self):
        if self.worker and self.worker.isRunning():
            self.worker.running = False; self.worker = None
            self.go.setText("▶  ابدأ الترجمة"); self.go.setObjectName("go")
            self.setStyleSheet(STYLE); self.status.setText("متوقف"); return
        self.worker = Worker(SRC[self.src.currentText()])
        self.worker.result.connect(self.on_result)
        self.worker.status.connect(self.status.setText)
        self.worker.start()
        self.go.setText("■  إيقاف"); self.go.setObjectName("stop"); self.setStyleSheet(STYLE)

    # ---- المخرجات (كل مخرج مستقل) ----
    def on_result(self, orig, ar):
        mode = self.mode.currentIndex()
        self.log.setText(f"{orig}\n\n{ar}")
        if mode in (0, 1, 3):
            self.overlay.show_text(ar)
        if mode in (0, 2):
            self.worker.muted = True
            r = self.speed.value()
            tw = TTSWorker(ar, VOICES[self.dialect.currentText()], f"{r:+d}%")
            tw.done.connect(self.play); tw.finished.connect(tw.deleteLater)
            self._tw = tw; tw.start()

    def play(self, path):
        self.audio.setVolume(self.vol.value() / 100)
        self.player.setSource(QUrl.fromLocalFile(path)); self.player.play()

    def _media(self, st):
        if st == QMediaPlayer.EndOfMedia and self.worker:
            self.worker.muted = False

    def closeEvent(self, e):
        if self.worker: self.worker.running = False
        e.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Main(); w.show()
    sys.exit(app.exec())
