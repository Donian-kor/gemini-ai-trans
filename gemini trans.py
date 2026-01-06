import sys
import os
import google.genai as genai
import configparser
import docx
import PyPDF2
import requests
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QFileDialog, QComboBox, QMessageBox, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

# INI 파일에서 API 키 읽기 (항상 tarns.py가 있는 폴더 기준)
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.ini")

config = configparser.ConfigParser()
config.read(config_path)

API_KEY = None
if "gemini" in config and "api_key" in config["gemini"]:
    API_KEY = config["gemini"]["api_key"].strip()

# 실행 전에 API 키 확인
if not API_KEY:
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 11))  # 전체 글꼴 고정
    QMessageBox.critical(None, "API 키 오류",
    """⚠️ config.ini 파일이 없거나 API 키가 설정되지 않았습니다.
config.ini 파일을 확인하고 올바른 API 키를 입력하세요.""")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

# 한글 → 영어 매핑
LANG_MAP = {
    "자동 감지": "auto",
    "영어": "English",
    "한국어": "Korean",
    "일본어": "Japanese",
    "중국어": "Chinese",
    "프랑스어": "French",
    "독일어": "German"
}

class TranslatorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.apply_styles()

    def init_ui(self):
        self.setWindowTitle("Gemini 번역기 — 확장판")
        self.setGeometry(300, 200, 800, 600)

        main_layout = QVBoxLayout()

        # 상단: 원문 / 번역 / 모델 선택 / UI 언어 선택
        top_layout = QHBoxLayout()

        self.source_lang_combo = QComboBox()
        self.source_lang_combo.addItems(["자동 감지", "영어", "한국어", "일본어", "중국어", "프랑스어", "독일어"])
        self.source_lang_combo.setCurrentIndex(0)

        self.target_lang_combo = QComboBox()
        self.target_lang_combo.addItems(["영어", "한국어", "일본어", "중국어", "프랑스어", "독일어"])
        self.target_lang_combo.setCurrentIndex(1)

        self.model_combo = QComboBox()
        try:
            models = client.models.list()
            for m in models:
                if any(ver in m.name for ver in ["2.0", "2.5", "3.0"]):
                    self.model_combo.addItem(m.name)
            if self.model_combo.count() == 0:
                self.model_combo.addItem("⚠️ 지원되는 모델 없음")
        except Exception:
            self.model_combo.addItem("⚠️ API 키를 확인하세요")

        self.model_combo.setCurrentIndex(0)

        lbl_source = QLabel("원문:")
        lbl_source.setAlignment(Qt.AlignCenter)
        lbl_source.setObjectName("lbl_source")

        lbl_target = QLabel("번역:")
        lbl_target.setAlignment(Qt.AlignCenter)
        lbl_target.setObjectName("lbl_target")

        lbl_model = QLabel("모델 선택:")
        lbl_model.setAlignment(Qt.AlignCenter)
        lbl_model.setObjectName("lbl_model")

        top_layout.addWidget(lbl_source)
        top_layout.addWidget(self.source_lang_combo)
        top_layout.addWidget(lbl_target)
        top_layout.addWidget(self.target_lang_combo)
        top_layout.addWidget(lbl_model)
        top_layout.addWidget(self.model_combo)

        # UI 언어 선택 콤보박스
        self.ui_lang_combo = QComboBox()
        self.ui_lang_combo.addItems(["한국어", "English"])
        self.ui_lang_combo.currentIndexChanged.connect(self.on_ui_language_changed)
        top_layout.addWidget(self.ui_lang_combo)

        main_layout.addLayout(top_layout)

        # 중간 입력/출력
        middle_layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        left_label = QLabel("원문 텍스트 입력")
        left_label.setObjectName("input_label")
        left_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(left_label)
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("여기에 원문 텍스트를 입력하거나, '파일 불러오기'를 사용하세요.")
        left_layout.addWidget(self.input_text)

        # 웹 번역용 URL 입력창 + 버튼을 한 줄로 배치
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()    
        self.url_input.setPlaceholderText("번역할 웹페이지 URL 입력")
        url_layout.addWidget(self.url_input)

        self.web_btn = QPushButton("웹 번역하기")
        self.web_btn.clicked.connect(self.translate_webpage)
        url_layout.addWidget(self.web_btn)

        left_layout.addLayout(url_layout)  # 왼쪽 레이아웃에 추가

        # 딜레이 타이머 설정 (3초)
        self.detect_timer = QTimer()
        self.detect_timer.setSingleShot(True)
        self.detect_timer.timeout.connect(self.auto_detect_language)
        self.input_text.textChanged.connect(self.schedule_detect)

        right_layout = QVBoxLayout()
        right_label = QLabel("번역 결과")
        right_label.setObjectName("output_label")
        right_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(right_label)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText("여기에 번역 결과가 표시됩니다.")
        right_layout.addWidget(self.output_text)

        middle_layout.addLayout(left_layout)
        middle_layout.addLayout(right_layout)

        # 하단 버튼
        button_layout = QHBoxLayout()
        self.load_btn = QPushButton("파일 불러오기")
        self.load_btn.clicked.connect(self.load_file)
        button_layout.addWidget(self.load_btn)

        self.translate_btn = QPushButton("번역하기")
        self.translate_btn.clicked.connect(self.translate_text)
        button_layout.addWidget(self.translate_btn)

        self.save_btn = QPushButton("번역 결과 저장")
        self.save_btn.clicked.connect(self.save_translation)
        button_layout.addWidget(self.save_btn)

        main_layout.addLayout(middle_layout)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #f0f8ff;
                font-family: "Segoe UI";
                font-size: 11pt;
            }
            QLabel {
                color: #2c3e50;
                font-weight: bold;
                background-color: #e6f7ff;
                border: 1px solid #b0c4de;
                border-radius: 8px;
                padding: 4px 8px;
            }
            QTextEdit {
                border: 1px solid #b0c4de;
                border-radius: 10px;
                padding: 8px;
                background-color: #ffffff;
            }
            QPushButton {
                background-color: #add8e6;
                color: #2c3e50;
                font-weight: bold;
                font-family: "Segoe UI";
                border-radius: 10px;
                padding: 8px 14px;
            }
            QPushButton:hover {
                background-color: #87ceeb;
            }
        """)
    def schedule_detect(self):
        self.detect_timer.start(3000)

    def load_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "파일 열기", "",
            "Text Files (*.txt);;Word Files (*.docx);;PDF Files (*.pdf);;All Files (*)"
        )
        if file_name:
            ext = os.path.splitext(file_name)[1].lower()
            try:
                if ext == ".txt":
                    with open(file_name, "r", encoding="utf-8") as f:
                        self.input_text.setText(f.read())
                elif ext == ".docx":
                    doc = docx.Document(file_name)
                    text = "\n".join([p.text for p in doc.paragraphs])
                    self.input_text.setText(text)
                elif ext == ".pdf":
                    reader = PyPDF2.PdfReader(file_name)
                    text = "\n".join([page.extract_text() for page in reader.pages])
                    self.input_text.setText(text)
                else:
                    self.input_text.setText("⚠️ 지원하지 않는 파일 형식입니다.")
            except Exception as e:
                self.input_text.setText(f"⚠️ 파일 읽기 오류: {e}")

    def save_translation(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "번역 결과 저장", "", "Text Files (*.txt)")
        if file_name:
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(self.output_text.toPlainText())

    def detect_language(self, text: str) -> str:
        model_name = self.model_combo.currentText()
        if "⚠️" in model_name:
            return "모델 선택 불가"
        response = client.models.generate_content(
            model=model_name,
            contents=f"Detect the language of this text and answer with the language name only:\n{text}"
        )
        return (response.text or "").strip()

    def auto_detect_language(self):
        source_text = self.input_text.toPlainText().strip()
        if not source_text:
            self.source_lang_combo.setCurrentText("자동 감지")
            return
        detected = self.detect_language(source_text)
        self.source_lang_combo.setCurrentText(detected or "감지 실패")

    def translate_text(self):
        source_text = self.input_text.toPlainText().strip()
        if not source_text:
            self.output_text.setText("⚠️ 번역할 문장을 입력하거나 파일을 불러오세요.")
            return

        source_lang = LANG_MAP.get(self.source_lang_combo.currentText(), "auto")
        if source_lang == "auto":
            source_lang = self.detect_language(source_text)
            self.source_lang_combo.setCurrentText(source_lang or "감지 실패")

        target_lang = LANG_MAP.get(self.target_lang_combo.currentText(), "Korean")
        model_name = self.model_combo.currentText()

        if "⚠️" in model_name:
            self.output_text.setText("⚠️ 올바른 모델을 선택해주세요.")
            return

        prompt = (
            f"Translate the following text from {source_lang} to {target_lang} using the {model_name} model.\n"
            f"Text:\n{source_text}"
        )

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            self.output_text.setText(response.text or "")
        except Exception as e:
            self.output_text.setText(f"⚠️ 번역 중 오류 발생: {e}")

    def translate_webpage(self):
        url = self.url_input.text().strip()
        if not url:
            self.output_text.setText("⚠️ URL을 입력해주세요.")
            return
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text()
            self.input_text.setText(text[:5000])  # 너무 길면 잘라서 표시
            self.translate_text()
        except Exception as e:
            self.output_text.setText(f"⚠️ 웹페이지 불러오기 실패: {e}")

    def on_ui_language_changed(self, index):
        if index == 0:
            self.change_ui_language("ko")
        else:
            self.change_ui_language("en")

    def change_ui_language(self, lang_code):
        ui_texts = {
            "ko": {
                "window_title": "Gemini 번역기 — 확장판",
                "lbl_source": "원문:",
                "lbl_target": "번역:",
                "lbl_model": "모델 선택:",
                "input_label": "원문 텍스트 입력",
                "output_label": "번역 결과",
                "load_btn": "파일 불러오기",
                "translate_btn": "번역하기",
                "save_btn": "번역 결과 저장",
                "web_btn": "웹 번역하기",
                "source_langs": ["자동 감지", "영어", "한국어", "일본어", "중국어", "프랑스어", "독일어"],
                "target_langs": ["영어", "한국어", "일본어", "중국어", "프랑스어", "독일어"]
            },
            "en": {
                "window_title": "Gemini Translator — Extended",
                "lbl_source": "Source:",
                "lbl_target": "Translation:",
                "lbl_model": "Select Model:",
                "input_label": "Input Text",
                "output_label": "Translation Result",
                "load_btn": "Load File",
                "translate_btn": "Translate",
                "save_btn": "Save Translation",
                "web_btn": "Translate Webpage",
                "source_langs": ["Auto Detect", "English", "Korean", "Japanese", "Chinese", "French", "German"],
                "target_langs": ["English", "Korean", "Japanese", "Chinese", "French", "German"]
            }
        }

        texts = ui_texts.get(lang_code, ui_texts["ko"])

        self.setWindowTitle(texts["window_title"])
        self.findChild(QLabel, "lbl_source").setText(texts["lbl_source"])
        self.findChild(QLabel, "lbl_target").setText(texts["lbl_target"])
        self.findChild(QLabel, "lbl_model").setText(texts["lbl_model"])
        self.findChild(QLabel, "input_label").setText(texts["input_label"])
        self.findChild(QLabel, "output_label").setText(texts["output_label"])
        self.load_btn.setText(texts["load_btn"])
        self.translate_btn.setText(texts["translate_btn"])
        self.save_btn.setText(texts["save_btn"])
        self.web_btn.setText(texts["web_btn"])
        self.source_lang_combo.clear()
        self.source_lang_combo.addItems(texts["source_langs"])
        self.target_lang_combo.clear()
        self.target_lang_combo.addItems(texts["target_langs"])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("맑은 고딕", 11))
    translator = TranslatorApp()
    translator.change_ui_language("ko")  # 기본 UI 언어 설정: 한국어
    translator.show()
    sys.exit(app.exec_())