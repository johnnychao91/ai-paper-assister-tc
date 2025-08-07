from PyQt6.QtCore import QThread, pyqtSignal
from pathlib import Path

class ProcessingThread(QThread):
    """處理PDF檔案的執行緒"""
    processing_finished = pyqtSignal(str)  # 處理完成訊號
    processing_error = pyqtSignal(str, str)  # 處理錯誤訊號
    
    def __init__(self, pipeline, pdf_path, output_dir):
        super().__init__()
        self.pipeline = pipeline
        self.pdf_path = pdf_path
        self.output_dir = output_dir
        self.is_running = True
    
    def run(self):
        try:
            output_paths = self.pipeline.process(
                self.pdf_path, 
                self.output_dir
            )
            
            if self.is_running:  # 檢查是否被取消
                self.processing_finished.emit(Path(self.pdf_path).stem)
        except Exception as e:
            if self.is_running:  # 只有在執行緒沒有被手動停止時才報告錯誤
                self.processing_error.emit(Path(self.pdf_path).stem, str(e))
    
    def stop(self):
        """立即停止執行緒處理"""
        self.is_running = False
        self.terminate()  # 強制終止執行緒

# 修改 AIResponseThread 類別以傳遞滾動資訊
class AIResponseThread(QThread):
    """AI回應執行緒 - 處理AI回應產生，避免阻塞UI"""
    
    # 修改訊號定義，新增滾動資訊
    response_ready = pyqtSignal(str)
    sentence_ready = pyqtSignal(str, str, object)  # (句子, 情緒, 滾動資訊)
    
    def __init__(self, ai_chat):
        """初始化AI回應執行緒"""
        super().__init__()
        self.ai_chat = ai_chat
        self.query = ""
        self.paper_id = None
        self.visible_content = None
        self.use_streaming = False  # 預設使用串流回應
    
    def set_request(self, query, paper_id=None, visible_content=None):
        """設定請求參數"""
        self.query = query
        self.paper_id = paper_id
        self.visible_content = visible_content
    
    def run(self):
        """執行執行緒"""
        if self.use_streaming:
            # 串流處理
            response = ""
            try:
                # 修改這裡，接收情緒參數
                for sentence, scroll_info in self.ai_chat.process_query_stream(self.query, self.visible_content):
                    # 檢查執行緒是否被請求中斷
                    if self.isInterruptionRequested():
                        print("AI回應生成被中斷")
                        break
                        
                    # 發射句子訊號，傳遞實際情緒
                    self.sentence_ready.emit(sentence, scroll_info)
                    response += sentence
            except Exception as e:
                print(f"AI回應產生失敗: {str(e)}")
                # 發射錯誤訊號
                self.response_ready.emit(f"抱歉，處理您的問題時出現錯誤: {str(e)}")
                return
                
            # 發射完整回應訊號
            if not self.isInterruptionRequested():
                self.response_ready.emit(response)
        else:
            # 非串流處理 - 單次回應
            try:
                # 直接處理查詢並取得完整回應
                response = list(self.ai_chat.process_query_stream(self.query, self.visible_content))
                
                if self.isInterruptionRequested():
                    print("AI回應生成被中斷")
                    return
                    
                # 發射完整回應訊號
                if response:
                    self.response_ready.emit(" ".join([item[0] for item in response]))  # 拼接所有結果的句子部分並發送
            except Exception as e:
                print(f"AI回應生成失敗: {str(e)}")
                self.response_ready.emit(f"抱歉，處理您的問題時出現錯誤: {str(e)}")