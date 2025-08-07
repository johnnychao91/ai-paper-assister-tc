import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase, QFont, QPalette, QColor, QIcon, QPixmap, QPainter, QBrush, QLinearGradient
from PyQt6.QtCore import Qt, QRect, QPoint
from .paths import get_font_path
from .AI_professor_UI import AIProfessorUI

def generate_app_icon():
    """產生應用程式圖示"""
    # 建立圖示畫布
    icon_size = 64
    pixmap = QPixmap(icon_size, icon_size)
    pixmap.fill(Qt.GlobalColor.transparent)  # 透明背景
    
    # 建立畫筆
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    
    # 建立漸層背景
    gradient = QLinearGradient(0, 0, icon_size, icon_size)
    gradient.setColorAt(0, QColor(13, 71, 161))  # 深藍色 #0D47A1
    gradient.setColorAt(0.5, QColor(26, 35, 126))  # 深靛藍 #1A237E
    gradient.setColorAt(1, QColor(13, 71, 161))  # 深藍色 #0D47A1
    
    # 繪製圓形背景
    painter.setBrush(QBrush(gradient))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, icon_size-8, icon_size-8)
    
    # 繪製書本圖案
    painter.setPen(Qt.GlobalColor.white)
    painter.setBrush(QBrush(QColor(255, 255, 255, 180)))
    
    # 繪製書本封面
    book_rect = QRect(18, 16, 28, 32)
    painter.drawRect(book_rect)
    
    # 繪製書頁
    painter.setBrush(QBrush(QColor(240, 240, 240)))
    page_rect = QRect(16, 18, 28, 29)
    painter.drawRect(page_rect)
    
    # 繪製書脊線條
    for i in range(4):
        y = 22 + i * 6
        painter.drawLine(QPoint(16, y), QPoint(44, y))
    
    # 繪製AI圖示（簡化的"AI"文字）
    painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
    painter.setPen(QColor(26, 35, 126))  # 深靛藍色
    painter.drawText(QRect(20, 20, 20, 20), Qt.AlignmentFlag.AlignCenter, "AI")
    
    # 結束繪製
    painter.end()
    
    # 建立圖示
    return QIcon(pixmap)

"""
def save_icon_to_file():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    icon = generate_app_icon()
    painter = QPainter(pixmap)
    icon.paint(painter, 0, 0, 64, 64)
    painter.end()

    pixmap.save("app_icon_output.png")
    print("圖示已儲存為 app_icon_output.png")
"""

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 使用Fusion風格以獲得更現代的外觀
    
    # 產生並設定應用程式圖示
    app_icon = generate_app_icon()
    app.setWindowIcon(app_icon)
    
    #save_icon_to_file()
    
    # 如果是Windows系統，設定工作列圖示ID
    if sys.platform == "win32":
        import ctypes
        app_id = 'ai.professor.paperassistant.1.0'  # 應用程式唯一識別符
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    
    # 註冊字型
    # UI使用思源黑體
    font_id_regular = QFontDatabase.addApplicationFont(get_font_path("SourceHanSansSC-Regular-2.otf"))
    font_id_bold = QFontDatabase.addApplicationFont(get_font_path("SourceHanSansSC-Bold-2.otf"))
    
    # 註冊Markdown字型
    # Markdown用的思源宋體
    QFontDatabase.addApplicationFont(get_font_path("SourceHanSerifCN-Regular-1.otf"))
    QFontDatabase.addApplicationFont(get_font_path("SourceHanSerifCN-Bold-2.otf"))

    # 檢查字型是否載入成功
    if font_id_regular != -1 and font_id_bold != -1:
        font_family_regular = QFontDatabase.applicationFontFamilies(font_id_regular)[0]
        font_family_bold = QFontDatabase.applicationFontFamilies(font_id_bold)[0]
        
        # 設定應用程式預設字型
        default_font = QFont(font_family_regular, 10)
        app.setFont(default_font)
    else:
        print("無法載入自訂字體，使用系統預設字體")
    
    # 設定應用程式級別的調色盤，使介面更加現代
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(51, 51, 51))
    palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(245, 245, 245))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(51, 51, 51))
    palette.setColor(QPalette.ColorRole.Text, QColor(51, 51, 51))
    palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(51, 51, 51))
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    
    app.setPalette(palette)
    
    window = AIProfessorUI(use_custom_titlebar=False)
    #window = AIProfessorUI(use_custom_titlebar=True)
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()