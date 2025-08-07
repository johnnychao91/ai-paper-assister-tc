import json
import logging
from pathlib import Path
from typing import Tuple, Dict, List, Any
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_community.vectorstores.faiss import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from ..config import EmbeddingModel

class RagProcessor:
    """RAG 處理器：將 JSON 轉換為 Markdown 和符合檢索需求的JSON樹結構，並生成向量庫"""

    def __init__(self):
        """初始化 RAG 處理器"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def process(self, input_path: str, output_md_path: str, output_tree_json_path: str, vector_store_path: str) -> Tuple[str, str, str]:
        """處理 JSON 檔案，生成 Markdown、JSON以及向量庫

        Args:
            input_path: 輸入JSON檔案路徑
            output_md_path: 輸出的Markdown檔案路徑
            output_tree_json_path: 輸出的樹結構JSON檔案路徑
            vector_store_path: 向量庫存儲路徑

        Returns:
            Tuple[str, str, str]: Markdown檔案路徑, JSON檔案路徑, 向量庫路徑
        """
        self.logger.info(f"開始處理 RAG 資料: {input_path}")

        try:
            with open(input_path, "r", encoding="utf-8") as f:
                paper_data = json.load(f)

            # 提取摘要並放入 summary 字段
            abstract_content = self._extract_abstract_summary(paper_data.get("sections", []))
            abstract_content = self._extract_abstract_summary(paper_data.get("sections", []))
            paper_data["abstract"] = {
                "content": abstract_content.get("content", ""),
                "translated_content": abstract_content.get("translated_content", "")
            }
            
            # 移除 sections 中的 abstract 和 references
            paper_data["sections"] = self._filter_sections(paper_data.get("sections", []))
            
            # 重構樹結構
            paper_data = self._restructure_tree(paper_data)
            
            # 生成樹結構 JSON
            with open(output_tree_json_path, "w", encoding="utf-8") as f:
                json.dump(paper_data, f, ensure_ascii=False, indent=2)

            # 生成 Markdown 檔案
            self._generate_markdown(paper_data, output_md_path)

            # 為 Markdown 檔案建立向量庫
            self._create_vector_store(output_md_path, vector_store_path)

            self.logger.info("RAG 資料處理完成")
            return output_md_path, output_tree_json_path, vector_store_path

        except Exception as e:
            self.logger.error(f"RAG 處理失敗: {str(e)}", exc_info=True)
            raise

    def _create_vector_store(self, md_path: str, vector_store_path: str) -> str:
        """
        為 Markdown 檔案建立向量庫

        Args:
            md_path: Markdown 檔案路徑
            vector_store_path: 向量庫存儲路徑

        Returns:
            str: 向量庫路徑
        """
        self.logger.info(f"開始為 Markdown 建立向量庫: {md_path}")
        
        # 確保向量庫存儲路徑存在
        vector_store_path_obj = Path(vector_store_path)
        vector_store_path_obj.mkdir(parents=True, exist_ok=True)
        
        # 讀取 Markdown 檔案
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 使用 Markdown 標題分割文檔
        # 按一級標題分割，這些通常是節點的 key
        headers_to_split_on = [("#", "Header")]
        md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        docs = md_splitter.split_text(content)
        
        self.logger.info(f"分割後得到 {len(docs)} 個文檔片段")
        
        # 建立向量存儲
        vector_store = FAISS.from_documents(
            documents=docs,
            embedding=EmbeddingModel.get_instance(),
            distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT
        )
        
        # 保存向量存儲
        vector_store.save_local(str(vector_store_path_obj))
        
        self.logger.info(f"向量庫建立完成: {vector_store_path_obj}")
        return str(vector_store_path_obj)

    def _extract_abstract_summary(self, sections: List[Dict]) -> Dict[str, str]:
        """提取摘要，同時返回原文和翻譯內容"""
        for section in sections:
            if section.get("type") == "abstract":
                content = []
                translated_content = []
                for item in section.get("content", []):
                    if isinstance(item, dict) and item.get("type") == "text":
                        content.append(item.get("content", ""))
                        translated_content.append(item.get("translated_content", ""))
                return {
                    "content": "\n".join(content),
                    "translated_content": "\n".join(translated_content)
                }
        return {"content": "", "translated_content": ""}

    def _filter_sections(self, sections: List[Dict]) -> List[Dict]:
        """過濾掉 abstract 和 references 類型的章節"""
        filtered_sections = []
        for section in sections:
            if section.get("type") != "abstract" and section.get("type") != "references":
                filtered_sections.append(section)
        return filtered_sections

    def _restructure_tree(self, paper_data: Dict) -> Dict:
        """重構樹結構，移除不需要的字段，重新標註索引和層級"""
        # 重新標註節點的 level 和 index
        restructured_sections = self._restructure_sections(paper_data.get("sections", []), level=1)
        
        # 重構後的 paper_data
        restructured_paper = {
            "title": paper_data.get("title", ""),
            "translated_title": paper_data.get("translated_title", ""),
            "abstract": {
                "content": paper_data.get("abstract", {}).get("content", ""),
                "translated_content": paper_data.get("abstract", {}).get("translated_content", "")
            },
            "sections": restructured_sections
        }
        
        # 根據重構後的樹生成 key_map
        restructured_paper["key_map"] = self._generate_key_map(restructured_sections, paper_data.get("title", ""))
        
        return restructured_paper

    def _restructure_sections(self, sections: List[Dict], level: int) -> List[Dict]:
        """遞歸重構章節，移除不需要的字段，重新標註索引和層級"""
        restructured_sections = []
        
        for i, section in enumerate(sections):
            # 建立新的章節字典，僅保留需要的字段
            new_section = {
                "title": section.get("title", ""),
                "translated_title": section.get("translated_title", ""),
                "level": level,
                "summary": section.get("summary", ""),
                "content": []
            }
            
            # 處理內容，重新標註索引
            content_index = 0
            for item in section.get("content", []):
                if isinstance(item, dict):
                    new_item = {
                        "type": item.get("type", ""),
                        "index": content_index
                    }
                    
                    # 根據內容類型保留相應字段
                    if item.get("type") == "text":
                        new_item["content"] = item.get("content", "")
                        new_item["translated_content"] = item.get("translated_content", "")
                        new_item["questions"] = item.get("questions", "")
                    elif item.get("type") == "figure":
                        new_item["src"] = item.get("src", "")
                        new_item["alt"] = item.get("alt", "")
                        new_item["caption"] = item.get("caption", "")
                        new_item["translated_caption"] = item.get("translated_caption", "")
                        new_item["questions"] = item.get("questions", "")
                    elif item.get("type") == "table":
                        new_item["content"] = item.get("content", "")
                        new_item["caption"] = item.get("caption", "")
                        new_item["translated_caption"] = item.get("translated_caption", "")
                        new_item["questions"] = item.get("questions", "")
                    elif item.get("type") == "formula":
                        new_item["content"] = item.get("content", "")
                        new_item["formula_analysis"] = item.get("formula_analysis", "")
                    
                    new_section["content"].append(new_item)
                    content_index += 1
            
            # 處理子章節
            if "children" in section and section["children"]:
                new_section["children"] = self._restructure_sections(section.get("children", []), level + 1)
            else:
                new_section["children"] = []
            
            restructured_sections.append(new_section)
        
        return restructured_sections

    def _generate_key_map(self, sections: List[Dict], title: str, parent_path="", parent_json_path="") -> Dict[str, str]:
        """
        生成 key_map，關鍵路徑映射表
        修復：正確處理子章節的JSON路徑
        """
        key_map = {}
        
        for i, section in enumerate(sections):
            section_title = section.get("title", "")
            
            # 構建語義路徑和JSON路徑
            section_path = f"{parent_path}/{section_title}" if parent_path else section_title
            current_json_path = f"{parent_json_path}/sections/{i}" if not parent_json_path else f"{parent_json_path}/{i}"
            
            # 添加章節的映射
            section_key = f"{title}/{section_path}/section"
            key_map[section_key] = current_json_path
            
            # 為內容生成鍵
            for j, item in enumerate(section.get("content", [])):
                content_key = f"{section_key}/{j}/{item.get('type', '')}"
                key_map[content_key] = f"{current_json_path}/content/{j}"
            
            # 處理子章節，傳遞正確的JSON路徑
            if section.get("children"):
                # 建立子章節的JSON路徑，確保包含children層級
                children_json_path = f"{current_json_path}/children"
                child_key_map = self._generate_key_map(
                    section.get("children", []),
                    title,
                    section_path,
                    children_json_path
                )
                key_map.update(child_key_map)
        
        return key_map

    def _get_node_by_json_path(self, json_path: str, json_data: Dict) -> Any:
        """根據 JSON 路徑獲取節點，增強錯誤處理和日誌記錄"""
        if not json_path:
            self.logger.warning(f"空JSON路徑")
            return None
            
        keys = json_path.strip("/").split("/")
        node = json_data
        
        try:
            for i, key in enumerate(keys):
                if isinstance(node, list):
                    try:
                        key = int(key)
                        if 0 <= key < len(node):
                            node = node[key]
                        else:
                            self.logger.warning(f"索引越界: {key}, 路徑: {json_path}, 位置: {i+1}/{len(keys)}")
                            return None
                    except (ValueError, IndexError):
                        self.logger.warning(f"無效的列表索引: {key}, 路徑: {json_path}, 位置: {i+1}/{len(keys)}")
                        return None
                elif isinstance(node, dict):
                    if key in node:
                        node = node[key]
                    else:
                        self.logger.warning(f"鍵不存在: {key}, 路徑: {json_path}, 位置: {i+1}/{len(keys)}")
                        return None
                else:
                    self.logger.warning(f"無法繼續導航, 節點類型: {type(node)}, 路徑: {json_path}, 位置: {i+1}/{len(keys)}")
                    return None
        except Exception as e:
            self.logger.error(f"解析JSON路徑時出錯: {json_path}, 錯誤: {str(e)}")
            return None
            
        return node

    def _generate_markdown(self, tree_structure: Dict, output_path: str):
        """生成 Markdown 檔案，按節點 key 組織內容，並增強錯誤處理"""
        self.logger.info(f"生成 Markdown 檔案: {output_path}")
        
        with open(output_path, "w", encoding="utf-8") as f:
            title = tree_structure.get("title", "")
            
            # 先檢查並記錄所有未找到的節點
            missing_nodes = []
            for key, json_path in tree_structure.get("key_map", {}).items():
                node = self._get_node_by_json_path(json_path, tree_structure)
                if not node:
                    missing_nodes.append((key, json_path))
                    
            if missing_nodes:
                self.logger.warning(f"找不到以下節點: {missing_nodes[:10]} {'...' if len(missing_nodes) > 10 else ''}")
            
            # 遍歷 key_map 生成 Markdown 內容
            for key, json_path in tree_structure.get("key_map", {}).items():
                node = self._get_node_by_json_path(json_path, tree_structure)
                
                if not node:
                    # 已在上面記錄了，這裡不再重複記錄
                    continue
                
                md_content = self._generate_md_content(node, key)
                if md_content:
                    f.write(md_content + "\n\n")
                else:
                    self.logger.warning(f"無法為節點生成Markdown內容: {key}, 路徑: {json_path}")
            
            self.logger.info(f"Markdown檔案生成完成: {output_path}")

    def _generate_md_content(self, node: Dict, key: str) -> str:
        """
        生成 Markdown 內容，寬鬆化條件以處理更多類型的內容
        """
        md_content = f"# {key}\n"
        
        # 不同類型的節點生成不同的內容
        if "summary" in node and "/section" in key:
            md_content += f"{node.get('summary', '')}"
            return md_content
        
        if node.get("type") == "text":
            questions = node.get("questions", "")
            # 首先嘗試使用translated_content，如果沒有則使用content
            content = node.get("translated_content", "")
            if not content:
                content = node.get("content", "")
            
            if questions or content:
                md_content += f"{questions}\n{content}"
                return md_content
        
        if node.get("type") == "figure":
            questions = node.get("questions", "")
            # 嘗試使用translated_caption，如果沒有則使用caption
            caption = node.get("translated_caption", "")
            if not caption:
                caption = node.get("caption", "")
                
            if questions or caption:
                md_content += f"{questions}\n{caption}"
                return md_content
            
        if node.get("type") == "table":
            questions = node.get("questions", "")
            # 嘗試使用translated_caption，如果沒有則使用caption
            caption = node.get("translated_caption", "")
            if not caption:
                caption = node.get("caption", "")
                
            if questions or caption:
                md_content += f"{questions}\n{caption}"
                return md_content
        
        if node.get("type") == "formula":
            formula_content = node.get("content", "")
            formula_analysis = node.get("formula_analysis", "")
            
            if formula_content or formula_analysis:
                md_content += f"{formula_content}\n{formula_analysis}"
                return md_content
        
        # 如果節點是章節而不是內容項
        if "title" in node and "level" in node:
            title = node.get("title", "")
            translated_title = node.get("translated_title", "")
            summary = node.get("summary", "")
            
            if title or translated_title or summary:
                content = ""
                if title:
                    content += f"**{title}**"
                if translated_title and translated_title != title:
                    content += f" ({translated_title})"
                if summary:
                    content += f"\n\n{summary}"
                
                md_content += content
                return md_content
        
        return ""


# === 運行示例 ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, 
                      format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    processor = RagProcessor()
    input_json_path = "HUMAN-LIKE_EPISODIC_MEMORY_FOR_INFINITE_CONTEXT_LLMS_extra_info.json"
    output_md_path = "HUMAN-LIKE_EPISODIC_MEMORY.md"
    output_tree_json_path = "HUMAN-LIKE_EPISODIC_MEMORY_tree.json"

    processor.process(input_json_path, output_md_path, output_tree_json_path)