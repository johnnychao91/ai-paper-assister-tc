import os
import json
from pathlib import Path
import shutil
from datetime import datetime
import hashlib
from PyQt6.QtCore import QObject, pyqtSignal
from .pipeline import Pipeline
from .threads import ProcessingThread

class DataManager(QObject):
    """
    後端資料管理類別
    
    負責所有資料的載入、處理和管理，作為前端UI和資料之間的橋樑
    """
    # 定義訊號
    papers_loaded = pyqtSignal(list)                         # 論文列表載入完成訊號
    paper_content_loaded = pyqtSignal(dict, str, str)        # 論文內容載入完成訊號(paper_data, zh_content, en_content)
    loading_error = pyqtSignal(str)                          # 載入錯誤訊號
    message = pyqtSignal(str)                                # 一般訊息訊號
    processing_started = pyqtSignal(str)                     # 開始處理論文訊號
    processing_progress = pyqtSignal(str, str, float, int)   # (檔案名, 階段, 進度, 剩餘數量)
    processing_finished = pyqtSignal(str)                    # 處理完成的論文ID
    processing_error = pyqtSignal(str, str)                  # (論文ID, 錯誤訊息)
    queue_updated = pyqtSignal(list)                         # 佇列更新訊號
    
    def __init__(self, base_dir=None):
        """初始化資料管理器"""
        super().__init__()
        
        # 初始化目錄結構
        self._init_directories(base_dir)
        
        # 初始化資料狀態
        self.papers_index = []
        self.current_paper = None

        self.current_dir = os.getcwd() if os.access(os.getcwd(), os.W_OK) else self.base_dir
        self.download_dir = os.path.join(self.current_dir, "downloads")
        
        # 初始化處理佇列和狀態
        self._init_processing_queue()
        
        # 初始化處理管線
        self._init_pipeline()
    
    # ========== 初始化相關方法 ==========
    
    def _init_directories(self, base_dir):
        """初始化基礎目錄結構"""
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.output_dir = os.path.join(self.base_dir, "output")
        self.data_dir = os.path.join(self.base_dir, "data")
        
        # 確保目錄存在
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
    
    def _init_processing_queue(self):
        """初始化處理佇列和狀態"""
        self.processing_queue = []    # 待處理檔案佇列
        self.is_processing = False    # 是否正在處理
        self.is_paused = True         # 初始狀態為暫停
        self.current_thread = None    # 目前處理執行緒
    
    def _init_pipeline(self):
        """初始化處理管線"""
        self.pipeline = Pipeline()
        self.pipeline.progress_updated.connect(self.on_pipeline_progress)

    # ========== 論文存檔與載入 ==========

    def _generate_papers_index(self, paper_ids):
        """產生論文索引"""
        for paper_id in paper_ids:
            paper_info = next((paper for paper in self.papers_index if paper["id"] == paper_id), None)
            if paper_info:
                paper_info["active"] = False  # 啟用狀態
                self.papers_index.remove(paper_info) if paper_info else None
                self.new_papers_index.append(paper_info)

        if len(self.new_papers_index) != len(paper_ids):
            self.message.emit(f"警告: 產生索引時發現 {len(paper_ids) - len(self.new_papers_index)} 篇論文索引缺失")
        
        # 儲存下載索引到檔案
        index_path = os.path.join(self.download_dir, "output", "papers_index.json")
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(self.new_papers_index, f, ensure_ascii=False, indent=4)
        self.message.emit(f"論文索引已儲存到: {index_path}")

        # 更新本地索引檔案
        self._update_papers_index()

    def _download_paper(self, paper_id):
        output_path = os.path.join(self.output_dir, paper_id)
        pdf_path = os.path.join(self.data_dir, f"{paper_id}.pdf")
        if os.path.exists(output_path):
            # 移動檔案到下載目錄
            shutil.move(output_path, os.path.join(self.download_dir, "output", paper_id))
        if os.path.exists(pdf_path):
            shutil.move(pdf_path, os.path.join(self.download_dir, "data", paper_id + ".pdf"))
        
        self.message.emit(f"論文 {paper_id} 已移至下載目錄")

    def _create_archive(self, paper_ids):
        # Generate current date and hash
        current_date = datetime.now().strftime("%Y%m%d")
        hash_input = "".join(paper_ids).encode('utf-8')
        hash_suffix = hashlib.md5(hash_input).hexdigest()[:8]
        
        # Construct zip file name
        zip_file_name = f"achieved_papers_{current_date}_{hash_suffix}"
        zip_path = os.path.join(self.current_dir, zip_file_name)

        # Save hash_suffix to a file
        hash_file_path = os.path.join(self.download_dir, "hash")
        with open(hash_file_path, 'w', encoding='utf-8') as hash_file:
            hash_file.write(hash_suffix)

        # Create zip file
        shutil.make_archive(zip_path, 'zip', self.download_dir)

        return zip_path

    def _open_folder(self, folder_path):
        import subprocess
        import sys
        """開啟指定目錄"""
        try:
            if os.name == 'nt':
                # Windows系統
                subprocess.Popen(['start', folder_path], shell=True)
            elif sys.platform == 'darwin':
                # macOS系統
                subprocess.Popen(['open', folder_path])
            else:
                # Linux系統
                subprocess.Popen(['xdg-open', folder_path])
            self.message.emit(f"開啟目錄: {folder_path}")
        except Exception as e:
            self.loading_error.emit(f"開啟目錄失敗: {str(e)}")

    def download_papers(self, paper_ids):
        self.message.emit(f"正在下載 {len(paper_ids)} 篇論文...") 

        # 初始化
        if os.path.exists(self.download_dir):
            # 清空下載目錄
            shutil.rmtree(self.download_dir)
        os.makedirs(self.download_dir)
        os.makedirs(os.path.join(self.download_dir, "data"))
        os.makedirs(os.path.join(self.download_dir, "output"))

        self.new_papers_index = []

        # 產生論文索引
        self._generate_papers_index(paper_ids)

        # 下載論文
        for paper_id in paper_ids:
            self._download_paper(paper_id)
            
        # 產生壓縮檔案
        zip_path = self._create_archive(paper_ids)

        if not os.path.exists(f"{zip_path}.zip"):
            self.message.emit(f"壓縮檔案產生失敗: {zip_path}.zip")

        self.message.emit(f"壓縮檔案已產生: {zip_path}.zip")
    
        # Remove temporary download directory
        shutil.rmtree(self.download_dir, ignore_errors=True)

        # 開啟下載目錄
        self._open_folder(self.current_dir)

    def _move_paper_file(self, paper_id, source_path, target_dir):
        """移動論文檔案到指定目錄"""
        if not os.path.exists(source_path):
            self.loading_error.emit(f"來源檔案不存在: {source_path}")
            return False
        
        # 構建源和目標路徑
        pdf_source_path = os.path.join(source_path, "data", f"{paper_id}.pdf")
        pdf_target_path = os.path.join(target_dir, "data", f"{paper_id}.pdf")
        output_source_path = os.path.join(source_path,"output", paper_id)
        output_target_path = os.path.join(target_dir, "output", paper_id)

        # 檢查pdf和output檔案是否存在
        if not os.path.exists(pdf_source_path):
            self.loading_error.emit(f"PDF檔案不存在: {pdf_source_path}")
            return False
        if not os.path.exists(output_source_path):
            self.loading_error.emit(f"output目錄不存在: {output_source_path}")
            return False

        # 移動檔案
        try:
            shutil.move(pdf_source_path, pdf_target_path)
            shutil.move(output_source_path, output_target_path)
            return True
        except Exception as e:
            self.loading_error.emit(f"移動檔案失敗: {str(e)}")
            return False

    def _move_paper_files(self, load_path):
        load_data_dir = os.path.join(load_path, "data")
        load_output_dir = os.path.join(load_path, "output")
        load_json_index = os.path.join(load_output_dir, "papers_index.json")

        # check if all files exist
        if not os.path.exists(load_json_index):
            self.loading_error.emit(f"索引檔案不存在: {load_json_index}")
            return
        if not os.path.exists(load_data_dir) or not os.path.exists(load_output_dir):
            self.loading_error.emit(f"資料目錄或輸出目錄不存在: {load_data_dir} 或 {load_output_dir}")
            return

        load_paper_index = []

        # Check index file
        with open(load_json_index, 'r', encoding='utf-8') as f:
            load_paper_index = json.load(f)

        for paper in load_paper_index:
            if any(existing_paper["id"] == paper["id"] for existing_paper in self.papers_index):
                self.message.emit(f"論文 {paper['id']} 已存在，跳")
                continue
            # Move files to data directory
            _load = self._move_paper_file(paper["id"], load_path, self.base_dir)
            if not _load:
                self.loading_error.emit(f"移動檔案失敗: {paper['id']}")
                continue
            self.papers_index.append(paper)

        # 寫入索引檔案
        self._update_papers_index()


    def load_achieved_papers(self, zip_path):
        self.message.emit(f"正在載入壓縮檔案: {zip_path}")
        file_name = os.path.basename(zip_path)
        zip_code = file_name.split("_")[-1].split(".")[0]

        # 解壓縮檔案到臨時目錄
        temp_dir = os.path.join(self.base_dir, "temp")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)

        try:
            shutil.unpack_archive(zip_path, temp_dir, 'zip')
            self.message.emit(f"壓縮檔案已解壓縮到暫存目錄: {temp_dir}")
        except Exception as e:
            self.loading_error.emit(f"解壓縮檔案失敗: {str(e)}")
            return

        hash_file_path = os.path.join(temp_dir, "hash")

        if not os.path.exists(hash_file_path):
            self.loading_error.emit(f"雜湊檔案不存在: {hash_file_path}")
            return

        with open(hash_file_path, 'r', encoding='utf-8') as hash_file:
            hash_suffix = hash_file.read().strip()
            if hash_suffix != zip_code:
                self.loading_error.emit(f"雜湊值不符合: {hash_suffix} != {zip_code}")
                return

        previous_paper_count = len(self.papers_index)

        # 移動檔案到資料目錄
        self._move_paper_files(temp_dir)

        # 清理臨時目錄
        shutil.rmtree(temp_dir, ignore_errors=True)

        self.message.emit(f"暫存目錄已清理: {temp_dir}")

        # 重新載入論文索引
        self.load_papers_index()
        
        self.message.emit(f"載入完成，發現 {len(self.papers_index) - previous_paper_count} 篇新論文")
    
    # ========== 論文索引載入管理 ==========
    
    def load_papers_index(self):
        """載入論文索引資料"""
        try:
            index_path = os.path.join(self.output_dir, "papers_index.json")
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    self.papers_index = json.load(f)
                    self.papers_index.sort(key=lambda x: (0 if x.get("active", True) else 1, x.get('id', '')))
                self.message.emit(f"成功從 {index_path} 載入論文索引")
                self.papers_loaded.emit(self.papers_index)
            else:
                self.message.emit(f"索引檔案不存在: {index_path}")
        except Exception as e:
            self.loading_error.emit(f"載入論文索引失敗: {str(e)}")

    def toggle_active(self, paper_id):
        """切換論文的啟用狀態"""
        for idx, paper in enumerate(self.papers_index):
            if paper["id"] == paper_id:
                self.papers_index[idx]["active"] = not paper.get("active", True)
                self.message.emit(f"論文 {paper_id} 的啟動狀態已切換")
                break

        # 更新索引檔案
        self._update_papers_index()

    def _update_papers_index(self):
        """更新論文索引"""
        index_path = os.path.join(self.output_dir, "papers_index.json")
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(self.papers_index, f, ensure_ascii=False, indent=4)
        self.message.emit(f"索引檔案已更新: {index_path}")

        # 重新載入索引以更新UI
        self.load_papers_index()
        self.papers_loaded.emit(self.papers_index)
    
    # ========== 論文內容載入 ==========
    
    def load_paper_content(self, paper_id):
        """
        載入指定論文的內容
        
        Args:
            paper_id: 論文ID
        
        Returns:
            tuple: (paper, zh_content, en_content)
        """
        # 查找指定ID的論文
        paper = next((p for p in self.papers_index if p["id"] == paper_id), None)
        
        if not paper:
            self.loading_error.emit(f"未找到ID為{paper_id}的論文")
            return None, "", ""
        
        self.current_paper = paper
        self.message.emit(f"嘗試載入論文: {paper.get('translated_title', '')} ({paper_id})")
        
        # 獲取路徑資訊
        paths = paper.get('paths', {})
        en_path = paths.get('article_en', '')
        zh_path = paths.get('article_zh', '')
        en_full_path = os.path.join(self.output_dir, en_path)
        zh_full_path = os.path.join(self.output_dir, zh_path)
        
        # 載入中文和英文內容
        zh_content = self._load_document_content(
            zh_full_path, 
            f"# {paper.get('translated_title', '')}", 
            is_chinese=True
        )
        
        en_content = self._load_document_content(
            en_full_path, 
            f"# {paper.get('title', '')}", 
            is_chinese=False
        )
        
        # 驗證圖片路徑
        self._verify_images_path(paper)
        
        # 傳送載入完成訊號
        self.paper_content_loaded.emit(paper, zh_content, en_content)
        return paper, zh_content, en_content
    
    def _load_document_content(self, file_path, default_title, is_chinese=True):
        """
        載入文件內容
        
        Args:
            file_path: 文件路徑
            default_title: 預設標題
            is_chinese: 是否中文文件
        
        Returns:
            str: 文件內容
        """
        lang_desc = "中文" if is_chinese else "英文"
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                self.loading_error.emit(f"載入{lang_desc}檔案失敗: {str(e)}")
                return f"{default_title}\n\n載入{lang_desc}檔案時發生錯誤: {str(e)}"
        else:
            self.message.emit(f"{lang_desc}文件不存在: {file_path}")
            return f"{default_title}\n\n{lang_desc}文件不存在或無法存取。 \n路徑: {file_path}"
    
    def _verify_images_path(self, paper):
        """驗證論文圖片路徑是否存在"""
        images_path = paper.get('paths', {}).get('images', '')
        if images_path:
            full_images_path = os.path.join(self.output_dir, images_path)
            if not os.path.exists(full_images_path):
                self.message.emit(f"警告: 圖片目錄不存在: {full_images_path}")
    
    # ========== RAG樹相關 ==========
    
    def load_rag_tree(self, paper_id):
        """
        載入指定論文的RAG樹結構
        
        Args:
            paper_id: 論文ID
            
        Returns:
            dict: RAG樹結構，如果載入失敗則返回None
        """
        # 查找指定ID的論文
        paper = next((p for p in self.papers_index if p["id"] == paper_id), None)
        
        if not paper:
            self.loading_error.emit(f"未找到ID為{paper_id}的論文")
            return None
        
        # 獲取RAG樹路徑
        rag_tree_path = paper.get('paths', {}).get('rag_tree', '')
        
        if not rag_tree_path:
            self.message.emit(f"論文 {paper_id} 沒有RAG樹路徑")
            return None
        
        # 構建基於目前應用目錄的絕對路徑
        rag_tree_full_path = os.path.join(self.output_dir, rag_tree_path)
        
        self.message.emit(f"嘗試載入RAG樹: {rag_tree_full_path}")
        
        # 載入RAG樹
        if os.path.exists(rag_tree_full_path):
            try:
                with open(rag_tree_full_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.loading_error.emit(f"載入RAG樹失敗: {str(e)}")
                return None
        else:
            self.message.emit(f"RAG樹檔案不存在: {rag_tree_full_path}")
            return None

    def find_matching_content(self, text_fragment, lang="zh", element_type="text"):
        """
        在目前論文的RAG樹中查找最符合的內容
        
        Args:
            text_fragment: 要符合的文字片段
            lang: 語言代碼，'zh'表示中文，'en'表示英文
            element_type: 元素類型，'title', 'text' 或 'table'
                'text': 符合標題或文字描述
                'table': 符合表格內容
                'title': 符合章節標題
            
        Returns:
            tuple: (對應的另一種語言的內容, 符合到的元素類型)
        """
        if not self.current_paper:
            self.message.emit("沒有載入論文，無法尋找符合內容")
            return None, None
        
        # 載入RAG樹
        rag_tree = self.load_rag_tree(self.current_paper['id'])
        if not rag_tree:
            self.message.emit("無法載入RAG樹，無法尋找符合內容")
            return None, None
        
        # 特殊處理：摘要符合
        if element_type == 'title' and ("abstract" in text_fragment.lower() or "摘要" in text_fragment):
            return "abstract" if lang == "zh" else "摘要", "title"
            
        # 根據元素類型選擇搜尋策略
        if element_type == 'title':
            return self._search_title_match(rag_tree, text_fragment, lang)
        else:
            return self._search_content_match(rag_tree, text_fragment, lang, element_type)
    
    def _search_title_match(self, rag_tree, text_fragment, lang):
        """在RAG樹中搜尋標題符合"""
        source_field, target_field = self._get_field_names("document_title", lang)
        
        # 檢查文件標題
        if source_field in rag_tree and target_field in rag_tree:
            if rag_tree[source_field] == text_fragment:
                return rag_tree[target_field], 'title'
        
        # 遞迴搜尋章節標題
        def search_title_in_sections(sections):
            for section in sections:
                if source_field in section and section[source_field] == text_fragment:
                    return section[target_field], 'title'
                    
                # 遞迴搜尋子章節
                if "children" in section and section["children"]:
                    result, type_found = search_title_in_sections(section["children"])
                    if result:
                        return result, type_found
            return None, None
                
        # 开始搜索章节标题
        if "sections" in rag_tree:
            return search_title_in_sections(rag_tree["sections"])
        
        return None, None
    
    def _search_content_match(self, rag_tree, text_fragment, lang, element_type):
        """在RAG树中搜索内容匹配"""
        # 特殊处理：首先检查摘要内容
        if "abstract" in rag_tree:
            source_field, target_field = self._get_field_names("text", lang)
            
            if source_field in rag_tree["abstract"] and target_field in rag_tree["abstract"]:
                abstract_content = rag_tree["abstract"][source_field]
                if self._is_text_match(abstract_content, text_fragment):
                    return rag_tree["abstract"][target_field], "text"

        # 递归搜索章节内容
        def search_in_sections(sections):
            for section in sections:
                # 搜索当前章节的内容
                if "content" in section:
                    for node in section["content"]:
                        node_type = node.get("type", "")
                        
                        # 跳过公式节点
                        if node_type == "formula":
                            continue
                        
                        # 特殊处理表格节点
                        if node_type == "table":
                            result, type_found = self._match_table_node(node, text_fragment, lang, element_type)
                            if result:
                                return result, type_found
                        # 处理普通文本节点
                        else:
                            source_field, target_field = self._get_field_names(node_type, lang)
                            if not source_field or source_field not in node:
                                continue
                                
                            content = node[source_field]
                                    
                            # 使用改进的匹配
                            if self._is_text_match(content, text_fragment):
                                return node.get(target_field), "text"
                
                # 遞迴搜尋子章節
                if "children" in section and section["children"]:
                    result, type_found = search_in_sections(section["children"])
                    if result:
                        return result, type_found
            
            return None, None
        
        # 開始搜尋
        if "sections" in rag_tree:
            return search_in_sections(rag_tree["sections"])
        
        return None, None
    
    def _match_table_node(self, node, text_fragment, lang, element_type):
        """符合表格節點"""
        if element_type == "text":
            # 當尋找文字時，符合表格的標題/說明
            source_field, target_field = self._get_field_names("table", lang)
            if source_field in node:
                caption = node[source_field]
                if self._is_text_match(caption, text_fragment):
                    return node.get(target_field), "text"
        elif element_type == "table":
            # 當尋找表格時，符合表格內容
            content_field = "content"
            if content_field in node:
                table_content = node[content_field]
                cleaned_content = self._clean_text(table_content)
                if self._is_text_match(cleaned_content, text_fragment):
                    return node.get(content_field), "table"
        return None, None
    
    def _get_field_names(self, node_type, lang):
        """獲取欄位名稱"""
        if node_type == "text":
            return ("translated_content" if lang == "zh" else "content", 
                    "content" if lang == "zh" else "translated_content")
        elif node_type in ["figure", "table"]:
            return ("translated_caption" if lang == "zh" else "caption", 
                    "caption" if lang == "zh" else "translated_caption")
        elif node_type == "formula":
            return "content", "content"
        elif node_type in ["section_title", "document_title"]:
            return ("translated_title" if lang == "zh" else "title", 
                    "title" if lang == "zh" else "translated_title")
        return None, None
    
    def _clean_text(self, text):
        """清理HTML标签和LaTeX公式"""
        if not text:
            return ""
        import re
        
        # 先移除HTML标签
        text = re.sub(r'</?[a-zA-Z][a-zA-Z0-9]*(\s+[^>]*)?>', ' ', text)
        
        # 移除行间公式 ($$...$$)
        text = re.sub(r'\$\$[^$]*\$\$', ' ', text)
        
        # 移除行内公式 ($...$)
        text = re.sub(r'\$[^$]*\$', ' ', text)
        
        # 移除其他可能的LaTeX表示 (\(...\) 和 \[...\])
        text = re.sub(r'\\[\(\[][^\\]*\\[\)\]]', ' ', text)
        
        # 清理多余空格
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _is_text_match(self, s1, s2):
        """检查两个文本是否互相包含（子串关系）"""
        if not s1 or not s2:
            return False
        
        # 清理并标准化两个文本
        def normalize_text(text):
            # 先清理LaTeX和HTML
            cleaned = self._clean_text(text)
            import re
            # 保留中文、英文字母和数字，移除所有其他字符
            normalized = re.sub(r'[^\u4e00-\u9fff\w\d]', '', cleaned)
            return normalized.lower()  # 转为小写以忽略大小写差异
        
        # 获取标准化后的全文
        norm_s1 = normalize_text(s1)
        norm_s2 = normalize_text(s2)
        
        # 检查是否存在子串关系（双向检查）
        return norm_s1 in norm_s2 or norm_s2 in norm_s1
    
    # ========== 论文处理队列管理 ==========
    
    def initialize_processing_system(self):
        """初始化处理系统，检查未处理文件并构建队列"""
        # 加载现有索引
        self.load_papers_index()
        
        # 初始化處理管線（如果尚未初始化）
        if self.pipeline is None:
            self._init_pipeline()
        
        # 掃描資料目錄中的PDF檔案
        self.scan_for_unprocessed_files()
    
    def scan_for_unprocessed_files(self):
        """掃描資料目錄，查找未處理或處理不完整的PDF檔案"""
        # 清空現有佇列
        self.processing_queue = []
        
        # 獲取已處理論文的ID列表
        processed_ids = {paper['id'] for paper in self.papers_index}
        
        # 掃描資料目錄中的PDF檔案
        pdf_files = [f for f in os.listdir(self.data_dir) if f.lower().endswith('.pdf')]
        
        # 對於每個PDF檔案，檢查是否已經處理
        for pdf_file in pdf_files:
            paper_id = os.path.splitext(pdf_file)[0]  # 不包含副檔名的檔案名作為ID
            
            # 檢查是否已經在索引中並且處理完整
            if paper_id not in processed_ids:
                # 新檔案，添加到佇列
                self.processing_queue.append({
                    'id': paper_id,
                    'path': os.path.join(self.data_dir, pdf_file),
                    'status': 'pending',
                    'missing_steps': ['all'],  # 全部步驟都缺失
                })
            else:
                # 檢查是否所有必要檔案都存在
                paper_info = next((p for p in self.papers_index if p['id'] == paper_id), None)
                missing_paths = self._check_missing_paths(paper_info)
                
                if missing_paths:
                    # 處理不完整，添加到佇列
                    self.processing_queue.append({
                        'id': paper_id,
                        'path': os.path.join(self.data_dir, pdf_file),
                        'status': 'incomplete',
                        'missing_steps': missing_paths,
                    })
        
        # 按缺失步驟數排序（缺失少的在前）
        self.processing_queue.sort(key=lambda x: len(x.get('missing_steps', [])))
        
        # 發射佇列更新訊號
        self.queue_updated.emit(self.processing_queue)
        
        self.message.emit(f"掃描完成，發現 {len(self.processing_queue)} 個待處理文件")
    
    def _check_missing_paths(self, paper_info):
        """检查论文是否缺少关键文件，返回缺失的文件类型列表"""
        if not paper_info:
            return ['all']
        
        missing = []
        paths = paper_info.get('paths', {})
        
        # 检查关键文件
        key_files = {
            'article_en': '英文文章',
            'article_zh': '中文文章',
            'rag_tree': 'RAG樹結構'
        }
        
        for key, desc in key_files.items():
            if key not in paths or not os.path.exists(os.path.join(self.output_dir, paths[key])):
                missing.append(key)
        
        return missing
    
    def upload_file(self, file_path):
        """上传文件到数据目录并添加到处理队列"""
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            # 提取文件名作为论文ID
            file_name = os.path.basename(file_path)
            paper_id = os.path.splitext(file_name)[0]
            
            # 目标路径
            target_path = os.path.join(self.data_dir, file_name)
            
            # 复制文件到数据目录（如果需要）
            self._copy_file_to_data_dir(file_path, target_path)
            
            # 更新处理队列
            self._update_processing_queue(paper_id, target_path)
            
            # 如果不是暂停状态，开始处理
            if not self.is_paused:
                self.process_next_in_queue()
            
            return True
        except Exception as e:
            self.loading_error.emit(f"上傳檔案失敗: {str(e)}")
            return False
    
    def _copy_file_to_data_dir(self, file_path, target_path):
        """複製檔案到資料目錄"""
        # 標準化路徑進行比較，檢查是否是同一檔案
        try:
            is_same_file = os.path.samefile(file_path, target_path)
        except:
            # 如果samefile失敗（例如檔案不存在），則使用normpath進行比較
            is_same_file = os.path.normpath(file_path) == os.path.normpath(target_path)
        
        # 如果不是同一檔案，才進行複製
        if not is_same_file:
            try:
                shutil.copy2(file_path, target_path)
                self.message.emit(f"檔案已複製到資料目錄: {target_path}")
            except Exception as e:
                self.loading_error.emit(f"複製檔案時發生錯誤: {str(e)}")
                # 繼續執行，假設檔案已存在或其他原因可以忽略
        else:
            self.message.emit(f"檔案已在資料目錄中: {target_path}")
    
    def _update_processing_queue(self, paper_id, file_path):
        """更新處理佇列"""
        # 檢查是否已在佇列中
        existing_item = next((item for item in self.processing_queue if item['id'] == paper_id), None)
        
        if existing_item:
            # 已在佇列中，更新狀態並移至隊首
            existing_item['status'] = 'pending'
            existing_item['path'] = file_path
            existing_item['priority'] = 1  # 確保高優先級
            
            # 將項目移到佇列開頭
            self.processing_queue.remove(existing_item)
            self.processing_queue.insert(0, existing_item)
        else:
            # 添加到佇列開頭（而不是末尾）
            self.processing_queue.insert(0, {
                'id': paper_id,
                'path': file_path,
                'status': 'pending',
                'missing_steps': ['all'],
                'priority': 1  # 添加一個高優先級標記
            })
        
        # 更新佇列
        self.queue_updated.emit(self.processing_queue)
    
    def process_next_in_queue(self):
        """处理队列中的下一个文件"""
        if self.is_paused or self.is_processing or not self.processing_queue:
            return False
        
        # 获取队列中第一个待处理项
        next_item = self.processing_queue[0]
        
        # 标记为正在处理
        self.is_processing = True
        next_item['status'] = 'processing'
        
        # 更新队列状态
        self.queue_updated.emit(self.processing_queue)
        
        # 发出开始处理信号
        self.processing_started.emit(next_item['id'])
        
        # 创建并启动处理线程
        self.current_thread = ProcessingThread(
            self.pipeline, next_item['path'], self.output_dir
        )
        self.current_thread.processing_finished.connect(self.on_processing_finished)
        self.current_thread.processing_error.connect(self.on_processing_error)
        self.current_thread.start()
        
        return True
    
    # ========== 处理线程回调 ==========
    
    def on_thread_progress(self, file_name, stage, progress, remaining):
        """处理线程进度更新回调"""
        self.processing_progress.emit(file_name, stage, progress, remaining)
    
    def on_pipeline_progress(self, stage_info):
        """管线进度更新回调"""
        # 构建当前处理的文件名
        if self.is_processing and self.processing_queue:
            file_name = os.path.basename(self.processing_queue[0]['path'])
            stage = stage_info.get('stage_name', '未知階段')
            progress = stage_info.get('progress', 0)
            remaining = len(self.processing_queue) - 1
            
            # 发送进度更新信号
            self.processing_progress.emit(file_name, stage, progress, remaining)
    
    def on_processing_finished(self, paper_id):
        """处理完成回调"""
        self.message.emit(f"論文處理完成: {paper_id}")
        
        # 標記處理完成
        self.is_processing = False
        
        # 從佇列中移除已處理項
        if self.processing_queue:
            self.processing_queue.pop(0)
        
        # 傳送處理完成訊號
        self.processing_finished.emit(paper_id)
        
        # 添加向量庫到RAG檢索器
        self._add_paper_vector_store(paper_id)
        
        # 更新佇列狀態
        self.queue_updated.emit(self.processing_queue)
        
        # 重新載入論文索引
        self.load_papers_index()
        
        # 繼續處理下一個（如果未暫停）
        if not self.is_paused:
            self.process_next_in_queue()

    def _add_paper_vector_store(self, paper_id):
        """將處理完成的論文向量庫添加到RAG檢索器"""
        try:
            # 獲取論文資料
            paper = next((p for p in self.papers_index if p["id"] == paper_id), None)
            if not paper:
                self.message.emit(f"[WARNING] 找不到ID為{paper_id}的論文，無法新增向量庫")
                return False
                
            # 獲取向量庫路徑
            vector_store_path = paper.get('paths', {}).get('rag_vector_store')
            if not vector_store_path:
                self.message.emit(f"[WARNING] 論文{paper_id}沒有向量庫路徑")
                return False
                
            # 構建完整路徑
            full_path = os.path.join(self.output_dir, vector_store_path)
            
            # 驗證路徑是否存在
            if not os.path.exists(full_path):
                self.message.emit(f"[WARNING] 論文{paper_id}的向量庫路徑不存在: {full_path}")
                return False
            
            # 透過AI管理器添加向量庫
            if hasattr(self, 'ai_manager') and self.ai_manager:
                success = self.ai_manager.add_paper_vector_store(paper_id, full_path)
                if success:
                    self.message.emit(f"已加入論文 {paper_id} 的向量庫到檢索系統")
                else:
                    self.message.emit(f"[WARNING] 新增論文 {paper_id} 的向量庫失敗")
                return success
            else:
                self.message.emit(f"[WARNING] AI管理器未初始化，無法新增向量庫")
                return False
                
        except Exception as e:
            self.message.emit(f"[ERROR] 新增向量庫失敗: {str(e)}")
            return False
    
    def on_processing_error(self, paper_id, error_msg):
        """处理错误回调"""
        # 由于我们可能通过强制终止线程导致错误，需要检查处理状态
        if not self.is_processing:
            # 线程已被手动停止，无需报告错误
            return
            
        self.loading_error.emit(f"處理論文 {paper_id} 時發生錯誤: {error_msg}")
        
        # 標記處理結束
        self.is_processing = False
        
        # 從佇列中移除錯誤項
        if self.processing_queue and len(self.processing_queue) > 0:
            self.processing_queue[0]['status'] = 'error'
            self.processing_queue[0]['error_msg'] = error_msg
            self.processing_queue.pop(0)
        
        # 更新佇列狀態
        self.queue_updated.emit(self.processing_queue)
        
        # 繼續處理下一個（如果未暫停）
        if not self.is_paused:
            self.process_next_in_queue()
    
    # ========== 佇列控制 ==========
    
    def pause_processing(self):
        """暫停處理佇列"""
        self.is_paused = True
        self.message.emit("處理佇列已暫停")
        
        # 立即停止目前正在執行的執行緒
        if self.current_thread and self.current_thread.isRunning():
            self.current_thread.stop()  # 立即終止執行緒
            self.is_processing = False  # 重置處理狀態
            
            # 如果佇列不為空，將目前任務重置為待處理狀態
            if self.processing_queue and len(self.processing_queue) > 0:
                current_item = self.processing_queue[0]
                current_item['status'] = 'pending'
                self.message.emit(f"已停止處理論文: {current_item['id']}")
            
            # 更新佇列狀態
            self.queue_updated.emit(self.processing_queue)
    
    def resume_processing(self):
        """繼續處理佇列"""
        self.is_paused = False
        self.message.emit("處理佇列已繼續")
        
        # 如果沒有正在進行的處理，嘗試處理下一個
        if not self.is_processing:
            self.process_next_in_queue()
    
    def set_ai_manager(self, ai_manager):
        """設定AI管理器引用"""
        self.ai_manager = ai_manager