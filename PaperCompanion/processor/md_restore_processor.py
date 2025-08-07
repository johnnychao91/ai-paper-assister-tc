import json
import logging
from pathlib import Path
from collections import defaultdict

class RestoreProcessor:
    """恢復處理器, 將提供的json檔案還原成中英兩篇md文檔"""

    def __init__(self):
        """初始化恢復處理器"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def _read_file(self, filepath: str) -> str:
        """讀取檔案內容"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.warning(f"讀取檔案 {filepath} 失敗: {str(e)}")
            return ""

    def _write_to_md(self, filepath, content):
        """將內容寫入md檔案"""
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(content + "\n\n")
    
    def _process_section(self, section, output_path_en, output_path_zh, level=1):
        """處理文檔的一個章節，遞歸處理子章節"""
        # 處理標題
        title_prefix = "#" * level
        
        # 英文標題
        en_title = f"{title_prefix} {section['title']}"
        self._write_to_md(output_path_en, en_title)
        
        # 中文標題
        zh_title = f"{title_prefix} {section.get('translated_title')}"
        self._write_to_md(output_path_zh, zh_title)
        
        # 處理正文內容
        if 'content' in section and section['content']:
            # 建立一個有序的結構來存儲所有內容項及其位置資訊
            ordered_items = []
            
            # 使用字典來存儲按索引分組的文字塊
            en_text_blocks = defaultdict(list)
            zh_text_blocks = defaultdict(list)
            
            # 第一遍遍歷：收集所有內容項
            for item in section['content']:
                if isinstance(item, str):  # 如果直接是字串（參考文獻等）
                    ordered_items.append({
                        'type': 'ref',
                        'content': item,
                        'index': float('inf'),  # 參考文獻通常放在最後
                        'part': 0
                    })
                elif isinstance(item, dict):
                    item_type = item.get('type')
                    index = item.get('index', 0)
                    part = item.get('part', 0)
                    
                    if item_type == 'text':
                        # 處理文字內容：先收集起來，稍後合併相同index的
                        en_content = item.get('content', '')
                        zh_content = item.get('translated_content', en_content)
                        
                        # 按索引和部分存儲內容
                        en_text_blocks[index].append((part, en_content))
                        zh_text_blocks[index].append((part, zh_content))
                        
                        # 記錄這個文字塊的位置資訊，用於最終有序處理
                        ordered_items.append({
                            'type': 'text',
                            'index': index,
                            'part': part
                        })
                    
                    elif item_type == 'formula':
                        ordered_items.append({
                            'type': 'formula',
                            'content': item.get('content', ''),
                            'index': index,
                            'part': part
                        })
                    
                    elif item_type == 'figure':
                        ordered_items.append({
                            'type': 'figure',
                            'src': item.get('src', ''),
                            'alt': item.get('alt', ''),
                            'en_caption': item.get('caption', ''),
                            'zh_caption': item.get('translated_caption', item.get('caption', '')),
                            'index': index,
                            'part': part
                        })
                    
                    elif item_type == 'table':
                        ordered_items.append({
                            'type': 'table',
                            'content': item.get('content', ''),
                            'en_caption': item.get('caption', ''),
                            'zh_caption': item.get('translated_caption', item.get('caption', '')),
                            'index': index,
                            'part': part
                        })
            
            # 按索引和部分排序所有內容
            ordered_items.sort(key=lambda x: (x['index'], x['part']))
            
            # 處理已合併的文字塊索引集合
            processed_text_indices = set()
            
            # 按照排序後的順序寫入內容
            for item in ordered_items:
                if item['type'] == 'text':
                    index = item['index']
                    
                    # 如果這個索引的文字塊已經處理過，跳過
                    if index in processed_text_indices:
                        continue
                    
                    # 合併並寫入相同索引的文字塊
                    # 對相同index的文字塊按part排序
                    en_parts = sorted(en_text_blocks[index], key=lambda x: x[0])
                    zh_parts = sorted(zh_text_blocks[index], key=lambda x: x[0])
                    
                    # 合併相同index的文字塊
                    en_content = ' '.join([part[1] for part in en_parts])
                    zh_content = ' '.join([part[1] for part in zh_parts])
                    
                    # 寫入合併後的內容
                    self._write_to_md(output_path_en, en_content)
                    self._write_to_md(output_path_zh, zh_content)
                    
                    # 標記這個索引已處理
                    processed_text_indices.add(index)
                
                elif item['type'] == 'formula':
                    # 處理公式（公式在中英文文檔中保持一致）
                    self._write_to_md(output_path_en, item['content'])
                    self._write_to_md(output_path_zh, item['content'])
                
                elif item['type'] == 'figure':
                    # 英文圖片說明
                    en_figure = f"![{item['alt']}]({item['src']})\n\n*{item['en_caption']}*"
                    self._write_to_md(output_path_en, en_figure)
                    
                    # 中文圖片說明
                    zh_figure = f"![{item['alt']}]({item['src']})\n\n*{item['zh_caption']}*"
                    self._write_to_md(output_path_zh, zh_figure)
                
                elif item['type'] == 'table':
                    # 表格內容在中英文文檔中保持一致
                    self._write_to_md(output_path_en, item['content'])
                    self._write_to_md(output_path_zh, item['content'])
                    
                    # 處理表格標題
                    if item['en_caption']:
                        en_caption = f"*{item['en_caption']}*"
                        self._write_to_md(output_path_en, en_caption)
                        
                        zh_caption = f"*{item['zh_caption']}*"
                        self._write_to_md(output_path_zh, zh_caption)
                
                elif item['type'] == 'ref':
                    # 參考文獻保持原樣
                    self._write_to_md(output_path_en, item['content'])
                    self._write_to_md(output_path_zh, item['content'])
        
        # 遞歸處理子章節
        if 'children' in section and section['children']:
            for child in section['children']:
                self._process_section(child, output_path_en, output_path_zh, level + 1)
    
    def process(self, input_path: str, output_path_en: str, output_path_zh: str) -> tuple:
        """
        讀取 input.json，恢復成中英文兩篇md文檔
        1. 中文用翻譯部分；如果沒有翻譯則保留英文原文
        """
        try:
            input_path = Path(input_path)
            output_path_en = Path(output_path_en)
            output_path_zh = Path(output_path_zh)
            
            # 確保輸出目錄存在
            output_path_en.parent.mkdir(parents=True, exist_ok=True)
            output_path_zh.parent.mkdir(parents=True, exist_ok=True)
            
            # 清空輸出檔案
            open(output_path_en, 'w', encoding='utf-8').close()
            open(output_path_zh, 'w', encoding='utf-8').close()
            
            self.logger.info(f"開始處理JSON檔案: {input_path}")
            with input_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 處理文檔標題
            title_en = data.get('title', '')
            self._write_to_md(output_path_en, f"# {title_en}")
            
            title_zh = data.get('translated_title', title_en)
            self._write_to_md(output_path_zh, f"# {title_zh}")
            
            # 處理作者資訊
            if 'authors_info' in data:
                self._write_to_md(output_path_en, data['authors_info'])
                self._write_to_md(output_path_zh, data['authors_info'])
            
            # 處理各個章節
            for section in data['sections']:
                self._process_section(section, output_path_en, output_path_zh)
            
            self.logger.info(f"恢復完成，結果已保存到: {output_path_en} 和 {output_path_zh}")
            return output_path_en, output_path_zh
        except Exception as e:
            self.logger.error(f"JSON處理失敗: {str(e)}", exc_info=True)
            raise


# 使用示例
if __name__ == "__main__":
    processor = RestoreProcessor()
    processor.process(
        "output/HUMAN-LIKE EPISODIC MEMORY FOR INFINITE CONTEXT LLMS/HUMAN-LIKE EPISODIC MEMORY FOR INFINITE CONTEXT LLMS_translated.json",
        "output_english.md",
        "output_chinese.md"
    )