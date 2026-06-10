import logging
import sys
import os
from typing import Optional, List, Dict, Any, Generator
from openai import OpenAI
from langchain_huggingface import HuggingFaceEmbeddings

# API配置
API_BASE_URL = "http://192.168.1.104:1234/v1"
#API_BASE_URL = "https://api.openai.com/v1"

API_KEY = ""  # 替換為你的API密鑰

# 嵌入模型配置
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"

# 資料儲存路徑
BASE_DIR = os.path.expanduser("~/.ai-paper-assister-data")

# 線上模式
ONLINE_MODE = True

# 日誌配置
def setup_logging():
    """設定日誌配置為控制台輸出"""
    # 設定日誌格式
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 建立一個根日誌記錄器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 建立並配置控制台處理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    
    # 清除任何現有的處理器
    root_logger.handlers.clear()
    # 新增控制台處理器
    root_logger.addHandler(console_handler)

# LLM客戶端
class LLMClient:
    _instance: Optional['LLMClient'] = None
    
    def __new__(cls, *args, **kwargs):
        """單例模式實現"""
        if cls._instance is None:
            cls._instance = super(LLMClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, api_key=None, base_url=None):
        """初始化LLM客戶端"""
        if self._initialized:
            return
            
        self.api_key = api_key or API_KEY
        self.base_url = base_url or API_BASE_URL
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        self._initialized = True
        
    def chat(self, messages: List[Dict[str, Any]], temperature=0.5, stream=True) -> str:
        """與LLM互動
        
        Args:
            messages: 訊息列表
            temperature: 溫度參數，控制隨機性
            stream: 是否使用流式輸出
            
        Returns:
            str: LLM回應內容
        """
        try:
            response = self.client.chat.completions.create(
                model="google/gemma-3-12b",
                #model="qwen/qwen3-coder-30b",
                #model="gpt-oss-20b@q6_k",
                #model="llama-breeze2-8b-instruct-text-i1@q6_k",
                #model="llama-breeze2-8b-instruct-text-i1@q4_k_m",
                #model="gpt-4o-mini-2024-07-18",
                #model="deepseek-chat",
                messages=messages,
                temperature=temperature,
                stream=stream
            )
            
            if stream:
                full_response = ""
                for chunk in response:
                    if chunk.choices[0].delta.content is not None:
                        content = chunk.choices[0].delta.content
                        print(content, end='', flush=True)
                        full_response += content
                print()
                return full_response
            else:
                return response.choices[0].message.content
                
        except Exception as e:
            print(f"LLM調用出錯: {str(e)}")
            raise

    def chat_stream_by_sentence(self, messages: List[Dict[str, Any]], temperature=0.5) -> Generator[str, None, str]:
        """與LLM互動，按句子流式返回結果
        
        Args:
            messages: 訊息列表
            temperature: 溫度參數，控制隨機性
            
        Yields:
            str: 每個完整句子
            
        Returns:
            str: 完整回應
        """
        try:
            response = self.client.chat.completions.create(
                model="google/gemma-3-12b",
                #model="qwen/qwen3-coder-30b",
                #model="gpt-oss-20b@q6_k",
                #model="llama-breeze2-8b-instruct-text-i1@q6_k",
                #model="llama-breeze2-8b-instruct-text-i1@q4_k_m",
                #model="gpt-4o-mini-2024-07-18",
                #model="deepseek-chat",
                messages=messages,
                temperature=temperature,
                stream=True
            )
            
            full_response = ""
            current_sentence = ""
            
            # 中文的結束標點 - 這些可以直接作為句子結束符
            cn_end_marks = '。！？'
            # 英文的結束標點 - 這些需要檢查後續字元
            en_end_marks = '.!?;'
            
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    current_sentence += content
                    full_response += content
                    
                    # 情況1: 包含中文結束標點，直接作為句子結束
                    if any(char in cn_end_marks for char in content):
                        sentence = current_sentence.strip()
                        # 只有句子長度超過10字才yield
                        if sentence and len(sentence) >= 10:
                            yield sentence
                            current_sentence = ""
                    
                    # 情況2: 檢查英文結束標點後是否跟著空格或換行符
                    elif any(char in en_end_marks for char in content):
                        # 檢查當前累積的句子中是否有 "英文結束標點+空格/換行" 的模式
                        import re
                        # 匹配 句點/感嘆號/問號/分號 後跟空白字元的模式
                        matches = list(re.finditer(r'[.!?;][\s\n]', current_sentence))
                        
                        if matches:
                            # 找到最後一個匹配，在該位置分割句子
                            last_match = matches[-1]
                            end_position = last_match.end() - 1  # 減1是為了不包含空格/換行符
                            
                            sentence = current_sentence[:end_position].strip()
                            remaining = current_sentence[end_position:].strip()
                            
                            # 只有句子長度超過10字才yield
                            if sentence and len(sentence) >= 10:
                                yield sentence
                                current_sentence = remaining
            
            # 處理剩餘內容
            if current_sentence.strip():
                sentence = current_sentence.strip()
                if sentence:
                    yield sentence
            
            return full_response
                
        except Exception as e:
            print(f"LLM調用出錯: {str(e)}")
            yield f"生成回應時出錯: {str(e)}"
            raise


# 嵌入模型
class EmbeddingModel:
    _instance: Optional[HuggingFaceEmbeddings] = None

    @classmethod
    def get_instance(cls) -> HuggingFaceEmbeddings:
        """獲取嵌入模型單例"""
        if cls._instance is None:
            # 檢查CUDA可用性
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                elif torch.mps.is_available():
                    device = "mps"
                elif torch.xpu.is_available():
                    device = "xpu"
                else:
                    device = "cpu"
            except ImportError:
                device = "cpu"
                
            logging.info(f"初始化嵌入模型: {EMBEDDING_MODEL_NAME}，使用設備: {device}")
            
            cls._instance = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL_NAME,
                model_kwargs={"device": device},
                encode_kwargs={"normalize_embeddings": True}
            )
        return cls._instance

# 使用示例
if __name__ == "__main__":
    # 設定日誌
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # LLM客戶端示例
    logger.info("測試LLM客戶端...")
    llm = LLMClient()
    messages = [
        {"role": "user", "content": "你好"}
    ]
    response = llm.chat(messages)
    logger.info(f"LLM回應: {response}")
    
    # 嵌入模型示例
    logger.info("測試嵌入模型...")
    text = "這是一個測試文本"
    embedding_model = EmbeddingModel.get_instance()
    embedding = embedding_model.embed_query(text)
    logger.info(f"嵌入向量維度: {len(embedding)}")