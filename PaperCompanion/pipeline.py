import os
from pathlib import Path
import json
import logging
from typing import Optional, Dict, List, Union
from .processor.pdf_processor import PDFProcessor
from .processor.md_processor import MarkdownProcessor
from .processor.json_processor import JsonProcessor
from .processor.tiling_processor import TilingProcessor
from .processor.translate_processor import TranslateProcessor
from .processor.md_restore_processor import RestoreProcessor
from .processor.extra_info_processor import ExtraInfoProcessor
from .processor.rag_processor import RagProcessor
from PyQt6.QtCore import QObject, pyqtSignal

from .config import ONLINE_MODE

# 配置日志
logger = logging.getLogger(__name__)

class Pipeline(QObject):
    """學術論文處理管線"""
    # 新增進度更新信號
    progress_updated = pyqtSignal(dict)  # 發送stage_info字典
    
    def __init__(self, stages: Optional[List[str]] = None):
        """
        初始化處理管線
        
        Args:
            stages: 需要運行的處理階段列表
                   可選值: ['pdf2md', 'md2json', 'json_process', 
                          'tiling', 'translate', 'md_restore', 'extra_info', 'rag']
        """
        super().__init__()  # 呼叫QObject初始化
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # 設定基礎路徑
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        # 確定是否為ONLINE MODE，跳過API呼叫部分
        self.online_mode = ONLINE_MODE

        # 定義階段識別符和對應的處理函數
        self.stage_identifiers = {
            'pdf2md': '',
            'md2json': '_structured',
            'json_process': '_processed',
            'tiling': '_tiled',
            'translate': '_translated',
            'md_restore': '_restored',
            'extra_info': '_extra_info',
            'rag': '_rag'
        }
        
        self.available_stages = {
            'pdf2md': self._stage_pdf_to_md,
            'md2json': self._stage_md_to_json,
            'json_process': self._stage_json_process,
            'tiling': self._stage_tiling,
            'translate': self._stage_translate,
            'md_restore': self._stage_md_restore,
            # 'extra_info': self._stage_extra_info,
            'rag': self._stage_rag
        }

        self.offline_skip_stages = {
            "translate", "md_restore", "rag"
        }
        self.stages = stages or list(self.available_stages.keys())
        self.logger.debug("初始化處理階段: %s", self.stages)
        
        # 初始化處理器
        self.pdf_processor = PDFProcessor()
        self.md_processor = MarkdownProcessor()
        self.json_processor = JsonProcessor()
        self.tiling_processor = TilingProcessor()
        self.translate_processor = TranslateProcessor(self.base_path)
        self.restore_processor = RestoreProcessor()
        self.extra_info_processor = ExtraInfoProcessor(self.base_path)
        self.rag_processor = RagProcessor()
        
        # 論文處理狀態
        self.paper_info = {
            'paper_id': None,     # 論文ID（基於PDF檔案名）
            'output_dir': None    # 輸出目錄
        }

        # 新增追蹤當前處理階段的屬性
        self._current_stage = None

    def _get_stage_output_path(self, stage: str, paper_dir: Path, paper_name: str) -> Path:
        """
        獲取特定階段的輸出檔案路徑
        
        Args:
            stage: 處理階段名稱
            paper_dir: 論文輸出目錄
            paper_name: 論文名稱
            
        Returns:
            Path: 輸出檔案路徑
        """
        identifier = self.stage_identifiers.get(stage, '')
        if stage == 'pdf2md':
            return paper_dir / f"{paper_name}{identifier}.md"
        elif stage == 'md_restore':
            # 對於restore階段，返回一個包含英文和中文輸出路徑的字典
            return {
                'en': paper_dir / f"final_{paper_name}_en.md",
                'zh': paper_dir / f"final_{paper_name}_zh.md"
            }
        elif stage == 'rag':
            # 對於RAG階段，返回一個包含md、tree_json和vector_store輸出路徑的字典
            return {
                'md': paper_dir / f"final_{paper_name}_rag.md",
                'tree_json': paper_dir / f"final_{paper_name}_rag_tree.json",
                'vector_store': paper_dir / "vectors"
            }
        else:
            return paper_dir / f"{paper_name}{identifier}.json"
        
    def get_current_stage(self) -> Dict[str, any]:
        """
        獲取當前處理階段的資訊
        
        Returns:
            Dict: 包含當前階段資訊的字典，格式為:
                {
                    'stage': 當前階段名稱,
                    'stage_name': 當前階段顯示名稱,
                    'index': 當前階段在所有階段中的索引位置,
                    'total': 總階段數,
                    'progress': 完成百分比,
                    'stage_progress': 當前階段內部進度
                }
        """
        # 階段名稱的友好顯示映射
        stage_names = {
            'pdf2md': 'PDF轉Markdown',
            'md2json': 'Markdown轉JSON',
            'json_process': 'JSON處理',
            'tiling': '分段處理',
            'translate': '內容翻譯',
            'md_restore': '產生Markdown文檔',
            'extra_info': '提取額外資訊',
            'rag': 'RAG處理'
        }
        
        if self._current_stage is None:
            return {
                'stage': None,
                'stage_name': '未開始',
                'index': 0,
                'total': len(self.stages),
                'progress': 0,
                'stage_progress': 0
            }
        
        current_index = self.stages.index(self._current_stage) if self._current_stage in self.stages else -1
        
        result = {
            'stage': self._current_stage,
            'stage_name': stage_names.get(self._current_stage, self._current_stage),
            'index': current_index + 1,
            'total': len(self.stages),
            'progress': int((current_index + 1) / len(self.stages) * 100) if current_index >= 0 else 0,
            'stage_progress': 0  # 可以根據需要新增階段內進度
        }
        
        # 發送進度更新信號
        self.progress_updated.emit(result)
        
        return result
    
    def process(self, pdf_path: str, output_dir: Optional[str] = None) -> Dict[str, Union[Path, Dict[str, Path]]]:
        """
        處理論文的主函數
        
        Args:
            pdf_path: PDF檔案路徑
            output_dir: 輸出目錄，預設為PDF所在目錄

        Returns:
            Dict[str, Path]: 各階段輸出檔案的路徑字典
        """
        try:
            # 規範化路徑
            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF檔案不存在: {pdf_path}")

            # 設定基礎輸出目錄
            base_output_dir = Path(output_dir) if output_dir else pdf_path.parent
            base_output_dir.mkdir(exist_ok=True, parents=True)
            
            # 初始化論文資訊
            self.paper_info['paper_id'] = pdf_path.stem
            
            # 建立輸出目錄
            paper_output_dir = base_output_dir / self.paper_info['paper_id']
            paper_output_dir.mkdir(exist_ok=True)
            self.paper_info['output_dir'] = paper_output_dir
            
            # 儲存各階段的輸出路徑
            output_paths = {}
            
            # 運行選定的處理階段
            for stage in self.stages:
                if stage not in self.available_stages:
                    self.logger.warning(f"未知的處理階段: {stage}")
                    continue

                # If not online_mode then skip api translate feature stage
                if not self.online_mode and stage in self.offline_skip_stages:
                    continue

                # 設定當前階段
                self._current_stage = stage
                self.progress_updated.emit(self.get_current_stage())
                self.logger.info(f"開始運行階段: {stage}")
   
                # 獲取該階段的預期輸出路徑
                expected_output = self._get_stage_output_path(stage, paper_output_dir, self.paper_info['paper_id'])
                
                # 檢查輸出檔案是否已存在
                if stage in ['md_restore', 'rag']:
                    # 對於有多個輸出檔案的階段，檢查所有檔案是否都已存在
                    files_exist = True
                    for _, path in expected_output.items():
                        if not path.exists():
                            files_exist = False
                            break
                            
                    if files_exist:
                        self.logger.info(f"階段 {stage} 的輸出檔案已存在，跳過處理: {expected_output}")
                        output_paths[stage] = expected_output
                        continue
                else:
                    if isinstance(expected_output, Path) and expected_output.exists():
                        self.logger.info(f"階段 {stage} 的輸出檔案已存在，跳過處理: {expected_output}")
                        output_paths[stage] = expected_output
                        continue
                
                # 執行處理階段
                self.logger.info(f"開始運行階段: {stage}")
                stage_output = self.available_stages[stage](
                    pdf_path, paper_output_dir, self.paper_info['paper_id'], output_paths
                )
                output_paths[stage] = stage_output
                self.logger.info(f"階段 {stage} 完成")

            # 處理完成後
            self._current_stage = None
            
            # 如果RAG或MD_RESTORE階段已完成，更新全域索引
            final_paths = {}
            
            # 收集最終檔案路徑
            if 'md_restore' in output_paths:
                restore_paths = output_paths['md_restore']
                final_paths.update({
                    'article_en': restore_paths['en'],
                    'article_zh': restore_paths['zh']
                })
                
            if 'rag' in output_paths:
                rag_paths = output_paths['rag']
                final_paths.update({
                    'rag_md': rag_paths['md'],
                    'rag_tree': rag_paths['tree_json'],
                    'rag_vector_store': rag_paths['vector_store']
                })
                
            # 檢查圖像檔案夾
            images_dir = paper_output_dir / "images"
            if images_dir.exists() and images_dir.is_dir():
                final_paths['images'] = images_dir
                
            # 如果有最終檔案，更新索引
            if final_paths and self.online_mode:
                self._update_global_index(base_output_dir, final_paths)
                output_paths['final'] = final_paths
            
            return output_paths
            
        except Exception as e:
            self.logger.error(f"處理過程出錯: {str(e)}", exc_info=True)
            raise

    def _update_global_index(self, base_output_dir: Path, final_paths: Dict) -> None:
        """
        更新全域論文索引
        
        Args:
            base_output_dir: 基礎輸出目錄
            final_paths: 最終檔案路徑字典
        """
        index_path = base_output_dir / "papers_index.json"
        
        # 讀取現有索引（如果存在）
        papers_index = []
        if index_path.exists():
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    papers_index = json.load(f)
            except json.JSONDecodeError:
                self.logger.warning(f"索引檔案損壞，將建立新索引: {index_path}")
                papers_index = []
        
        # 建構論文條目
        # 將路徑字串化，儲存相對路徑以避免跨機器使用時的問題
        path_dict = {}
        for key, path in final_paths.items():
            if path:
                # 將路徑轉換為相對於基礎輸出目錄的相對路徑
                try:
                    rel_path = path.relative_to(base_output_dir)
                    path_dict[key] = str(rel_path)
                except ValueError:
                    # 如果無法獲取相對路徑，則使用絕對路徑
                    path_dict[key] = str(path)
        
        # 從 rag_tree.json 提取 title 和 translated_title
        title = ""
        translated_title = ""
        if 'rag_tree' in final_paths and Path(final_paths['rag_tree']).exists():
            try:
                with open(final_paths['rag_tree'], 'r', encoding='utf-8') as f:
                    tree_data = json.load(f)
                    title = tree_data.get('title', '')
                    translated_title = tree_data.get('translated_title', '')
                    self.logger.info(f"從RAG樹中提取標題: {title}, 翻譯標題: {translated_title}")
            except Exception as e:
                self.logger.error(f"從RAG樹中提取標題時出錯: {str(e)}")
        
        paper_entry = {
            'id': self.paper_info['paper_id'],
            'title': title,
            'translated_title': translated_title,
            'paths': path_dict,
            'active': False,
        }
        
        # 查找現有條目
        existing_index = -1
        for i, entry in enumerate(papers_index):
            if entry.get('id') == paper_entry['id']:
                existing_index = i
                break
        
        # 更新或新增條目
        if existing_index >= 0:
            papers_index[existing_index] = paper_entry
        else:
            papers_index.append(paper_entry)
        
        # 儲存更新後的索引
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(papers_index, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"全域索引更新完成: {index_path}")

    def _stage_pdf_to_md(self, pdf_path: Path, paper_dir: Path, 
                        paper_name: str, output_paths: dict) -> Path:
        """PDF轉Markdown階段"""
        self.logger.info(f"開始將PDF轉換為Markdown: {pdf_path}")
        try:
            markdown_path = self.pdf_processor.process(
                str(pdf_path),
                str(paper_dir)
            )
            self.logger.info(f"PDF成功轉換為Markdown: {markdown_path}")
            return markdown_path
        except Exception as e:
            self.logger.error(f"PDF轉Markdown失敗: {str(e)}")
            raise

    def _stage_md_to_json(self, pdf_path: Path, paper_dir: Path, 
                         paper_name: str, output_paths: dict) -> Path:
        """Markdown轉結構化JSON階段"""
        self.logger.info("開始將Markdown轉換為JSON")
        try:
            markdown_path = output_paths.get('pdf2md')
            if not markdown_path:
                raise ValueError("未找到前序階段產生的Markdown檔案")

            output_path = self._get_stage_output_path('md2json', paper_dir, paper_name)
            json_path = self.md_processor.process(
                str(markdown_path),
                str(output_path)
            )
            self.logger.info(f"Markdown成功轉換為JSON: {json_path}")
            return json_path
        except Exception as e:
            self.logger.error(f"Markdown轉JSON失敗: {str(e)}")
            raise

    def _stage_json_process(self, pdf_path: Path, paper_dir: Path, 
                          paper_name: str, output_paths: dict) -> Path:
        """JSON處理階段"""
        self.logger.info("開始處理JSON檔案")
        try:
            input_json_path = output_paths.get('md2json')
            if not input_json_path:
                raise ValueError("未找到前序階段產生的JSON檔案")
            
            output_path = self._get_stage_output_path('json_process', paper_dir, paper_name)
            processed_json_path = self.json_processor.process(
                str(input_json_path),
                str(output_path)
            )
            self.logger.info(f"JSON檔案處理完成: {processed_json_path}")
            return processed_json_path
        except Exception as e:
            self.logger.error(f"JSON處理失敗: {str(e)}")
            raise
            
    def _stage_tiling(self, pdf_path: Path, paper_dir: Path, 
                    paper_name: str, output_paths: dict) -> Path:
        """平鋪階段：將處理後的JSON檔案進行平鋪處理"""
        self.logger.info("開始平鋪階段")
        try:
            # 獲取前一階段處理好的JSON檔案路徑
            input_json_path = output_paths.get('json_process')
                
            if not input_json_path:
                raise ValueError("未找到可用於平舖的JSON檔案，請確保已運行前序JSON處理階段")
            
            # 建構輸出檔案路徑
            output_path = self._get_stage_output_path('tiling', paper_dir, paper_name)
            
            # 呼叫平鋪處理器進行平鋪
            tiled_json_path = self.tiling_processor.process(
                str(input_json_path),
                str(output_path)
            )
            
            self.logger.info(f"JSON檔案平鋪完成: {tiled_json_path}")
            return tiled_json_path
        except Exception as e:
            self.logger.error(f"平鋪階段失敗: {str(e)}", exc_info=True)
            raise

    def _stage_translate(self, pdf_path: Path, paper_dir: Path, 
                        paper_name: str, output_paths: dict) -> Path:
        """翻譯階段，使用TranslateProcessor進行JSON檔案的翻譯"""
        self.logger.info("開始翻譯階段")
        try:
            # 獲取前一階段處理好的JSON檔案路徑
            input_json_path = output_paths.get('tiling')  
                
            if not input_json_path:
                raise ValueError("未找到可用於翻譯的JSON檔案，請確保已運行前序平鋪階段")
            
            # 建構輸出檔案路徑
            output_path = self._get_stage_output_path('translate', paper_dir, paper_name)
            
            # 呼叫翻譯處理器進行翻譯
            translated_json_path = self.translate_processor.process(
                str(input_json_path),
                str(output_path)
            )
            
            self.logger.info(f"JSON檔案翻譯完成: {translated_json_path}")
            return translated_json_path
        except Exception as e:
            self.logger.error(f"翻譯階段失敗: {str(e)}", exc_info=True)
            raise

    def _stage_md_restore(self, pdf_path: Path, paper_dir: Path, 
                  paper_name: str, output_paths: dict) -> dict:
        """還原階段：將JSON檔案還原為中英文Markdown文件"""
        self.logger.info("開始還原階段")
        try:
            # 獲取前一階段處理好的翻譯JSON檔案路徑
            input_json_path = output_paths.get('translate')
                
            if not input_json_path:
                raise ValueError("未找到可用於還原的翻譯JSON檔案，請確保已運行前序翻譯階段")
            
            # 獲取該階段的預期輸出路徑字典，直接產生最終路徑
            output_paths_dict = self._get_stage_output_path('md_restore', paper_dir, paper_name)
            output_path_en = output_paths_dict['en']
            output_path_zh = output_paths_dict['zh']
            
            # 呼叫還原處理器
            en_path, zh_path = self.restore_processor.process(
                str(input_json_path),
                str(output_path_en),
                str(output_path_zh)
            )
            
            self.logger.info(f"還原完成: 英文文件 {en_path}, 中文文件 {zh_path}")
            
            # 返回一個字典，包含兩個輸出路徑
            return {
                'en': Path(en_path),
                'zh': Path(zh_path)
            }
        except Exception as e:
            self.logger.error(f"還原階段失敗: {str(e)}", exc_info=True)
            raise

    def _stage_extra_info(self, pdf_path: Path, paper_dir: Path, 
                paper_name: str, output_paths: dict) -> Path:
        """額外資訊提取處理階段，主要產生各章節的總結"""
        self.logger.info("開始額外資訊擷取階段")
        try:
            # 獲取前一階段處理好的JSON檔案路徑，這裡使用翻譯階段的輸出作為輸入
            input_json_path = output_paths.get('translate')
                
            if not input_json_path:
                raise ValueError("未找到可用於提取額外資訊的JSON檔案，請確保已運行前序翻譯階段")
            
            # 建構輸出檔案路徑
            output_path = self._get_stage_output_path('extra_info', paper_dir, paper_name)
            
            # 呼叫額外資訊處理器
            processed_json_path = self.extra_info_processor.process(
                str(input_json_path),
                str(output_path)
            )
            
            self.logger.info(f"額外資訊擷取完成: {processed_json_path}")
            return processed_json_path
        except Exception as e:
            self.logger.error(f"額外資訊擷取階段失敗: {str(e)}", exc_info=True)
            raise

    def _stage_rag(self, pdf_path: Path, paper_dir: Path, 
                paper_name: str, output_paths: dict) -> dict:
        """RAG處理階段：產生用於檢索增強生成的資料結構
        
        該階段將產生三個檔案：
        1. Markdown檔案：用於RAG向量庫的文字內容，以#節點key + 文段內容為基本單位
        2. 樹結構JSON檔案：包含論文的層次結構，與MD檔案中的節點key對應
        3. 向量庫：基於Markdown檔案產生的向量庫，用於檢索增強生成
        """
        self.logger.info("開始RAG處理階段")
        try:
            # 獲取前一階段處理好的JSON檔案路徑
            # 使用extra_info階段的輸出作為輸入，因為它包含了額外的摘要資訊
            input_json_path = output_paths.get('extra_info')
            
            if not input_json_path:
                # 如果沒有extra_info階段的輸出，則使用translate階段的輸出
                input_json_path = output_paths.get('translate')
                
            if not input_json_path:
                raise ValueError("未找到可用於RAG處理的JSON檔案，請確保已執行前序翻譯或額外資訊階段")
            
            # 建構輸出檔案路徑字典，直接產生最終路徑
            output_paths_dict = self._get_stage_output_path('rag', paper_dir, paper_name)
            output_md_path = output_paths_dict['md']
            output_tree_json_path = output_paths_dict['tree_json']
            
            # 獲取向量庫路徑
            vector_store_path = output_paths_dict['vector_store']
            
            # 呼叫RAG處理器
            md_path, tree_json_path, vector_store_path = self.rag_processor.process(
                str(input_json_path),
                str(output_md_path),
                str(output_tree_json_path),
                str(vector_store_path)
            )
            
            self.logger.info(
                f"RAG處理完成: Markdown檔 {md_path}, 樹結構JSON {tree_json_path}, 向量庫 {vector_store_path}"
            )
            
            # 返回一個字典，包含三個輸出路徑
            return {
                'md': Path(md_path),
                'tree_json': Path(tree_json_path),
                'vector_store': Path(vector_store_path)
            }
        except Exception as e:
            self.logger.error(f"RAG處理階段失敗: {str(e)}", exc_info=True)
            raise