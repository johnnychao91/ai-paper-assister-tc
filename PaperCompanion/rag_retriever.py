import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from langchain_community.vectorstores.faiss import FAISS
from .config import EmbeddingModel
from PyQt6.QtCore import QObject, pyqtSignal, QThread

class VectorLoadingThread(QThread):
    """用於在背景載入向量庫的執行緒"""
    loading_finished = pyqtSignal(dict)  # 載入完成信號，攜帶paper_id到路徑的映射
    
    def __init__(self, base_path):
        super().__init__()
        self.base_path = base_path
    
    def run(self):
        """執行向量庫索引載入"""
        paper_vector_paths = {}
        
        try:
            # 建構索引檔案路徑
            index_path = Path(self.base_path) / "papers_index.json"
            if not index_path.exists():
                print(f"[WARNING] 論文索引不存在: {index_path}")
                self.loading_finished.emit({})
                return
                
            # 載入索引
            with open(index_path, 'r', encoding='utf-8') as f:
                papers_index = json.load(f)
                
            # 遍歷所有論文，記錄其向量庫路徑
            for paper in papers_index:
                paper_id = paper.get('id')
                vector_store_path = paper.get('paths', {}).get('rag_vector_store')
                
                if paper_id and vector_store_path:
                    # 儲存論文ID和向量庫路徑的映射
                    full_path = str(Path(self.base_path) / vector_store_path)
                    paper_vector_paths[paper_id] = full_path
                    
            print(f"[INFO] 預先載入了 {len(paper_vector_paths)} 篇論文的向量庫路徑")
            
            # 發出載入完成信號
            self.loading_finished.emit(paper_vector_paths)
            
        except Exception as e:
            print(f"[ERROR] 預先載入論文索引失敗: {str(e)}")
            self.loading_finished.emit({})


class RagRetriever(QObject):
    """RAG檢索器，用於從向量庫中檢索相關內容"""
    
    loading_complete = pyqtSignal(bool)  # 載入完成信號
    
    def __init__(self, base_path=None):
        """
        初始化RAG檢索器並預載入所有論文的向量庫路徑
        
        Args:
            base_path: 基礎路徑，如果提供則自動預載入所有論文
        """
        super().__init__()
        self.vector_stores = {}  # 快取載入過的向量庫: {paper_id: vector_store}
        self.paper_vector_paths = {}  # 論文ID到向量庫路徑的映射: {paper_id: vector_path}
        self.base_path = base_path
        self.loading_thread = None
        self.rag_trees = {}  # 快取載入過的rag_tree: {paper_id: rag_tree}
        
        # 如果提供了base_path，則預載入所有論文的索引
        if base_path:
            self.preload_all_papers(base_path)

    def preload_all_papers(self, base_path):
        """
        在背景執行緒中預載入所有論文的索引和向量庫路徑
        
        Args:
            base_path: 基礎路徑
        """
        self.base_path = base_path
        print(f"[INFO] 開始在背景載入論文向量庫索引: {base_path}")
        
        # 建立並啟動載入執行緒
        self.loading_thread = VectorLoadingThread(base_path)
        self.loading_thread.loading_finished.connect(self._on_loading_finished)
        self.loading_thread.start()

    def _on_loading_finished(self, paper_vector_paths):
        """處理向量庫路徑載入完成的回調"""
        self.paper_vector_paths = paper_vector_paths
        print(f"[INFO] 完成論文向量庫索引載入，共載入 {len(paper_vector_paths)} 個論文索引")
        self.loading_complete.emit(len(paper_vector_paths) > 0)

    def add_paper(self, paper_id: str, vector_store_path: str) -> bool:
        """
        新增新論文的向量庫路徑並嘗試載入
        
        Args:
            paper_id: 論文ID
            vector_store_path: 向量庫路徑
            
        Returns:
            bool: 新增成功返回True，否則返回False
        """
        try:
            # 新增論文ID和向量庫路徑的映射
            self.paper_vector_paths[paper_id] = vector_store_path
            print(f"[INFO] 新增論文向量庫: {paper_id} -> {vector_store_path}")
            
            # 嘗試載入向量庫
            vector_store = self.load_vector_store(vector_store_path)
            if vector_store:
                self.vector_stores[paper_id] = vector_store
                print(f"[INFO] 成功載入新論文 {paper_id} 的向量庫")
                return True
            else:
                print(f"[WARNING] 無法載入新論文 {paper_id} 的向量庫")
                return False
        except Exception as e:
            print(f"[ERROR] 新增論文 {paper_id} 失敗: {str(e)}")
            return False

    def load_vector_store(self, vector_store_path: str) -> Optional[FAISS]:
        """
        載入向量庫
        
        Args:
            vector_store_path: 向量庫路徑
            
        Returns:
            Optional[FAISS]: 向量庫物件，載入失敗則返回None
        """
        # 檢查路徑是否存在
        path = Path(vector_store_path)
        if not path.exists():
            print(f"[ERROR] 向量庫路徑不存在: {vector_store_path}")
            return None
            
        # 檢查索引檔案是否存在
        if not (path / "index.faiss").exists():
            print(f"[ERROR] 向量庫索引檔不存在: {vector_store_path}/index.faiss")
            return None
            
        try:
            # 載入向量庫
            vector_store = FAISS.load_local(
                vector_store_path,
                EmbeddingModel.get_instance(),
                allow_dangerous_deserialization=True
            )
            
            print(f"[INFO] 成功載入向量庫: {vector_store_path}")
            return vector_store
        except Exception as e:
            print(f"[ERROR] 載入向量庫失敗: {str(e)}")
            return None
            
    def load_rag_tree(self, paper_id: str) -> Dict:
        """
        載入論文的rag_tree
        
        Args:
            paper_id: 論文ID
            
        Returns:
            Dict: 論文的rag_tree結構
        """
        if paper_id in self.rag_trees:
            return self.rag_trees[paper_id]
            
        try:
            # 建構rag_tree路徑
            if not self.base_path:
                print("[ERROR] 未設定基礎路徑，無法載入rag_tree")
                return {}
                
            # 從索引檔案查找rag_tree路徑
            index_path = Path(self.base_path) / "papers_index.json"
            if not index_path.exists():
                print(f"[ERROR] 論文索引不存在: {index_path}")
                return {}
                
            # 載入索引
            with open(index_path, 'r', encoding='utf-8') as f:
                papers_index = json.load(f)
            
            # 查找論文
            rag_tree_path = None
            for paper in papers_index:
                if paper.get('id') == paper_id:
                    rag_tree_path = paper.get('paths', {}).get('rag_tree')
                    break
            
            if not rag_tree_path:
                print(f"[ERROR] 未找到論文 {paper_id} 的rag_tree路徑")
                return {}
                
            # 載入rag_tree
            full_path = Path(self.base_path) / rag_tree_path
            if not full_path.exists():
                print(f"[ERROR] rag_tree檔案不存在: {full_path}")
                return {}
                
            with open(full_path, 'r', encoding='utf-8') as f:
                rag_tree = json.load(f)
                
            # 快取rag_tree
            self.rag_trees[paper_id] = rag_tree
            print(f"[INFO] 成功載入論文 {paper_id} 的rag_tree")
            return rag_tree
            
        except Exception as e:
            print(f"[ERROR] 載入rag_tree失敗: {str(e)}")
            return {}

    def retrieve(self, query: str, paper_id: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        從指定論文的向量庫中檢索相關內容
        
        Args:
            query: 查詢文字
            paper_id: 論文ID
            top_k: 返回結果數量
            
        Returns:
            List[Tuple[str, float]]: 檢索結果列表，每個元素為(文字內容, 分數)
        """
        # 獲取該論文的向量庫
        vector_store = None
        
        # 檢查是否已載入
        if paper_id in self.vector_stores:
            vector_store = self.vector_stores[paper_id]
        else:
            # 嘗試載入
            if paper_id in self.paper_vector_paths:
                vector_store_path = self.paper_vector_paths[paper_id]
                vector_store = self.load_vector_store(vector_store_path)
                if vector_store:
                    self.vector_stores[paper_id] = vector_store
        
        if not vector_store:
            print(f"[WARNING] 未能取得論文 {paper_id} 的向量庫")
            return []
            
        try:
            # 執行檢索
            docs_with_scores = vector_store.similarity_search_with_score(
                query=query,
                k=top_k
            )
            
            # 格式化結果
            results = [(doc.page_content, score) for doc, score in docs_with_scores]
            
            print(f"[INFO] 從論文 {paper_id} 檢索到 {len(results)} 筆結果")
            return results
        except Exception as e:
            print(f"[ERROR] 檢索失敗: {str(e)}")
            return []

    def is_ready(self):
        """檢查向量庫是否已載入完成"""
        return bool(self.paper_vector_paths)

    def retrieve_with_context(self, query: str, paper_id: str, top_k: int = 5) -> Tuple[str, Dict]:
        """
        從指定論文的向量庫中檢索相關內容並保留其在原文中的結構
        
        Args:
            query: 查詢文字
            paper_id: 論文ID
            top_k: 返回結果數量
            
        Returns:
            Tuple[str, Dict]: (結構化的檢索結果, 最佳滾動定位資訊)
        """
        # 首先檢查是否已完成載入
        if not self.is_ready():
            print("[WARNING] 向量庫索引尚未載入完成，無法執行檢索")
            return "", None

        # 獲取該論文的向量庫
        vector_store = None
        
        # 檢查是否已載入
        if paper_id in self.vector_stores:
            vector_store = self.vector_stores[paper_id]
        else:
            # 嘗試載入
            if paper_id in self.paper_vector_paths:
                vector_store_path = self.paper_vector_paths[paper_id]
                vector_store = self.load_vector_store(vector_store_path)
                if vector_store:
                    self.vector_stores[paper_id] = vector_store
        
        if not vector_store:
            print(f"[WARNING] 未能取得論文 {paper_id} 的向量庫")
            return "", None
            
        try:
            # 載入rag_tree
            rag_tree = self.load_rag_tree(paper_id)
            if not rag_tree:
                print(f"[WARNING] 未能載入論文 {paper_id} 的rag_tree")
                return "", None
                
            # 移除重試機制，直接執行檢索
            try:
                # 執行檢索
                docs_with_scores = vector_store.similarity_search_with_score(
                    query=query,
                    k=top_k
                )
            except Exception as e:
                print(f"[ERROR] 檢索失敗: {str(e)}")
                return "", None

            # 過濾分數大於0.6的結果 - 保持原有檢索邏輯
            filtered_docs = [(doc, score) for doc, score in docs_with_scores if score > 0.6]

            if not filtered_docs:
                print(f"[INFO] 未找到相關分數大於0.6的內容，回傳空結果")
                return "", None  # 直接返回空字串，而不是使用備選檢索
                
            # 從metadata中提取路徑並通過key_map查找對應內容
            section_paths = []
            # 保存第一個文檔的分數（最高分）用於定位判斷
            first_doc_score = filtered_docs[0][1] if filtered_docs else 0
            
            for doc, score in filtered_docs:
                if 'Header' in doc.metadata:
                    header_key = doc.metadata['Header']
                    if header_key in rag_tree.get('key_map', {}):
                        section_paths.append(rag_tree['key_map'][header_key])
            
            if not section_paths:
                print("[WARNING] 未找到對應的section路徑")
                return "", None  # 同樣直接返回空字串
                
            # 建立檢索到的章節內容
            retrieved_sections = {}
            for path in section_paths:
                # 解析路徑取得節點
                node = self._get_node_from_path(rag_tree, path)
                if node:
                    # 使用路徑作為鍵，避免重複
                    retrieved_sections[path] = node
                    
                    # 查找緊鄰的公式區塊
                    self._add_adjacent_formulas(rag_tree, path, retrieved_sections)
            
            # 初始化滾動資訊為None
            scroll_info = None
            
            # 只有當第一個檢索結果分數大於0.65時才產生滾動資訊
            if first_doc_score > 0.65 and section_paths:
                first_path = section_paths[0]
                first_node = retrieved_sections.get(first_path)
                if first_node:
                    scroll_info = self._create_scroll_info(first_path, first_node, rag_tree)
                    print(f"[INFO] 啟動定位功能，分數: {first_doc_score:.4f}")
            else:
                print(f"[INFO] 不啟動定位功能，首個結果分數: {first_doc_score:.4f}")
                
            # 按照路徑順序排序
            sorted_paths = sorted(retrieved_sections.keys())
            
            # 建立最終結果字串
            result_parts = ["以下是論文中與您問題最相關的內容:"]

            for path in sorted_paths:
                node = retrieved_sections[path]
                # 建立完整的路徑層次標題
                section_title = self._build_section_title(rag_tree, path)
                
                result_parts.append(f"\n## {section_title}")
                
                # 新增節點內容
                if node.get('type') == 'text':
                    result_parts.append(node.get('translated_content', '') or node.get('content', ''))
                elif node.get('type') == 'formula':
                    result_parts.append(node.get('content', ''))
                    if 'formula_analysis' in node:
                        result_parts.append(f"公式解釋: {node['formula_analysis']}")
                elif node.get('type') == 'figure':
                    caption = node.get('translated_caption', '') or node.get('caption', '')
                    if caption:
                        result_parts.append(f"圖片: {caption}")
                elif node.get('type') == 'table':
                    content = node.get('content', '')
                    caption = node.get('translated_caption', '') or node.get('caption', '')
                    if content:
                        result_parts.append(content)
                    if caption:
                        result_parts.append(f"表格: {caption}")
                elif 'summary' in node:
                    result_parts.append(f"摘要: {node['summary']}")

            return "\n\n".join(result_parts), scroll_info
            
        except Exception as e:
            print(f"[ERROR] 結構化檢索失敗: {str(e)}")
            return "", None  # 發生異常也直接返回空字串和None

    def _create_scroll_info(self, path: str, node: Dict, rag_tree: Dict) -> Dict:
        """
        建立滾動定位資訊
        
        Args:
            path: 節點路徑
            node: 節點資料
            rag_tree: RAG樹結構
            
        Returns:
            Dict: 滾動定位資訊
        """
        # 預設滾動資訊
        scroll_info = {
            'is_title': False,  # 是否是標題
            'zh_content': '',   # 中文內容
            'en_content': '',   # 英文內容
            'node_type': node.get('type', 'unknown')  # 節點類型
        }
        
        # 處理節點類型
        if 'type' not in node:
            # 可能是章節節點，需要找到標題
            if path.startswith('/sections/'):
                parts = path.split('/')
                # 對於章節節點，設定為標題類型
                scroll_info['is_title'] = True
                
                # 取得章節標題
                if 'title' in node:
                    scroll_info['en_content'] = node['title']
                if 'translated_title' in node:
                    scroll_info['zh_content'] = node['translated_title']
                
                return scroll_info
        
        # 根據節點類型設定內容
        if node.get('type') == 'text':
            scroll_info['en_content'] = node.get('content', '')
            scroll_info['zh_content'] = node.get('translated_content', '')
        elif node.get('type') == 'figure' or node.get('type') == 'table':
            scroll_info['en_content'] = node.get('caption', '')
            scroll_info['zh_content'] = node.get('translated_caption', '')
        elif node.get('type') == 'formula':
            # 公式內容在中英文中相同
            scroll_info['en_content'] = node.get('content', '')
            scroll_info['zh_content'] = node.get('content', '')
        
        return scroll_info

    def _get_node_from_path(self, tree: Dict, path: str) -> Dict:
        """
        從路徑取得節點內容
        
        Args:
            tree: rag_tree結構
            path: 節點路徑，如 /sections/0/content/2
            
        Returns:
            Dict: 節點內容
        """
        try:
            # 移除開頭的斜線
            if path.startswith('/'):
                path = path[1:]
                
            # 分割路徑
            parts = path.split('/')
            
            # 從樹的根開始遍歷
            node = tree
            for part in parts:
                if part.isdigit():
                    part = int(part)
                if isinstance(node, dict) and part in node:
                    node = node[part]
                elif isinstance(node, list) and isinstance(part, int) and part < len(node):
                    node = node[part]
                else:
                    return {}
            
            return node
        except Exception as e:
            print(f"[ERROR] 取得節點失敗: {str(e)}")
            return {}
    
    def _add_adjacent_formulas(self, tree: Dict, path: str, retrieved_sections: Dict) -> None:
        """
        新增緊鄰的公式區塊
        
        Args:
            tree: rag_tree結構
            path: 目前節點路徑
            retrieved_sections: 已檢索的章節字典
        """
        try:
            # 解析路徑
            if not path or not path.startswith('/'):
                return
                
            parts = path.split('/')
            # 處理如 /sections/0/content/2 格式的路徑
            if len(parts) >= 5 and parts[-2] == 'content':
                current_index = int(parts[-1])
                base_path = '/'.join(parts[:-1])
                
                # 檢查前面的區塊
                if current_index > 0:
                    prev_path = f"{base_path}/{current_index - 1}"
                    prev_node = self._get_node_from_path(tree, prev_path)
                    
                    if prev_node.get('type') == 'formula':
                        retrieved_sections[prev_path] = prev_node
                
                # 檢查後面的區塊
                next_path = f"{base_path}/{current_index + 1}"
                next_node = self._get_node_from_path(tree, next_path)
                
                if next_node and next_node.get('type') == 'formula':
                    retrieved_sections[next_path] = next_node
        except Exception as e:
            print(f"[ERROR] 新增相鄰公式區塊失敗: {str(e)}")
    
    def _build_section_title(self, tree: Dict, path: str) -> str:
        """
        建立完整的章節標題
        
        Args:
            tree: rag_tree結構
            path: 節點路徑
            
        Returns:
            str: 完整的章節標題
        """
        try:
            # 移除開頭的斜線
            if path.startswith('/'):
                path = path[1:]
                
            # 分割路徑
            parts = path.split('/')
            
            # 對於sections路徑，建立章節標題
            if len(parts) >= 2 and parts[0] == 'sections':
                section_index = int(parts[1])
                
                # 取得章節
                if 'sections' in tree and section_index < len(tree['sections']):
                    section = tree['sections'][section_index]
                    
                    # 優先使用翻譯標題，否則使用原標題
                    title = section.get('translated_title', '') or section.get('title', '')
                    
                    # 如果有子章節
                    if len(parts) >= 4 and parts[2] == 'children':
                        child_index = int(parts[3])
                        
                        # 取得子章節
                        if 'children' in section and child_index < len(section['children']):
                            child = section['children'][child_index]
                            
                            # 子章節標題
                            child_title = child.get('translated_title', '') or child.get('title', '')
                            
                            if child_title:
                                return f"{title} > {child_title}"
                    
                    return title
            
            # 如果無法建立標題，返回簡單路徑描述
            return f"章節 {path}"
        except Exception as e:
            print(f"[ERROR] 建置章節標題失敗: {str(e)}")
            return f"章節 {path}"