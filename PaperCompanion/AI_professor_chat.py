import logging
import json
import os
from typing import List, Dict, Any, Generator, Tuple
from .config import LLMClient

AI_EXPLAIN_PROMPT_PATH = "prompt/ai_explain_prompt.txt"
AI_ROUTER_PROMPT_PATH = "prompt/ai_router_prompt.txt"

class AIProfessorChat:
    """
    AI對話助手 - 學術論文智能問答系統
    
    支援多種回答策略：
    - 直接回答
    - 頁面內容分析
    - 宏觀檢索（章節概要）
    - RAG檢索（精準段落）
    """
    
    def __init__(self):
        """初始化AI對話助手"""
        self.logger = logging.getLogger(__name__)
        
        # 設置基礎路徑
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        
        # 對話歷史 (保持最近10條)
        self.conversation_history = []
        
        # 當前論文上下文
        self.current_paper_id = None
        self.current_paper_data = None
        
        # 將實例化改為引用初始化
        self.retriever = None  # 稍後由AI_manager設置
        
        # LLM客戶端
        self.llm_client = None
        try:
            self.llm_client = LLMClient()
            self.logger.info("AI對話助理初始化完成")
        except Exception as e:
            self.logger.error(f"初始化AI對話組件失敗: {str(e)}")

    def _read_file(self, filepath: str) -> str:
        """讀取檔案內容"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.warning(f"讀取檔案 {filepath} 失敗: {str(e)}")
            return ""
    
    def set_paper_context(self, paper_id: str, paper_data: Dict[str, Any]) -> bool:
        """設置當前論文上下文
        
        Args:
            paper_id: 論文ID
            paper_data: 論文資料字典
            
        Returns:
            bool: 成功返回True，失敗返回False
        """
        try:
            self.current_paper_id = paper_id
            self.current_paper_data = paper_data
            self.logger.info(f"已設定論文上下文: {paper_id}")
            return True
        except Exception as e:
            self.logger.error(f"設定論文上下文失敗: {str(e)}")
            return False
    
    def process_query_stream(self, query: str, visible_content: str = None) -> Generator[Tuple[str, str, Dict], None, None]:
        """串流處理用戶查詢並生成回答，按句子返回
        
        Args:
            query: 用戶查詢文字
            visible_content: 當前可見的頁面內容
            
        Yields:
            Tuple[str, str, Dict]: (生成的句子, 情緒, 滾動定位資訊)
            
        Returns:
            Generator: 句子生成器
        """
        try:
            if not self.llm_client:
                yield "AI服務尚未初始化，請稍後再試。", None, None
                return

            print(f"\n==== 使用者查詢 ====\n{query}")

            # 1. 檢查是否需要添加用戶問題到對話歷史
            should_add_query = True
            if self.conversation_history and len(self.conversation_history) > 0:
                last_message = self.conversation_history[-1]
                if last_message["role"] == "user" and last_message["content"] == query:
                    # 問題已存在於歷史記錄的最後一條，不需要重複添加
                    should_add_query = False
                    self.logger.info("偵測到重複問題，跳過新增到歷史記錄")
            
            # 只有在需要時才添加問題到對話歷史
            if should_add_query:
                self.conversation_history.append({"role": "user", "content": query})
            
            # 保持對話歷史在合理長度
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
                
            # 2. 決策過程 - 調用LLM進行決策
            decision = self._make_decision(query)
            self.logger.info(f"決策結果: {decision}")
            print(f"\n==== 決策結果 ====\n{json.dumps(decision, ensure_ascii=False, indent=2)}")
            
            # 3. 根據決策選擇策略
            function_name = decision.get('function', 'direct_answer')
            optimized_query = decision.get('query', query)  # 獲取優化後的查詢
            
            # 4. 根據策略執行不同的處理
            context_info = ""
            scroll_info = None  # 初始化滾動資訊
            
            if function_name == 'direct_answer':
                # 直接回答，不需要額外資訊
                print("\n==== 直接回答模式 ====\n無需檢索上下文")
                pass
            
            elif function_name == 'page_content_analysis':
                # 分析當前頁面內容
                if visible_content:
                    context_info = f"以下是頁面目前顯示的內容:\n\n{visible_content}"
                    print(f"\n==== 頁面內容分析 ====\n{context_info}")
            
            elif function_name == 'macro_retrieval':
                # 宏觀檢索 - 獲取章節概要
                if self.current_paper_data:
                    context_info = self._get_macro_context(optimized_query)  # 使用優化查詢
            
            elif function_name == 'rag_retrieval':
                # RAG檢索 - 獲取相關段落
                if self.current_paper_id:
                    context_info, scroll_info = self._get_rag_context(optimized_query)  # 使用優化查詢
            
            else:
                # 未知策略，使用直接回答
                self.logger.warning(f"未知的回答策略: {function_name}，使用直接回答")
            
            # 5. 準備最終查詢訊息，傳遞原始查詢、優化查詢和回答策略
            final_messages = self._prepare_final_messages(
                query=query,
                context_info=context_info,
                optimized_query=optimized_query,  # 傳遞優化後的查詢
                function_name=function_name  # 傳遞回答策略
            )
            
            print(f"\n==== 最終發送給LLM的訊息 ====")
            for i, msg in enumerate(final_messages):
                print(f"訊息 {i+1} - 角色: {msg['role']}")
                print(f"內容: {msg['content']}\n")
            
            # 6. 調用LLM獲取串流回答
            response_generator = self.llm_client.chat_stream_by_sentence(
                messages=final_messages,
                temperature=0.7
            )
            
            # 7. 收集完整響應以添加到歷史記錄
            full_response = ""
            
            # 8. 串流返回結果，第一個句子附帶滾動資訊
            first_sentence = True
            for sentence in response_generator:
                full_response += sentence
                if first_sentence:
                    yield sentence, scroll_info  # 添加情緒參數
                    first_sentence = False
                else:
                    yield sentence, None  # 添加情緒參數
            
            # 9. 記錄AI回答到對話歷史
            self.conversation_history.append({"role": "assistant", "content": full_response})
            
            print(f"\n==== LLM完整回應 ====\n{full_response}")

        except Exception as e:
            error_msg = f"串流處理查詢失敗: {str(e)}"
            self.logger.error(error_msg)
            yield f"抱歉，處理您的問題時出現錯誤: {str(e)}", None, None
    
    def record_assistant_response(self, response):
        """記錄AI助手的回應到對話歷史
        
        Args:
            response: AI生成的回答
        """
        # 記錄AI回答到對話歷史
        self.conversation_history.append({"role": "assistant", "content": response})
    
    def _validate_decision(self, decision_data: Dict[str, str]) -> bool:
        """驗證決策結果是否符合要求
        
        Args:
            decision_data: 決策資料字典
            
        Returns:
            bool: 驗證通過返回True，否則返回False
        """
        # 檢查必要字段
        required_fields = ["function", "query"]
        if not all(field in decision_data for field in required_fields):
            self.logger.warning("決策資料缺少必要字段")
            return False
        
        # 確保function在有效範圍內
        valid_functions = ["direct_answer", "page_content_analysis", "macro_retrieval", "rag_retrieval"]
        if decision_data["function"] not in valid_functions:
            self.logger.warning(f"無效的功能類型: {decision_data['function']}")
            return False
        
        return True

    def _make_decision(self, query: str) -> Dict[str, str]:
        """決定如何回答用戶的問題
        
        Args:
            query: 用戶查詢
                
        Returns:
            Dict[str, str]: 包含 function, query的決策字典
        """
        # 預設決策結果
        default_decision = {
            "function": "direct_answer",
            "query": query  # 預設使用原始查詢
        }
        
        try:
            # 1. 讀取並準備決策提示詞
            router_prompt = self._read_file(os.path.join(self.base_path,AI_ROUTER_PROMPT_PATH))
            
            # 確定當前論文狀態
            has_paper_loaded = self.current_paper_id is not None and self.current_paper_data is not None
            paper_status = "有論文載入" if has_paper_loaded else "無論文載入"
            
            # 獲取當前論文標題（如果有）
            paper_title = "無論文"
            if has_paper_loaded:
                paper_title = self.current_paper_data.get('translated_title', '') or self.current_paper_data.get('title', '')
                paper_title = f"目前論文標題: {paper_title}"
            
            # 準備對話歷史格式 - 不包括最新的用戶查詢
            formatted_history = ""
            if len(self.conversation_history) > 1:  # 確保有足夠的歷史記錄
                # 只取最近的歷史記錄（不包括最新的用戶查詢）
                recent_history = self.conversation_history[:-1][-4:]  # 最多取4條歷史記錄(不包括最新的)
                history_items = []
                for msg in recent_history:
                    role = "用戶" if msg["role"] == "user" else "暴躁教授"
                    content = msg["content"]
                    history_items.append(f"{role}: {content}")
                formatted_history = "\n".join(history_items)
            
            # 將論文狀態、論文標題和對話歷史添加到提示中
            decision_prompt = router_prompt.format(
                query=query, 
                paper_status=paper_status,
                paper_title=paper_title,
                conversation_history=formatted_history
            )
            
            print(f"\n==== 決策提示 ====\n{decision_prompt}")
            
            # 2. 準備調用LLM的訊息
            messages = [{"role": "user", "content": decision_prompt}]
            
            # 3. 最多嘗試兩次
            import re
            decision_data = None
            
            for attempt in range(2):
                self.logger.info(f"決策請求嘗試 {attempt+1}/2")
                
                # 調用LLM進行決策
                decision_response = self.llm_client.chat(
                    messages=messages,
                    temperature=0.7,
                    stream=False
                )
                
                print(f"\n==== 決策LLM回應 (嘗試 {attempt+1}) ====\n{decision_response}")
                
                # 使用正規表達式匹配JSON結構
                json_match = re.search(r'\{.*\}', decision_response, re.DOTALL)
                if not json_match:
                    self.logger.warning("無法從回應中提取JSON，將重試")
                    continue
                    
                try:
                    # 解析提取的JSON
                    decision_data = json.loads(json_match.group(0))
                    
                    # 驗證決策資料
                    if self._validate_decision(decision_data):
                        # 驗證通過，跳出迴圈
                        break
                    else:
                        self.logger.warning("決策驗證失敗，將重試")
                except json.JSONDecodeError:
                    self.logger.warning("JSON解析失敗，將重試")
            
            # 4. 如果無論文載入，強制使用direct_answer
            if not has_paper_loaded and decision_data and self._validate_decision(decision_data):
                decision_data["function"] = "direct_answer"
                self.logger.info("無論文載入，強制使用direct_answer策略")
            
            # 5. 返回決策結果：如果decision_data有效則使用它，否則使用預設值
            if decision_data and self._validate_decision(decision_data):
                return {
                    "function": decision_data["function"],
                    "query": decision_data["query"]
                }
            else:
                self.logger.warning("所有決策嘗試都失敗，使用預設決策")
                return default_decision
                
        except Exception as e:
            self.logger.error(f"決策過程失敗: {str(e)}")
            return default_decision
    
    def _get_macro_context(self, query: str) -> str:
        """獲取宏觀上下文 - 從章節概要中提取
        
        提取內容:
        - 論文總標題(翻譯或原始)
        - 論文總摘要(如果存在)
        - 第一級章節的標題和摘要(不遞迴處理子章節)
        
        Args:
            query: 檢索查詢
            
        Returns:
            str: 宏觀上下文資訊
        """
        try:
            if not self.current_paper_data:
                return ""
                    
            # 提取章節標題和摘要
            context_parts = []
            
            # 添加文件標題
            doc_title = self.current_paper_data.get('translated_title', '') or self.current_paper_data.get('title', '')
            if doc_title:
                context_parts.append(f"# {doc_title}")
            
            # 添加論文總摘要(如果存在)
            if 'summary' in self.current_paper_data and self.current_paper_data['summary']:
                context_parts.append(f"## 總摘要\n{self.current_paper_data['summary']}")
            
            # 添加第一級章節標題和摘要(不遞迴)
            if 'sections' in self.current_paper_data and self.current_paper_data['sections']:
                context_parts.append("## 章節概要")
                for section in self.current_paper_data['sections']:
                    # 提取章節標題(優先使用翻譯標題)
                    section_title = section.get('translated_title', '') or section.get('title', '')
                    
                    # 提取章節摘要
                    section_summary = section.get('summary', '')
                    
                    if section_title:
                        # 添加章節標題和摘要
                        section_text = f"### {section_title}"
                        if section_summary:
                            section_text += f"\n{section_summary}"
                        
                        context_parts.append(section_text)
            
            # 組合所有上下文
            if context_parts:
                context_result = "\n\n".join(context_parts)
                print(f"\n==== 宏觀檢索結果 ====\n{context_result}")
                return context_result
            else:
                print("\n==== 宏觀檢索結果為空 ====")
                return ""
                    
        except Exception as e:
            self.logger.error(f"取得宏觀上下文失敗: {str(e)}")
            return ""
    
    def _get_rag_context(self, query: str) -> Tuple[str, Dict]:
        """從RAG檢索器獲取相關上下文和滾動定位資訊"""
        try:
            if not self.current_paper_id or not query:
                return "", None
            
            print(f"\n==== RAG檢索查詢 ====\n{query}")
            
            # 添加檢查 - 確保檢索器存在且已載入完成
            if not self.retriever:
                self.logger.warning("RAG檢索器未初始化，無法執行檢索")
                return "", None
                
            # 檢查檢索器是否就緒
            if not self.retriever.is_ready():
                self.logger.warning("RAG檢索器尚未載入完成，無法執行檢索")
                return "", None
                
            # 使用RAG檢索器獲取結構化相關內容和滾動資訊
            context, scroll_info = self.retriever.retrieve_with_context(
                query=query,
                paper_id=self.current_paper_id,
                top_k=5
            )
            
            print(f"\n==== RAG檢索結果 ====\n{context}")
            
            return context, scroll_info
                
        except Exception as e:
            self.logger.error(f"RAG檢索失敗: {str(e)}")
            return "", None
    
    def _prepare_final_messages(self, query: str, context_info: str, optimized_query: str = None, function_name: str = None) -> List[Dict[str, str]]:
        """準備最終發送給LLM的訊息列表
        
        Args:
            query: 原始用戶查詢
            context_info: 上下文資訊
            optimized_query: 優化後的查詢
            function_name: 回答策略
            
        Returns:
            List[Dict[str, str]]: 訊息列表
        """
        messages = []
        
        # 讀取角色提示詞和解釋提示詞
        explain_prompt = self._read_file(os.path.join(self.base_path,AI_EXPLAIN_PROMPT_PATH))
        
        # 添加論文標題到系統提示(如果有)
        title = ""
        if self.current_paper_data:
            title = self.current_paper_data.get('translated_title', '') or self.current_paper_data.get('title', '')
        else:
            title = "無論文"

        explain_prompt = explain_prompt.format(title=title)
        
        # 系統提示 - 使用回車拼接提示詞
        system_message = f"{explain_prompt}"
        
        messages.append({"role": "system", "content": system_message})
        
        # 添加對話歷史（不包括最新的用戶查詢）
        if len(self.conversation_history) > 1:
            messages.extend(self.conversation_history[:-1])  
        
        # 構建用戶查詢 - 包含原始查詢和優化查詢
        final_query = f"目前用戶訊息：{query}"
        
        # 如果有上下文資訊，根據function_name添加對應的資訊類型說明
        if context_info:
            context_type = "參考資訊"
            if function_name == "page_content_analysis":
                context_type = "目前頁面內容"
            elif function_name == "macro_retrieval":
                context_type = "論文概要"
            elif function_name == "rag_retrieval":
                context_type = "相關論文段落"
        
            final_query = f"{final_query}\n\n{context_type}:\n{context_info}"
        
        final_query += f"{final_query}\n\n輸出回覆的話："
        # 添加最終用戶查詢
        messages.append({"role": "user", "content": final_query})
        
        return messages