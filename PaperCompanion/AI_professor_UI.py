import os
import sys
import subprocess
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QPushButton, QSplitter, 
                           QLabel, QFrame)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from .ui.markdown_view import MarkdownView
from .ui.chat_widget import ChatWidget
from .ui.sidebar_widget import SidebarWidget
from .data_manager import DataManager
from .AI_manager import AIManager
from .config import BASE_DIR, ONLINE_MODE

class AIProfessorUI(QMainWindow):
    """
    主視窗類別 - 學術論文AI助手的主介面
    
    負責創建和管理整個應用的UI布局、樣式和交互邏輯，
    包括側邊欄、文件檢視區和AI聊天區
    """
    def __init__(self, use_custom_titlebar=True):
        """初始化主視窗及所有子元件"""
        super().__init__()
        
        # 初始化資料管理器和AI管理器
        self.data_manager = DataManager(BASE_DIR)
        self.ai_manager = AIManager()

        # 初始化ONLINE模式
        self.online_mode = ONLINE_MODE
        
        # 設定兩者互相引用
        self.ai_manager.set_data_manager(self.data_manager)
        self.data_manager.set_ai_manager(self.ai_manager)
        
        self.use_custom_titlebar = use_custom_titlebar
        
        # 設定UI元素
        self.init_window_properties()
        if self.use_custom_titlebar:
            self.init_custom_titlebar()
        self.init_ui_components()
        
        # 連接資料管理器訊號
        self.connect_signals()
        
        # 載入論文資料
        self.data_manager.load_papers_index()
        
        # 在背景預載入所有論文向量庫
        self.ai_manager.init_rag_retriever(os.path.join(BASE_DIR,"output"))

    def init_window_properties(self):
        """初始化視窗屬性：大小、圖示、狀態列和視窗風格"""
        # 設定視窗標題和初始大小
        self.setWindowTitle("讀論文助手")
        self.setGeometry(100, 100, 1400, 900)
        
        # 添加狀態列
        self.statusBar().showMessage("就緒")
        self.statusBar().setStyleSheet("""
            QStatusBar {
                background-color: #303F9F;
                color: white;
                padding: 2px;
                font-size: 11px;
            }
        """)
        
        if self.use_custom_titlebar:
        # 無邊框但自己做控制按鈕
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                        Qt.WindowType.WindowMaximizeButtonHint | 
                        Qt.WindowType.WindowMinimizeButtonHint | 
                        Qt.WindowType.WindowCloseButtonHint)
        else:
        # 用系統原生邊框
            self.setWindowFlags(Qt.WindowType.Window)
        
        """
        # 設定無邊框視窗，但允許調整大小
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                          Qt.WindowType.WindowMaximizeButtonHint | 
                          Qt.WindowType.WindowMinimizeButtonHint | 
                          Qt.WindowType.WindowCloseButtonHint)
        """
        
        # 設定視窗樣式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #E8EAF6;
            }
        """)

    def init_custom_titlebar(self):
        """
        初始化自訂標題列
        
        創建一個美觀的自訂標題列，包含應用圖示、標題和視窗控制按鈕，
        並實現拖拽移動和雙擊最大化的功能
        """
        # 創建標題列框架
        self.titlebar = QFrame(self)
        self.titlebar.setObjectName("customTitleBar")
        self.titlebar.setFixedHeight(30)
        self.titlebar.setStyleSheet("""
            #customTitleBar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                             stop:0 #0D47A1, stop:0.5 #1A237E, stop:1 #0D47A1);
                color: white;
            }
        """)
        
        # 設定布局
        titlebar_layout = QHBoxLayout(self.titlebar)
        titlebar_layout.setContentsMargins(10, 0, 10, 0)
        titlebar_layout.setSpacing(5)
        
        # 設定應用圖示
        app_icon = QLabel()
        # 使用應用程式圖示渲染到標題列
        app_icon.setPixmap(self.windowIcon().pixmap(16, 16))
        
        # 設定應用標題
        app_title = QLabel("讀論文助手") if self.online_mode else QLabel("讀論文助理（離線版）")
        app_title.setStyleSheet("color: white; font-weight: bold;")
        
        # 創建視窗控制按鈕
        self.create_window_control_buttons()
        
        # 添加元件到布局
        titlebar_layout.addWidget(app_icon)
        titlebar_layout.addWidget(app_title)
        titlebar_layout.addStretch(1)
        titlebar_layout.addWidget(self.btn_minimize)
        titlebar_layout.addWidget(self.btn_maximize)
        titlebar_layout.addWidget(self.btn_close)
        
        # 綁定拖動和雙擊事件
        self.titlebar.mousePressEvent = self.titlebar_mousePressEvent
        self.titlebar.mouseMoveEvent = self.titlebar_mouseMoveEvent
        self.titlebar.mouseDoubleClickEvent = self.titlebar_doubleClickEvent
        
        # 將標題列添加到主視窗
        if self.use_custom_titlebar:
            self.layout().setMenuBar(self.titlebar)

    def create_window_control_buttons(self):
        """創建視窗控制按鈕：最小化、最大化和關閉"""
        # 通用按鈕樣式
        btn_style = """
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-family: Arial;
                font-weight: bold;
                font-size: 14px;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """
        
        # 最小化按鈕
        self.btn_minimize = QPushButton("🗕")
        self.btn_minimize.setStyleSheet(btn_style)
        self.btn_minimize.clicked.connect(self.showMinimized)
        self.btn_minimize.setToolTip("最小化")
        self.btn_minimize.setShortcut("Ctrl+M")
        self.btn_minimize.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # 最大化/還原按鈕
        self.btn_maximize = QPushButton("🗖")
        self.btn_maximize.setStyleSheet(btn_style)
        self.btn_maximize.clicked.connect(self.toggle_maximize)
        self.btn_maximize.setShortcut("Ctrl+F")
        self.btn_maximize.setToolTip("最大化")
        self.btn_maximize.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # 關閉按鈕
        self.btn_close = QPushButton("✕")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-family: Arial;
                font-weight: bold;
                font-size: 14px;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #FF3B30; /* macOS close button red */
                border-radius: 4px;
            }
        """)
        self.btn_close.clicked.connect(self.close)
        self.btn_close.setToolTip("關閉")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)

    def titlebar_mousePressEvent(self, event):
        """處理標題列的滑鼠按下事件，用於實現視窗拖動"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragPos = event.globalPosition().toPoint()
            event.accept()
    
    def titlebar_mouseMoveEvent(self, event):
        """處理標題列的滑鼠移動事件，實現視窗拖動"""
        if event.buttons() == Qt.MouseButton.LeftButton:
            if hasattr(self, 'dragPos'):
                self.move(self.pos() + event.globalPosition().toPoint() - self.dragPos)
                self.dragPos = event.globalPosition().toPoint()
                event.accept()
    
    def titlebar_doubleClickEvent(self, event):
        """處理標題列的雙擊事件，切換視窗最大化狀態"""
        self.toggle_maximize()
    
    def toggle_maximize(self):
        """切換視窗最大化/還原狀態"""
        if self.isMaximized():
            self.showNormal()
            self.btn_maximize.setText("🗖")
            self.btn_maximize.setToolTip("最大化")
        else:
            self.showMaximized()
            self.btn_maximize.setText("🗗")
            self.btn_maximize.setToolTip("還原")
        self.btn_maximize.setShortcut("Ctrl+F")

    def init_ui_components(self):
        """
        初始化UI元件和布局
        
        創建應用的主要UI元件，包括:
        - 側邊欄：用於顯示和選擇論文
        - 文件檢視區：顯示論文內容，支援中英文切換
        - 聊天區域：用於與AI助手交互
        """
        # 設定中心部件和主布局
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 初始化側邊欄
        self.sidebar = SidebarWidget()
        
        # 初始化主內容區域
        content_container = self.create_content_container()
        
        # 添加到主布局
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(content_container)
        
        # 應用全域樣式
        self.apply_global_styles()

    def create_content_container(self):
        """創建主內容區域容器，包含文件檢視區和聊天區域"""
        # 主內容區域容器
        content_container = QWidget()
        content_container.setObjectName("contentContainer")
        content_container.setStyleSheet("""
            #contentContainer {
                background-color: #E8EAF6;
            }
        """)
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(10, 10, 10, 10)
        
        # 內容區域
        content_widget = QWidget()
        content_widget.setObjectName("contentWidget")
        content_widget.setStyleSheet("""
            #contentWidget {
                background-color: #E8EAF6;
                border: 1px solid rgba(0,0,0,0.1);
            }
        """)
        
        content_inner_layout = QHBoxLayout(content_widget)
        content_inner_layout.setContentsMargins(0, 0, 0, 0)
        
        # 創建分隔器和內容區域元件
        splitter = self.create_content_splitter()
        content_inner_layout.addWidget(splitter)
        content_layout.addWidget(content_widget)
        
        return content_container

    def create_content_splitter(self):
        """創建內容區域分隔器，用於調整文件和聊天區域的比例"""
        # 分隔器，用於調整文件和聊天的寬度比例
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)  # 設定分隔條寬度
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #C5CAE9;
            }
        """)
        
        # 創建Markdown顯示區域
        md_container = self.create_markdown_container()
        
        # 創建聊天區域
        self.chat_widget = ChatWidget()
        self.chat_widget.set_paper_controller(self.data_manager)
        self.chat_widget.set_ai_controller(self.ai_manager)
        self.chat_widget.set_markdown_view(self.md_view) 
        
        # 添加到分隔器並設定初始比例
        splitter.addWidget(md_container)
        splitter.addWidget(self.chat_widget)
        splitter.setSizes([int(self.width() * 0.6), int(self.width() * 0.4)])
        
        return splitter

    def create_markdown_container(self):
        """創建Markdown文件顯示區域"""
        # Markdown顯示區域容器
        md_container = QWidget()
        md_container.setObjectName("mdContainer")
        md_layout = QVBoxLayout(md_container)
        md_layout.setContentsMargins(0, 0, 0, 0)
        md_layout.setSpacing(0)
        
        # 創建文件工具列
        toolbar = self.create_doc_toolbar()
        
        # 創建Markdown檢視容器
        md_view_container = QFrame()
        md_view_container.setObjectName("mdViewContainer")
        md_view_container.setStyleSheet("""
            #mdViewContainer {
                background-color: #FFFFFF;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
                border-left: 1px solid #CFD8DC;
                border-right: 1px solid #CFD8DC;
                border-bottom: 1px solid #CFD8DC;
            }
        """)
        md_view_layout = QVBoxLayout(md_view_container)
        md_view_layout.setContentsMargins(5, 5, 5, 10)

        # 創建Markdown檢視並傳入資料管理器
        self.md_view = MarkdownView()
        self.md_view.set_data_manager(self.data_manager)  # 設定資料管理器
        self.md_view.setStyleSheet("background-color: #FFFFFF;")
        md_view_layout.addWidget(self.md_view)
        
        # 添加到布局
        md_layout.addWidget(toolbar)
        md_layout.addWidget(md_view_container)
        
        return md_container

    def create_doc_toolbar(self):
        """創建文件工具列，包含標題和語言切換按鈕"""
        # 工具列容器
        toolbar = QFrame()
        toolbar.setObjectName("docToolbar")
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet("""
            #docToolbar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                             stop:0 #303F9F, stop:1 #1A237E);
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                color: white;
            }
        """)
        
        # 工具列布局
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(15, 0, 15, 0)
        
        # 工具列標題
        title_font = QFont("Source Han Sans SC", 11, QFont.Weight.Bold)
        doc_title = QLabel("論文閱讀")
        doc_title.setFont(title_font)
        doc_title.setStyleSheet("color: white; font-weight: bold;")
        
        # 語言切換按鈕
        self.lang_button = QPushButton("切換為英文")
        self.lang_button.setObjectName("langButton")
        self.lang_button.setStyleSheet("""
            #langButton {
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 8px;
                padding: 5px 15px;
                font-weight: bold;
            }
            #langButton:hover {
                background-color: rgba(255, 255, 255, 0.3);
            }
        """)
        self.lang_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lang_button.clicked.connect(self.toggle_language)

        self.pdf_button = QPushButton("View Original PDF")
        self.pdf_button.setObjectName("pdfButton")
        self.pdf_button.setStyleSheet("""
            #pdfButton {
                background-color: rgba(255, 0, 0, 0.4);
                color: white;
                border: 1px solid rgba(255, 0, 0, 0.6);
                border-radius: 8px;
                padding: 5px 15px;
                font-weight: bold;
            }
            #pdfButton:hover {
                background-color: rgba(255, 0, 0, 0.6);
            }
        """)
        self.pdf_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pdf_button.clicked.connect(self.toggle_pdf)
        self.pdf_button.setShortcut("Ctrl+P")
        self.pdf_button.setToolTip("View Original PDF")
        
        # 添加到布局
        toolbar_layout.addWidget(doc_title, 0, Qt.AlignmentFlag.AlignLeft)
        combo_widget = QWidget()
        combo_layout = QHBoxLayout(combo_widget)
        combo_layout.setContentsMargins(0, 0, 0, 0)
        combo_layout.addWidget(self.lang_button)
        combo_layout.addWidget(self.pdf_button)
        toolbar_layout.addWidget(combo_widget, 0, Qt.AlignmentFlag.AlignRight)
        
        return toolbar

    def apply_global_styles(self):
        """應用全域樣式，主要用於統一滾動條風格"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #E8EAF6;
            }
            QScrollBar:vertical {
                border: none;
                background: #F5F5F5;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #C5CAE9;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #7986CB;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

    def connect_signals(self):
        """連接資料管理器和UI元件的訊號和槽"""
        # 連接側邊欄上傳訊號
        self.sidebar.upload_file.connect(self.data_manager.upload_file)
        self.sidebar.upload_zip.connect(self.data_manager.load_achieved_papers)
        self.sidebar.pause_processing.connect(self.data_manager.pause_processing)
        self.sidebar.resume_processing.connect(self.data_manager.resume_processing)

        # 連接資料管理器的論文資料訊號
        self.sidebar.resume_processing.connect(self.data_manager.resume_processing)

        # 連接資料管理器的論文資料訊號
        self.data_manager.papers_loaded.connect(self.on_papers_loaded)  # 這是關鍵連接
        self.data_manager.paper_content_loaded.connect(self.on_paper_content_loaded)
        self.data_manager.loading_error.connect(self.on_loading_error)
        self.data_manager.message.connect(self.on_message)
        
        # 連接側邊欄的論文選擇訊號
        self.sidebar.paper_selected.connect(self.on_paper_selected)

        # 連接側邊欄的PDF下載訊號
        self.sidebar.download_selected.connect(self.data_manager.download_papers)

        # Toggle Active
        self.sidebar.toggle_active.connect(self.data_manager.toggle_active)

        # 連接處理進度訊號
        self.data_manager.processing_progress.connect(self.on_processing_progress)
        self.data_manager.processing_finished.connect(self.on_processing_finished)
        self.data_manager.processing_error.connect(self.on_processing_error)
        self.data_manager.queue_updated.connect(self.on_queue_updated)

        # 初始化處理系統
        self.data_manager.initialize_processing_system()

    def on_papers_loaded(self, papers):
        """
        處理論文列表載入完成的訊號
        
        Args:
            papers: 論文資料列表
        """
        self.sidebar.load_papers(papers)
        
    def on_paper_selected(self, paper_id):
        """
        處理論文選擇事件
        
        當用戶在側邊欄選擇一篇論文時，通知資料管理器載入相應內容
        
        Args:
            paper_id: 選擇的論文ID
        """
        # 通知資料管理器載入選定的論文
        self.data_manager.load_paper_content(paper_id)

    def toggle_active(self, paper_id):
        """
        切換論文的啟用狀態
        
        Args:
            paper_id: 論文ID
        """
        # 通知資料管理器切換選定的論文啟用狀態
        self.data_manager.toggle_active(paper_id)

    def on_paper_content_loaded(self, paper, zh_content, en_content):
        """
        處理論文內容載入完成的訊號
        
        Args:
            paper: 論文資料字典
            zh_content: 中文內容
            en_content: 英文內容
        """
        # 載入文件內容到Markdown檢視
        self.md_view.load_markdown(zh_content, "zh", render=False)  # 不立即渲染
        self.md_view.load_markdown(en_content, "en", render=False)  # 不立即渲染
        self.md_view.set_language("zh")  # 預設顯示中文
        
        # 更新語言按鈕文字
        self.lang_button.setText("切換為英文")
        self.lang_button.setShortcut("Ctrl+L")
        self.lang_button.setStyleSheet("""
            #langButton {
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 8px;
                padding: 5px 15px;
                font-weight: bold;
            }
            #langButton:hover {
                background-color: rgba(255, 255, 255, 0.3);
            }
        """)
        
        # 更新狀態列
        title = paper.get('id', '')
        #title = paper.get('translated_title', '') or paper.get('title', '')
        self.statusBar().showMessage(f"已載入論文: {title}")
        
        # 向AI助手傳送論文載入通知
        self.chat_widget.receive_ai_message(f"已載入論文「{title}」")

    def on_loading_error(self, error_message):
        """
        處理載入錯誤的訊號
        
        Args:
            error_message: 錯誤訊息
        """
        # 更新狀態列顯示錯誤
        self.statusBar().showMessage(f"錯誤: {error_message}")
        
        # 也可以在這裡添加更明顯的錯誤提示，如彈窗等

    def on_message(self, message):
        """
        處理一般訊息的訊號
        
        Args:
            message: 訊息內容
        """
        # 更新狀態列
        self.statusBar().showMessage(message)

    def toggle_pdf(self):
        """
        切換PDF檢視器
        """
        current_paper = self.data_manager.current_paper
        if current_paper and current_paper.get('id'):
            pdf_path = os.path.join(self.data_manager.base_dir,"data", f"{current_paper.get('id')}.pdf")
            if os.path.exists(pdf_path):
                try:
                    if os.name == 'nt':
                        # Windows系統
                        subprocess.Popen(['start', pdf_path], shell=True)
                    elif sys.platform == 'darwin':
                        # macOS系統
                        subprocess.Popen(['open', pdf_path])
                    else:
                        # Linux系統
                        subprocess.Popen(['xdg-open', pdf_path])
                    self.statusBar().showMessage(f"開啟PDF檔案: {pdf_path}")
                except Exception as e:
                    self.statusBar().showMessage(f"開啟PDF檔案失敗: {e}")
            else:
                self.statusBar().showMessage("PDF檔案不存在")
        else:
            self.statusBar().showMessage("未載入論文或未指定PDF路徑")
        pass

    def toggle_language(self):
        """
        切換文件語言
        
        在中文和英文之間切換文件顯示語言，並更新按鈕狀態和樣式
        """
        lang = self.md_view.toggle_language()
        
        # 設定按鈕文字和樣式
        if lang == "zh":
            btn_text = "切換為英文"
            self.lang_button.setStyleSheet("""
                #langButton {
                    background-color: rgba(255, 255, 255, 0.2);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    border-radius: 8px;
                    padding: 5px 15px;
                    font-weight: bold;
                }
                #langButton:hover {
                    background-color: rgba(255, 255, 255, 0.3);
                }
            """)
        else:
            btn_text = "切換為中文"
            self.lang_button.setStyleSheet("""
                #langButton {
                    background-color: rgba(65, 105, 225, 0.3);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    border-radius: 8px;
                    padding: 5px 15px;
                    font-weight: bold;
                }
                #langButton:hover {
                    background-color: rgba(65, 105, 225, 0.4);
                }
            """)
            
        self.lang_button.setText(btn_text)
        self.lang_button.setShortcut("Ctrl+L")
        
        # 更新狀態列
        current_paper = self.data_manager.current_paper
        if current_paper:
            language_text = "英文" if lang == "en" else "中文"
            title = current_paper.get('id')
            #title = current_paper.get('title' if lang == "en" else 'translated_title', '')
            self.statusBar().showMessage(f"已切換到{language_text}版本: {title}")

    def on_processing_progress(self, file_name, stage, progress, remaining):
        self.sidebar.update_upload_status(file_name, stage, progress, remaining)
        
    def on_processing_finished(self, paper_id):
        self.data_manager.load_papers_index()
        
    def on_processing_error(self, paper_id, error_msg):
        self.statusBar().showMessage(f"處理論文出錯: {error_msg}")
        
    def on_queue_updated(self, queue):
        """處理佇列更新回調"""
        # 獲取待處理檔案數量
        pending_count = len(queue)
        
        # 更新狀態列顯示
        if pending_count > 0:
            self.statusBar().showMessage(f"佇列中有 {pending_count} 個檔案待處理")
        else:
            self.statusBar().showMessage("處理佇列為空")
        
        # 更新上傳元件UI
        if pending_count == 0:
            # 佇列空時更新UI為完成狀態
            self.sidebar.update_upload_status("", "全部完成", 100, 0)
        elif not self.data_manager.is_processing and pending_count > 0:
            # 有待處理檔案但目前沒在處理時，顯示下一個要處理的檔案
            next_item = queue[0]
            self.sidebar.update_upload_status(
                os.path.basename(next_item['path']), 
                "等待處理", 
                0, 
                pending_count
            )

    def closeEvent(self, event):
        """處理視窗關閉事件 - 確保所有執行緒停止"""
        # 調用聊天部件的closeEvent
        # 清理AI管理器資源
        if hasattr(self, 'ai_manager'):
            self.ai_manager.cleanup()
        if hasattr(self, 'chat_widget'):
            # 如果chat_widget中有語音執行緒，請求中斷並清理
            if hasattr(self.chat_widget, 'voice_thread') and self.chat_widget.voice_thread:
                self.chat_widget.voice_thread.stop()  # 使用新增的stop()方法
                self.chat_widget.voice_thread.wait(1000)  # 等待執行緒完成，最多1秒
            
            self.chat_widget.closeEvent(event)
        
        # 停止任何正在執行的處理執行緒
        if self.data_manager.current_thread is not None and self.data_manager.current_thread.isRunning():
            self.data_manager.current_thread.stop()
            self.data_manager.current_thread.wait(1000)  # 等待執行緒完成，最多1秒
        
        # 調用父類別的closeEvent
        super().closeEvent(event)