import sys
import os
import asyncio
import tempfile
import shutil
import whisper
import edge_tts
import time
from deep_translator import GoogleTranslator
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                             QPushButton, QLabel, QFileDialog, QProgressBar)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import QUrl, Qt, QThread, pyqtSignal, QTimer

class FinalTranslatorWorker(QThread):
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)

    def __init__(self, video_path, temp_dir):
        super().__init__()
        self.video_path = video_path
        self.temp_dir = temp_dir
        self.voice_map = {}

    def run(self):
        try:
            self.status_signal.emit("1/3: AI model yuklanmoqda...")
            model = whisper.load_model("base")
            
            self.status_signal.emit("2/3: Video tahlil qilinmoqda (Whisper)...")
            result = model.transcribe(self.video_path)
            segments = result.get('segments', [])
            total = len(segments)

            translator = GoogleTranslator(source='auto', target='uz')

            self.status_signal.emit(f"3/3: {total} ta gap tarjima qilinmoqda...")
            for i, segment in enumerate(segments):
                try:
                    text = segment['text'].strip()
                    if not text: continue

                    try:
                        uz_text = translator.translate(text)
                        time.sleep(0.1) 
                    except:
                        uz_text = text

                    start_ms = int(segment['start'] * 1000)
                    voice_path = os.path.join(self.temp_dir, f"v_{start_ms}.mp3")
                    
                    asyncio.run(self.generate_voice(uz_text, voice_path))
                    self.voice_map[start_ms] = voice_path

                except Exception as e:
                    print(f"Segment xatosi: {e}")
                
                self.progress_signal.emit(int(((i + 1) / total) * 100))

            self.status_signal.emit("Tayyor! Dublyaj rejimi ishga tushdi.")
            self.finished_signal.emit(self.voice_map)

        except Exception as e:
            self.status_signal.emit(f"Kritik xato: {str(e)}")

    async def generate_voice(self, text, path):
        communicate = edge_tts.Communicate(text, "uz-UZ-MadinaNeural")
        await communicate.save(path)

class DubbingPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Uzbek AI - Professional Dubbing Player")
        self.resize(1100, 850)
        
        self.temp_dir = tempfile.mkdtemp(prefix="dub_uz_")
        self.voice_map = {}
        self.play_ready = False

        self.init_ui()
        self.setup_multimedia()

        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.dubbing_engine)
        self.sync_timer.start(20)

    def setup_multimedia(self):
        self.player = QMediaPlayer()
        self.player.setVideoOutput(self.video_widget)
        self.v_audio = QAudioOutput()
        self.player.setAudioOutput(self.v_audio)
        self.v_audio.setVolume(0.1)

        self.uz_player = QMediaPlayer()
        self.uz_audio = QAudioOutput()
        self.uz_player.setAudioOutput(self.uz_audio)
        self.uz_audio.setVolume(1.0)
        
        self.uz_player.playbackStateChanged.connect(self.resume_video)

    def init_ui(self):
        widget = QWidget()
        self.setCentralWidget(widget)
        layout = QVBoxLayout(widget)
        
        self.btn = QPushButton("VIDEO TANLASH VA DUBLYAJNI TAYYORLASH")
        self.btn.setStyleSheet("height: 50px; background: #c0392b; color: white; font-weight: bold; border-radius: 5px;")
        self.btn.clicked.connect(self.open_video)
        
        self.pbar = QProgressBar()
        self.status = QLabel("Video tanlang...")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(550)
        
        layout.addWidget(self.btn)
        layout.addWidget(self.pbar)
        layout.addWidget(self.status)
        layout.addWidget(self.video_widget)

    def open_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Video", "", "Videos (*.mp4 *.mkv)")
        if path:
            self.v_path = path
            self.btn.setEnabled(False)
            self.worker = FinalTranslatorWorker(path, self.temp_dir)
            self.worker.progress_signal.connect(self.pbar.setValue)
            self.worker.status_signal.connect(self.status.setText)
            self.worker.finished_signal.connect(self.start_playback)
            self.worker.start()

    def start_playback(self, vmap):
        self.voice_map = vmap
        self.play_ready = True
        self.player.setSource(QUrl.fromLocalFile(self.v_path))
        self.player.play()
        self.status.setText("Dublyaj rejimi faol (Har bir so'z tarjima qilinadi)")

    def dubbing_engine(self):
        if not self.play_ready or self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            return
        
        current_pos = self.player.position()
        
        for t in list(self.voice_map.keys()):
            if abs(current_pos - t) < 150:
                voice_path = self.voice_map.pop(t)
                
                self.player.pause()
                
                self.uz_player.setSource(QUrl.fromLocalFile(voice_path))
                self.uz_player.play()
                break

    def resume_video(self, state):
        """O'zbekcha gap tugashi bilan videoni davom ettiradi"""
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.player.play()

    def closeEvent(self, event):
        """Vaqtinchalik fayllarni o'chirish"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            print("Tozalash bajarildi.")
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DubbingPlayer()
    window.show()
    sys.exit(app.exec())