from PyQt6.QtCore import QObject, pyqtSignal, QUuid
from .AI_professor_chat import AIProfessorChat
from .threads import AIResponseThread
from .rag_retriever import RagRetriever
import os

class AIManager(QObject):
    """
    AI管理類 - 處理所有AI相關的功能
    
    包括:
    - AI對話邏輯
    - 語音辨識
    - TTS語音合成
    - RAG檢索增強生成
    """
    # 信號定義
    ai_response_ready = pyqtSignal(str)       # AI回覆準備好信號
    vad_started = pyqtSignal()                # 語音活動開始信號
    vad_stopped = pyqtSignal()                # 語音活動結束信號  
    voice_error = pyqtSignal(str)             # 語音錯誤信號
    voice_ready = pyqtSignal()                # 語音系統就緒信號
    voice_device_switched = pyqtSignal(bool)  # 語音設備切換狀態信號
    ai_sentence_ready = pyqtSignal(str, str)  # 單句AI回覆準備好信號（內容, 請求ID）
    ai_generation_cancelled = pyqtSignal()    # AI生成被取消信號
    
    def __init__(self):
        """初始化AI管理器"""
        super().__init__()
        
        # 初始化AI聊天助手
        self._init_ai_assistant()
        
        # 緩存待顯示的句子
        self.pending_sentences = {}
        
        # 語音輸入對象將在init_voice_recognition中初始化
        self.data_manager = None  # 將在later設置
        
        # 添加狀態標誌來追蹤是否有正在進行的AI生成
        self.is_generating_response = False
        
        # 當前活動的請求ID
        self.current_request_id = None

        # 添加累積響應變數
        self.accumulated_response = ""
    
    def set_data_manager(self, data_manager):
        """設置資料管理器引用"""
        self.data_manager = data_manager
    
    def _init_ai_assistant(self):
        """初始化AI聊天助手和響應線程"""
        self.ai_chat = AIProfessorChat()
        self.ai_response_thread = AIResponseThread(self.ai_chat)
        self.ai_response_thread.response_ready.connect(self._on_ai_response_ready)
        # 連接新的單句信號
        self.ai_response_thread.sentence_ready.connect(self._on_ai_sentence_ready)
    
    def cancel_current_response(self):
        """取消當前正在生成的AI響應"""
        print("取消目前的AI回應...")
        
        # 處理已收集的部分響應
        # 只有當有實際內容時才添加到歷史記錄
        if self.accumulated_response and self.accumulated_response.strip():
            print(f"將已產生的部分回應儲存到對話歷史: {self.accumulated_response[:30]}...")
            # 將已生成的部分添加到對話歷史
            if hasattr(self.ai_chat, 'conversation_history'):
                # 添加到對話歷史
                self.ai_chat.conversation_history.append({
                    "role": "assistant", 
                    "content": self.accumulated_response
                })
        # 無論是否添加到歷史，都重置累積響應
        self.accumulated_response = ""
        
        # 清空待處理的句子
        self.pending_sentences.clear()
        
        # 中斷AI響應線程
        if self.ai_response_thread.isRunning():
            print("正在停止AI生成...")
            self.ai_response_thread.requestInterruption()
            self.ai_response_thread.wait(1000)  # 等待最多1秒
            
            # 發出取消信號，以便UI清理loading bubble
            self.is_generating_response = False
            self.ai_generation_cancelled.emit()
            
            # 清除當前請求ID
            self.current_request_id = None
    
    def get_ai_response(self, query, paper_id=None, visible_content=None):
        """獲取AI對用戶查詢的響應"""
        try:
            # 如果已經有正在生成的響應，先取消它
            if self.is_generating_response:
                self.cancel_current_response()
            
            # 確保線程不在運行狀態
            if self.ai_response_thread.isRunning():
                print("等待上一個AI響應線程結束...")
                self.ai_response_thread.requestInterruption()
                self.ai_response_thread.wait(1000)  # 等待最多1秒
                
                # 如果線程仍在運行，建立新的線程
                if self.ai_response_thread.isRunning():
                    print("建立新的AI響應線程...")
                    self._init_ai_assistant()
            
            # 生成新的請求ID
            request_id = str(QUuid.createUuid().toString(QUuid.StringFormat.Id128))
            self.current_request_id = request_id
            print(f"建立新的AI請求，ID: {request_id}")
            
            # 確保有論文上下文(如果必要)
            if not paper_id and self.data_manager and self.data_manager.current_paper:
                paper_id = self.data_manager.current_paper.get('id')
                
            # 獲取論文資料並設置上下文
            if paper_id and self.data_manager:
                paper_data = self.data_manager.load_rag_tree(paper_id)
                if paper_data:
                    self.ai_chat.set_paper_context(paper_id, paper_data)
            
            # 設置請求參數並啟動線程
            self.ai_response_thread.set_request(query, paper_id, visible_content)
            
            # 更新狀態標誌
            self.is_generating_response = True
            
            # 啟動線程
            self.ai_response_thread.start()
            
            # 返回請求ID，以便調用者可以使用
            return request_id
        except Exception as e:
            print(f"AI回應生成失敗: {str(e)}")
            self.is_generating_response = False
            self.current_request_id = None
            self.ai_response_ready.emit(f"抱歉，處理您的問題時出現錯誤: {str(e)}")
            return None

    def _on_ai_response_ready(self, response):
        """處理AI響應就緒事件"""
        # 更新狀態標誌
        self.is_generating_response = False

        # 發出信號通知UI
        self.ai_response_ready.emit(response)
        
    def _on_ai_sentence_ready(self, sentence, scroll_info=None):
        """處理單句AI響應就緒事件"""
        # 如果沒有當前請求ID，可能是已經被取消，忽略這個句子
        if not self.current_request_id:
            return
        
        # 緩存句子，並關聯請求ID和情緒
        sentence_id = id(sentence)  # 使用對象id作為唯一標識
        self.pending_sentences[sentence_id] = (sentence, self.current_request_id)
        
        # 累積響應
        self.accumulated_response += sentence
        
        # 刪除此行，不在AI生成時觸發顯示
        # self.ai_sentence_ready.emit(sentence, self.current_request_id)
        
        # 處理滾動資訊 - 如果有滾動資訊且markdown_view被設置，則執行滾動
        if scroll_info and hasattr(self, 'markdown_view') and self.markdown_view:
            self._scroll_to_content(scroll_info)
        
    def cleanup(self):
        """清理所有資源"""
        # 停止AI響應線程
        if self.ai_response_thread and self.ai_response_thread.isRunning():
            self.ai_response_thread.requestInterruption()
            self.ai_response_thread.wait()

    def init_rag_retriever(self, base_path):
        """在後台初始化RAG檢索器"""
        try:
            print(f"[INFO] 開始初始化RAG檢索器: {base_path}")
            
            # 建立RAG檢索器並開始後台載入
            self.retriever = RagRetriever(base_path)

            # 確保AI聊天模組使用相同的檢索器
            if hasattr(self, 'ai_chat') and self.ai_chat:
                if self.ai_chat.retriever is not None:
                    print("[INFO] 取代AI聊天模組中的舊檢索器")
                self.ai_chat.retriever = self.retriever
            
            # 連接載入完成信號以進行日誌記錄
            self.retriever.loading_complete.connect(self._on_retriever_loaded)
            
            return True
        except Exception as e:
            print(f"[ERROR] 初始化RAG檢索器失敗: {str(e)}")
            return False

    def _on_retriever_loaded(self, success):
        """處理檢索器載入完成事件"""
        if success:
            print(f"[INFO] RAG檢索器載入完成，總共載入了 {len(self.retriever.paper_vector_paths)} 篇論文的向量庫索引")
            
            # 可以添加額外驗證代碼
            for paper_id, path in self.retriever.paper_vector_paths.items():
                if not os.path.exists(path):
                    print(f"[WARNING] 論文 {paper_id} 的向量庫路徑不存在: {path}")
        else:
            print("[ERROR] RAG檢索器載入失敗或沒有找到論文")

    def add_paper_vector_store(self, paper_id, vector_store_path):
        """添加新論文的向量庫
        
        在處理完新論文後調用此方法
        
        Args:
            paper_id: 論文ID
            vector_store_path: 向量庫路徑
            
        Returns:
            bool: 成功返回True
        """
        if hasattr(self, 'retriever'):
            return self.retriever.add_paper(paper_id, vector_store_path)
        return False

    def _scroll_to_content(self, scroll_info):
        """根據滾動資訊滾動到對應內容"""
        if not scroll_info:
            return
            
        # 獲取當前語言
        current_lang = self.markdown_view.get_current_language()
        
        # 根據當前語言選擇內容
        content = scroll_info['zh_content'] if current_lang == 'zh' else scroll_info['en_content']
        node_type = scroll_info.get('node_type', 'text')
        is_title = scroll_info.get('is_title', False)
        
        # 如果內容為空，嘗試使用另一種語言的內容
        if not content:
            content = scroll_info['en_content'] if current_lang == 'zh' else scroll_info['zh_content']
        
        # 執行滾動
        if content:
            # 根據節點類型確定滾動類型
            if is_title:
                self.markdown_view._scroll_to_matching_content(content, 'title')
            else:
                self.markdown_view._scroll_to_matching_content(content, 'text')