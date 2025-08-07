import os
import json
import logging
from pathlib import Path
from ..config import LLMClient

# 翻譯提示詞檔案路徑
TITLE_TRANSLATE_PROMPT_PATH = "prompt/title_translate_prompt.txt"
CONTENT_TRANSLATE_PROMPT_PATH = "prompt/content_translate_prompt.txt"

class TranslateProcessor:
    """翻譯處理器, 使用LLM進行對論文json檔案分段翻譯"""

    def __init__(self, base_dir: str = ""):
        """初始化翻譯處理器"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.llm = LLMClient()
        self.base_dir = base_dir
        
        # 保存已翻譯的摘要，用於後續翻譯的上下文
        self.translated_abstract = ""
        
    def _read_file(self, filepath: str) -> str:
        """讀取檔案內容"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.warning(f"讀取檔案 {filepath} 失敗: {str(e)}")
            return ""
        
    def process(self, input_path: str, output_path: str) -> Path:
        """
        讀取 input.json，分階段進行翻譯。
        首先翻譯所有title，然後翻譯abstact，最後遞迴翻譯每個章節的text和caption。
        """
        try:
            input_path = Path(input_path)
            output_path = Path(output_path)

            self.logger.info(f"開始翻譯JSON檔案: {input_path}")
            with input_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 1. 翻譯標題
            self.translate_titles(data)
            
            # 2. 翻譯abstract
            self.translate_abstract(data)
            
            # 3. 翻譯sections內容
            self.translate_content(data)

            # 寫入 output.json
            with output_path.open('w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"翻譯完成，結果已保存到: {output_path}")
            return output_path
        except Exception as e:
            self.logger.error(f"JSON處理失敗: {str(e)}", exc_info=True)
            raise
    
    def translate_titles(self, data):
        """
        翻譯JSON結構中的所有標題
        將翻譯結果添加到對應層級title下的"translated_title"欄位
        """
        # 翻譯主標題
        if "title" in data:
            title = data["title"]
            self.logger.info(f"翻譯主標題: {title}")
            data["translated_title"] = self.translate_text("title", title)
        
        # 遞迴翻譯sections中的所有標題
        if "sections" in data:
            self.translate_section_titles(data["sections"])
    
    def translate_section_titles(self, sections):
        """遞迴翻譯所有章節標題"""
        for section in sections:
            # 翻譯當前章節標題
            if "title" in section:
                title = section["title"]
                self.logger.info(f"翻譯章節標題: {title}")
                section["translated_title"] = self.translate_text("title", title)
            
            # 遞迴翻譯子章節標題
            if "children" in section and section["children"]:
                self.translate_section_titles(section["children"])
    
    def translate_abstract(self, data):
        """翻譯論文摘要"""
        # 查找abstract部分
        if not data.get("sections"):
            self.logger.warning("未找到sections，跳過摘要翻譯")
            return
            
        for section in data["sections"]:
            if section.get("type") == "abstract":
                # 檢查是否有內容
                if not (section.get("content") and section["content"]):
                    self.logger.warning("Abstract內容為空，跳過摘要翻譯")
                    return
                    
                # 查找第一個type為text的content項
                abstract_text = ""
                for content_item in section["content"]:
                    if content_item.get("type") == "text":
                        abstract_text = content_item.get("content", "")
                        break
                        
                if not abstract_text:
                    self.logger.warning("Abstract中未找到text類型內容，跳過摘要翻譯")
                    return
                
                # 翻譯摘要
                self.logger.info("開始翻譯摘要")
                translated_abstract = self.translate_text("abstract", abstract_text)
                
                # 保存翻譯結果
                content_item["translated_content"] = translated_abstract
                self.translated_abstract = translated_abstract
                
                self.logger.info("摘要翻譯完成")
                return
                
        self.logger.warning("未找到abstract部分，跳過摘要翻譯")
    
    def translate_content(self, data):
        """翻譯所有章節內容"""
        if "sections" in data:
            self.translate_section_content(data["sections"])
    
    def translate_section_content(self, sections):
        """遞迴翻譯章節內容，包括文字和圖表標題"""
        for section in sections:
            # 對於abstract部分，只處理圖表和表格標題，跳過文字內容
            if section.get("type") == "abstract":
                self.logger.info("abstract部分: 只處理圖表和表格標題")
                if "content" in section:
                    for item in section["content"]:
                        # 先檢查item是否為字典類型
                        if not isinstance(item, dict):
                            self.logger.info(f"跳過非字典類型的內容: {str(item)[:50]}...")
                            continue
                        
                        # 根據類型處理不同內容
                        item_type = item.get("type")
                        
                        # 只處理圖表和表格標題，跳過文字內容
                        if item_type in ["figure", "table"] and "caption" in item and item["caption"]:
                            caption = item["caption"]
                            self.logger.info(f"翻譯abstract中的{item_type}標題: {caption[:50]}...")
                            item["translated_caption"] = self.translate_text("caption", caption, use_abstract_reference=True)
                continue

            # 翻譯章節內容
            if "content" in section:
                # 用於保存章節內的前一段翻譯，初始為空
                previous_section_translation = ""
                
                for item in section["content"]:
                    # 先檢查item是否為字典類型
                    if not isinstance(item, dict):
                        self.logger.info(f"跳過非字典類型的內容: {str(item)[:50]}...")
                        continue

                    # 根據類型處理不同內容
                    item_type = item.get("type")
                    
                    # 處理文字內容
                    if item_type == "text" and "content" in item and item["content"]:
                        content = item["content"]
                        self.logger.info(f"翻譯文字內容: {content[:50]}...")
                        
                        # 如果是章節的第一段文字且沒有前一段參考，則使用abstract作為參考
                        if not previous_section_translation:
                            item["translated_content"] = self.translate_text("content", content, 
                                                                           previous_translation=None, 
                                                                           use_abstract_reference=True)
                        else:
                            # 否則使用前一段文字作為參考
                            item["translated_content"] = self.translate_text("content", content, 
                                                                           previous_translation=previous_section_translation, 
                                                                           use_abstract_reference=False)
                        
                        # 更新章節內的前一段翻譯
                        previous_section_translation = item["translated_content"]
                    
                    # 處理圖表和表格標題（使用abstract作為參考）
                    elif item_type in ["figure", "table"] and "caption" in item and item["caption"]:
                        caption = item["caption"]
                        self.logger.info(f"翻譯{item_type}標題: {caption[:50]}...")
                        item["translated_caption"] = self.translate_text("caption", caption, use_abstract_reference=True)
                    
            # 遞迴翻譯子章節 - 每個子章節有自己的翻譯上下文
            if "children" in section and section["children"]:
                self.translate_section_content(section["children"])

    def translate_text(self, text_type, content, previous_translation=None, use_abstract_reference=False):
        """
        使用LLM翻譯指定類型的文字
        
        參數:
        text_type: 文字類型 (title, abstract, content, caption)
        content: 需要翻譯的內容
        previous_translation: 前一段文字的翻譯（可選）
        use_abstract_reference: 是否使用abstract作為參考（圖表和表格標題，或章節第一段）
        """
        # 根據文字類型選擇對應的提示詞檔案路徑
        prompt_file = os.path.join(self.base_dir,TITLE_TRANSLATE_PROMPT_PATH) if text_type == "title" else os.path.join(self.base_dir,CONTENT_TRANSLATE_PROMPT_PATH)
        
        # 讀取系統提示詞
        system_prompt = self._read_file(prompt_file)
        
        # 構建使用者提示詞
        if text_type == "title":
            user_prompt = f"需要翻譯的標題:\n{content}\n\n直接輸出："
        elif text_type == "abstract":
            user_prompt = f"需要翻譯的內容:\n{content}\n\n直接輸出："
        elif use_abstract_reference and self.translated_abstract:
            # 圖表和表格標題或章節第一段使用abstract作為參考
            user_prompt = f"摘要翻譯參考:\n{self.translated_abstract}\n\n需要翻譯的內容:\n{content}\n\n直接輸出："
        elif previous_translation:
            # 使用前一段文字作為參考（章節內的非第一段）
            user_prompt = f"前文翻譯參考:\n{previous_translation}\n\n需要翻譯的內容:\n{content}\n\n直接輸出："
        else:
            # 如果沒有任何參考，直接翻譯
            user_prompt = f"需要翻譯的內容:\n{content}\n\n直接輸出："

        # 構建翻譯提示並調用LLM進行翻譯
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        return self.llm.chat(messages, stream=True).strip()