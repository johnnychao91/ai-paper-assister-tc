from pathlib import Path
import logging

from magic_pdf.data.data_reader_writer import FileBasedDataWriter, FileBasedDataReader
from magic_pdf.data.dataset import PymuDocDataset
from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze

logger = logging.getLogger(__name__)

class PDFProcessor:
    """PDF處理器：將PDF轉換為Markdown格式"""
    
    def __init__(self):
        """
        初始化PDF處理器
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.logger.debug("初始化PDF處理器")

    def process(self, pdf_path: str, output_dir: str) -> Path:
        """
        處理PDF檔案
        
        Args:
            pdf_path: PDF檔案路徑
            output_dir: 輸出目錄路徑

        Returns:
            Path: 生成的Markdown檔案路徑
        
        Raises:
            FileNotFoundError: 當PDF檔案不存在時
        """
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF檔案不存在: {pdf_path}")

        try:
            # 設置輸出路徑
            paper_name = pdf_path.stem
            output_image_path = output_dir / "images"
            local_image_path = 'images'
            
            # 初始化圖片寫入器
            image_writer = FileBasedDataWriter(str(output_image_path))
            md_writer = FileBasedDataWriter(str(output_dir))
            
            # 讀取PDF檔案
            reader = FileBasedDataReader("")
            pdf_bytes = reader.read(pdf_path)  # 讀取PDF內容
            
            # 建立資料集實例
            ds = PymuDocDataset(pdf_bytes)
            
            # 處理PDF
            self.logger.info("開始PDF處理流程...")
            ds.apply(doc_analyze, ocr=True).pipe_ocr_mode(image_writer).dump_md(md_writer, f"{paper_name}.md", local_image_path)
            
            # 生成Markdown路徑
            markdown_path = output_dir / f"{paper_name}.md"
            
            self.logger.info(f"Markdown檔案已保存到: {markdown_path}")
            return markdown_path
            
        except Exception as e:
            self.logger.error(f"PDF處理失敗: {str(e)}", exc_info=True)
            raise
