import os

# 獲取專案根目錄
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

# 常用目錄
FONT_DIR = os.path.join(PROJECT_ROOT, "font")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")

# 輔助函數
def get_font_path(font_name):
    return os.path.join(FONT_DIR, font_name)

def get_asset_path(asset_name):
    return os.path.join(ASSETS_DIR, asset_name)