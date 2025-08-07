import json
import logging
import re
import numpy as np
from pathlib import Path
from typing import Dict, List, Any
from sklearn.metrics.pairwise import cosine_similarity
from ..config import EmbeddingModel

class TilingProcessor:
    """
    JSON檔案分塊處理器
    
    將處理後的JSON檔案進行分割合併處理，為翻譯階段做準備
    使用向量相似度計算最佳切分點
    """
    
    def __init__(self, min_length: int = 500, max_length: int = 2500, window_size: int = 3, step_size: int = 1):
        """
        初始化平鋪處理器
        
        Args:
            min_length: 文字塊最小長度
            max_length: 文字塊最大長度
            window_size: 相似度計算窗口大小
            step_size: 滑動窗口步長
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.min_length = min_length
        self.max_length = max_length
        self.window_size = window_size
        self.step_size = step_size
    
    def process(self, input_path: str, output_path: str) -> Path:
        """
        處理JSON檔案，將文字塊進行合併分割處理
        
        Args:
            input_path: 輸入JSON檔案路徑
            output_path: 輸出JSON檔案路徑
            
        Returns:
            Path: 輸出檔案路徑
        """
        self.logger.info(f"開始處理JSON檔案: 從 {input_path} 到 {output_path}")
        
        # 讀取輸入JSON檔案
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 處理sections中的content
        if 'sections' in data:
            self.logger.info(f"開始處理文檔sections，共 {len(data['sections'])} 個section")
            self._process_sections(data['sections'])
            self.logger.info("sections處理完成")
        
        # 保存處理後的JSON檔案
        output_file = Path(output_path)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"處理完成，輸出已保存到 {output_file}")
        return output_file
    
    def _process_sections(self, sections: List[Dict[str, Any]]) -> None:
        """
        處理sections列表，遞歸處理所有section內容，跳過abstract和references
        
        Args:
            sections: section列表
        """
        for section in sections:
            # 跳過abstract和references類型的section
            if section.get('type') in ['abstract', 'references']:
                self.logger.info(f"跳過處理section類型: {section.get('type')}")
                continue
                
            if 'content' in section:
                section['content'] = self._process_content(section['content'])
            
            # 遞歸處理子section
            if 'children' in section and section['children']:
                self._process_sections(section['children'])
    
    def _process_content(self, content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        處理content列表，合併和分割文字塊
        
        Args:
            content: content列表
            
        Returns:
            List[Dict[str, Any]]: 處理後的content列表
        """
        # 先檢查是否需要合併相鄰的小文字塊
        content = self._merge_small_text_blocks(content)
        
        # 為每個塊添加index和part標記
        for idx, item in enumerate(content):
            item['index'] = idx
            # 如果是未分割的塊，part為0
            item['part'] = 0
        
        # 然後檢查是否需要分割大文字塊
        result = []
        for item in content:
            if item['type'] == 'text' and len(item['content']) > self.max_length:
                # 獲取原始索引
                original_index = item.get('index', 0)
                
                # 分割大文字塊
                if '\n\n' in item['content']:
                    # 使用換行符分割策略
                    elements = item['content'].split('\n\n')
                    split_mode = "delimiter"
                else:
                    # 使用句子分割策略
                    elements = self._split_into_sentences(item['content'])
                    split_mode = "sentence"
                
                # 使用統一的TextTiling算法進行分割
                segments = self._texttiling(elements, split_mode)
                
                # 建立分割後的文字塊
                split_blocks = []
                for i, segment_text in enumerate(segments):
                    new_block = item.copy()
                    new_block['content'] = segment_text
                    new_block['index'] = original_index
                    new_block['part'] = i
                    split_blocks.append(new_block)
                
                result.extend(split_blocks)
            else:
                result.append(item)
        
        return result
    
    def _merge_small_text_blocks(self, content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合併相鄰的小文字塊，直到遇到非文字塊或滿足最小長度的文字塊
        
        Args:
            content: content列表
            
        Returns:
            List[Dict[str, Any]]: 處理後的content列表
        """
        if not content:
            return content
        
        result = []
        current_buffer = None
        
        for item in content:
            if item['type'] == 'text':
                # 處理小文字塊的邏輯
                if len(item['content']) < self.min_length:
                    # 小文字塊，需要合併
                    if current_buffer is None:
                        # 沒有緩衝區，建立一個
                        current_buffer = item.copy()
                    else:
                        # 已有緩衝區，直接合併
                        current_buffer['content'] += "\n\n" + item['content']
                else:
                    # 遇到了滿足最小長度的文字塊
                    if current_buffer is not None:
                        # 有緩衝區，將當前文字塊合併到緩衝區
                        current_buffer['content'] += "\n\n" + item['content']
                        result.append(current_buffer)
                        current_buffer = None
                    else:
                        # 添加當前文字塊
                        result.append(item)
            else:
                # 遇到非文字塊
                if current_buffer is not None:
                    # 有緩衝區，輸出緩衝區內容
                    result.append(current_buffer)
                    current_buffer = None
                # 添加當前非文字塊
                result.append(item)
        
        # 處理最後的緩衝區
        if current_buffer is not None:
            result.append(current_buffer)
        
        return result
    
    def _texttiling(self, elements: List[str], split_mode: str = "sentence") -> List[str]:
        """
        通用的TextTiling算法實現
        
        Args:
            elements: 文字元素列表（可以是句子或分隔符分割的部分）
            split_mode: 分割模式，"sentence"或"delimiter"
            
        Returns:
            List[str]: 分段結果文字列表
        """
        # 如果元素數量不足，直接返回合併後的文字
        if len(elements) < self.window_size + 2:
            combined_text = ' '.join(elements) if split_mode == "sentence" else '\n\n'.join(elements)
            return [combined_text]
        
        # 建立文字塊（窗口）
        blocks = []
        for i in range(0, len(elements) - self.window_size + 1, self.step_size):
            window = elements[i:i + self.window_size]
            if split_mode == "sentence":
                blocks.append(' '.join(window))
            else:  # delimiter mode
                blocks.append('\n'.join(window))
        
        # 計算每個塊的嵌入向量 - 使用統一的EmbeddingModel
        embedding_model = EmbeddingModel.get_instance()
        block_embeddings = [embedding_model.embed_query(block) for block in blocks]
        
        # 計算相鄰塊之間的相似度                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       
        similarities = [cosine_similarity([block_embeddings[i]], [block_embeddings[i+1]])[0][0] 
                        for i in range(len(block_embeddings)-1)]
        
        # 計算深度分數
        depth_scores = [0] * len(elements)
        for i in range(1, len(similarities)-1):
            depth = (similarities[i-1] + similarities[i+1] - 2*similarities[i]) / 2
            depth_scores[i+self.window_size//2] = depth
        
        # 計算閾值
        depth_values = [d for d in depth_scores if d > 0]
        if depth_values:
            mean_depth = np.mean(depth_values)
            std_depth = np.std(depth_values)
            threshold = mean_depth + 0.4 * std_depth
        else:
            threshold = 0
        
        # 找出潛在的邊界
        potential_boundaries = [i for i, score in enumerate(depth_scores) if score > threshold]
        
        # 找到最優分段
        segments = []
        start = 0
        
        while start < len(elements):
            optimal_boundary = self._find_optimal_boundary(start, elements, potential_boundaries, depth_scores)
            
            if split_mode == "sentence":
                segment_text = ' '.join(elements[start:optimal_boundary+1])
            else:  # delimiter mode
                segment_text = '\n'.join(elements[start:optimal_boundary+1])
            
            segments.append(segment_text)
            start = optimal_boundary + 1
        
        # 處理最後一個段落如果太小
        if segments and len(segments[-1]) < self.min_length and len(segments) > 1:
            last_segment = segments.pop()
            if split_mode == "sentence":
                segments[-1] += " " + last_segment
            else:  # delimiter mode
                segments[-1] += "\n" + last_segment
        
        return segments
    
    def _find_optimal_boundary(self, start: int, elements: List[str], 
                               potential_boundaries: List[int], depth_scores: List[float]) -> int:
        """
        找到最優的段落邊界
        
        Args:
            start: 起始位置
            elements: 元素列表（句子或分隔部分）
            potential_boundaries: 潛在邊界列表
            depth_scores: 深度分數列表
            
        Returns:
            int: 最優邊界的索引
        """
        current_length = 0
        candidate_boundaries = []
        
        for i in range(start, len(elements)):
            current_length += len(elements[i])
            if self.min_length <= current_length <= self.max_length:
                if i in potential_boundaries:
                    candidate_boundaries.append((i, depth_scores[i]))
            if current_length > self.max_length:
                break
        
        if not candidate_boundaries:
            # 找一個長度接近目標的位置
            target_length = (self.min_length + self.max_length) / 2
            return min(range(start, min(len(elements), start + 10)), 
                      key=lambda i: abs(sum(len(e) for e in elements[start:i+1]) - target_length))
        
        # 選擇深度分數最高的邊界
        best_boundary = max(candidate_boundaries, key=lambda x: x[1])
        return best_boundary[0]
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """
        將文字分割成句子（支援中英文）
        
        Args:
            text: 待分割的文字
            
        Returns:
            List[str]: 句子列表
        """
        # 中英文句子結束標誌
        sentence_pattern = re.compile(r'(?<=[。！？?!.;；])')
        sentences = [s.strip() for s in re.split(sentence_pattern, text) if s.strip()]
        
        return sentences