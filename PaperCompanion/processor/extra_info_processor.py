import os
import json
import logging
from pathlib import Path
from ..config import LLMClient

SUMMARY_PROMPT_PATH = "prompt/summary_generation_prompt.txt"
QUESTION_PROMPT_PATH = "prompt/question_generation_prompt.txt"
GRAPH_QUESTION_PROMPT_PATH = "prompt/graph_question_generation_prompt.txt"
FORMULA_ANALYSIS_PROMPT_PATH = "prompt/formula_analysis_prompt.txt"

class ExtraInfoProcessor:
    """額外資訊處理器，用於生成論文各章節的總結資訊和問題"""

    def __init__(self, base_dir: str = ""):
        """初始化額外資訊處理器"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.llm = LLMClient()
        self.abstract_text = ""
        self.base_dir = base_dir
        
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
        讀取JSON檔案，自下而上為各章節生成總結
        
        Args:
            input_path: 輸入JSON檔案路徑
            output_path: 輸出添加了總結的JSON檔案路徑
            
        Returns:
            Path: 輸出檔案路徑
        """
        try:
            input_path = Path(input_path)
            output_path = Path(output_path)

            self.logger.info(f"開始生成章節總結: {input_path}")
            with input_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 提取摘要資訊
            self.extract_abstract(data)
            
            # 從頂層章節開始，自下而上生成總結
            if "sections" in data:
                self.generate_section_summaries(data["sections"])
                
                # 生成問題階段
                self.logger.info("開始生成各塊內容的問題")
                self.generate_questions(data["sections"])
                self.logger.info("問題生成完成")

            # 寫入輸出檔案
            with output_path.open('w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"章節總結和問題生成完成，結果已保存到: {output_path}")
            return output_path
        except Exception as e:
            self.logger.error(f"章節總結和問題生成失敗: {str(e)}", exc_info=True)
            raise
    
    def extract_abstract(self, data):
        """
        從資料中提取摘要資訊並保存到類別變數
        
        Args:
            data: 論文資料
        """
        if "sections" not in data:
            return
        
        for section in data["sections"]:
            if section.get("type") == "abstract":
                abstract_text = ""
                for item in section.get("content", []):
                    if isinstance(item, dict) and item.get("type") == "text" and item.get("translated_content"):
                        abstract_text += item["translated_content"] + "\n"
                
                if abstract_text:
                    self.abstract_text = abstract_text.strip()
                    self.logger.info("已提取摘要資訊")
                    return
        
        self.logger.warning("未找到摘要資訊")
    
    def generate_section_summaries(self, sections):
        """
        自下而上遞迴生成所有章節的總結
        
        Args:
            sections: 章節列表
            
        Returns:
            list: 當前層級所有章節的總結列表，每個元素為{"title": 章節標題, "summary": 章節總結}的字典
        """
        all_summaries = []
        
        for section in sections:
            # 跳過abstract和references類型的章節
            if section.get("type") in ["abstract", "references"]:
                self.logger.info(f"跳過 {section.get('title')} 章節的總結生成")
                continue
            
            # 收集子章節總結
            children_summaries = []
            if "children" in section and section["children"]:
                # 遞迴處理子章節，獲取子章節的總結列表
                children_summaries = self.generate_section_summaries(section["children"])
                
            # 生成當前章節的總結
            self.logger.info(f"生成 {section.get('title', '未命名章節')} 的總結")
            section_summary = self.generate_summary_for_section(section, children_summaries)
            
            if section_summary:
                section["summary"] = section_summary
                # 將當前章節的標題和總結作為字典添加到列表中
                title = section.get('translated_title', section.get('title', '未命名章節'))
                all_summaries.append({"title": title, "summary": section_summary})
                
        return all_summaries
    
    def generate_summary_for_section(self, section, children_summaries=None):
        """
        為單個章節生成總結，綜合考慮自身內容和子章節總結
        
        Args:
            section: 章節資料
            children_summaries: 子章節總結列表，每個元素為{"title": 章節標題, "summary": 章節總結}的字典
            
        Returns:
            str: 生成的章節總結
        """
        if children_summaries is None:
            children_summaries = []
            
        # 提取章節中所有翻譯後的文字內容和formula內容
        contents = []
        for item in section.get("content", []):
            if isinstance(item, dict):
                if item.get("type") == "text" and item.get("translated_content"):
                    contents.append(item["translated_content"])
                elif item.get("type") == "formula" and item.get("content"):
                    contents.append(item['content'])
        
        # 如果沒有內容且沒有子章節總結，跳過總結生成
        if not contents and not children_summaries:
            self.logger.warning(f"章節 {section.get('title', '未命名章節')} 沒有內容和子章節總結，跳過總結生成")
            return ""
        
        # 合併所有內容
        combined_text = "\n\n".join(contents) if contents else ""
        
        # 添加子章節總結資訊（如果有），並包含章節標題
        children_summaries_text = ""
        if children_summaries:
            # 構建包含子章節標題的總結文字
            sub_summaries = []
            for child in children_summaries:
                sub_summaries.append(f"{child['title']}核心內容:\n{child['summary']}")
            
            children_summaries_text = "子章節：\n" + "\n\n".join(sub_summaries)
        
        # 合併當前章節內容和子章節總結，用於檢查長度
        total_content = ""
        if combined_text:
            total_content += combined_text
        if children_summaries_text:
            total_content += "\n\n" + children_summaries_text if total_content else children_summaries_text
        
        # 如果總內容不超過100字元，直接使用總內容作為總結
        if len(total_content) <= 100:
            self.logger.info(f"章節 {section.get('title', '未命名章節')} 內容不超過100字元，直接使用原內容作為總結")
            return total_content.replace("\n", " ").strip()
        
        # 讀取系統提示詞
        system_prompt = self._read_file(os.path.join(self.base_dir,SUMMARY_PROMPT_PATH))
        
        # 構建使用者提示詞
        user_prompt = f"章節標題: {section.get('translated_title', section.get('title', '未命名章節'))}\n\n"
        
        # 添加摘要作為背景資訊
        if self.abstract_text:
            user_prompt += f"論文摘要背景:\n{self.abstract_text}\n\n"
        
        if combined_text:
            user_prompt += f"章節內容:\n{combined_text}\n\n"
            
        if children_summaries_text:
            user_prompt += f"{children_summaries_text}\n\n"
            
        user_prompt += "請根據要求生成這個章節的總結，只需輸出總結文段，無需任何額外的解釋說明:"
        
        # 調用LLM生成總結
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            summary = self.llm.chat(messages, stream=True).replace("\n", " ").strip()
            return summary
        except Exception as e:
            self.logger.error(f"生成章節 {section.get('title', '未命名章節')} 的總結失敗: {str(e)}")
            return ""
    
    def generate_questions(self, sections):
        """
        為各個章節的內容塊生成問題
        
        Args:
            sections: 章節列表
        """
        for section in sections:
            # 跳過abstract和references類型的章節
            if section.get("type") in ["abstract", "references"]:
                self.logger.info(f"跳過 {section.get('title')} 章節的問題生成")
                continue
            
            # 獲取當前章節的summary，如果沒有則使用abstract
            section_summary = section.get("summary", self.abstract_text)
            
            # 處理當前章節的內容塊
            if "content" in section:
                self._process_content_blocks(section["content"], section_summary)
            
            # 遞迴處理子章節
            if "children" in section and section["children"]:
                self.generate_questions(section["children"])
    
    def _process_content_blocks(self, content_blocks, section_summary):
        """
        處理內容塊，為每個塊生成問題
        
        Args:
            content_blocks: 內容塊列表
            section_summary: 章節摘要
        """
        # 處理連續的文字塊
        i = 0
        while i < len(content_blocks):
            block = content_blocks[i]
            
            if isinstance(block, dict):
                block_type = block.get("type")
                
                if block_type == "text" and block.get("translated_content"):
                    # 處理文字塊
                    questions = self._generate_questions_for_text(block["translated_content"], section_summary)
                    if questions:
                        block["questions"] = questions
                
                elif block_type in ["figure", "table"] and block.get("translated_caption"):
                    # 處理圖片和表格塊
                    questions = self._generate_questions_for_graph(
                        block["translated_caption"], 
                        section_summary,
                        block_type
                    )
                    if questions:
                        block["questions"] = questions
                
                elif block_type == "formula":
                    # 處理公式塊，需要獲取前後的文字上下文
                    context_before = self._find_text_context_backwards(content_blocks, i-1)
                    context_after = self._find_text_context_forwards(content_blocks, i+1)
                    
                    # 生成公式解析
                    formula_analysis = self._generate_formula_analysis(block.get("content", ""), context_before, context_after, section_summary)
                    if formula_analysis:
                        block["formula_analysis"] = formula_analysis
            
            i += 1
    
    def _generate_questions_for_text(self, text_content, section_summary):
        """
        為文字塊生成問題
        
        Args:
            text_content: 文字內容
            section_summary: 章節摘要
            
        Returns:
            list: 生成的問題列表
        """
        if not text_content:
            return []
        
        # 讀取問題生成提示詞
        system_prompt = self._read_file(os.path.join(self.base_dir,QUESTION_PROMPT_PATH))
        
        # 構建使用者提示詞
        user_prompt = f"上下文背景資訊：{section_summary}\n需要生成問題的論文段落：{text_content}\n\n請根據要求生成問題："
        
        # 調用LLM生成問題
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            questions = self.llm.chat(messages, stream=True).replace("\n", " ").strip()
            return questions
        except Exception as e:
            self.logger.error(f"生成文字塊問題失敗: {str(e)}")
            return ""
    
    def _generate_questions_for_graph(self, caption, section_summary, graph_type):
        """
        為圖片和表格塊生成問題
        
        Args:
            caption: 圖表說明
            section_summary: 章節摘要
            graph_type: 圖表類型（"figure"或"table"）
            
        Returns:
            list: 生成的問題列表
        """
        if not caption:
            return []
        
        # 讀取問題生成提示詞
        system_prompt = self._read_file(os.path.join(self.base_dir,GRAPH_QUESTION_PROMPT_PATH))
        
        # 根據圖表類型設定提示詞
        graph_type_text = "圖片" if graph_type == "figure" else "表格"
        
        # 構建使用者提示詞
        user_prompt = f"上下文背景資訊：{section_summary}\n需要生成問題的{graph_type_text}描述：{caption}\n\n請根據要求生成問題："
        
        # 調用LLM生成問題
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            questions = self.llm.chat(messages, stream=True).replace("\n", " ").strip()
            return questions
        except Exception as e:
            self.logger.error(f"生成{graph_type_text}塊問題失敗: {str(e)}")
            return ""
    
    def _find_text_context_backwards(self, content_blocks, start_index):
        """
        向後查找文字上下文（即向前查找）
        
        Args:
            content_blocks: 內容塊列表
            start_index: 開始查找的索引
            
        Returns:
            str: 找到的文字上下文，如果沒找到則返回空字串
        """
        if start_index < 0:
            return ""
            
        for i in range(start_index, -1, -1):
            if (isinstance(content_blocks[i], dict) and 
                content_blocks[i].get("type") == "text" and 
                content_blocks[i].get("translated_content")):
                return content_blocks[i].get("translated_content", "")
        
        return ""
    
    def _find_text_context_forwards(self, content_blocks, start_index):
        """
        向前查找文字上下文（即向後查找）
        
        Args:
            content_blocks: 內容塊列表
            start_index: 開始查找的索引
            
        Returns:
            str: 找到的文字上下文，如果沒找到則返回空字串
        """
        if start_index >= len(content_blocks):
            return ""
            
        for i in range(start_index, len(content_blocks)):
            if (isinstance(content_blocks[i], dict) and 
                content_blocks[i].get("type") == "text" and 
                content_blocks[i].get("translated_content")):
                return content_blocks[i].get("translated_content", "")
        
        return ""
    
    def _generate_formula_analysis(self, formula, context_before, context_after, section_summary):
        """
        為公式塊生成詳細解讀和分析。

        Args:
            formula (str): 公式內容（LaTeX 或文字形式）
            context_before (str): 公式前的文字上下文
            context_after (str): 公式後的文字上下文
            section_summary (str): 當前章節的總結資訊或摘要資訊

        Returns:
            str: 生成的公式解析文字
        """
        if not formula:
            return ""

        # 讀取系統提示詞
        system_prompt = self._read_file(os.path.join(self.base_dir,FORMULA_ANALYSIS_PROMPT_PATH))

        # 構建使用者提示詞，重點是讓大模型結合前後文以及章節摘要，來解釋公式的含義、符號意義、推導思路等
        user_prompt = f"""請對下列公式進行詳細解讀，並給出它在論文中的作用和意義。需要參考以下資訊：

        章節背景摘要：
        {section_summary}

        公式前的文字上下文：
        {context_before}

        公式：
        {formula}

        公式後的文字上下文：
        {context_after}
        
        請根據要求生成這個公式的解析，只需輸出解析文段，無需任何額外的解釋說明："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            # 調用 LLM 生成公式解析
            formula_analysis = self.llm.chat(messages, stream=True).replace("\n", " ").strip()
            return formula_analysis
        except Exception as e:
            self.logger.error(f"生成公式解析失敗: {str(e)}")
            return ""
