import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple

class JsonProcessor:
    """
    JSON處理器：順序掃描章節內容，保證文字塊的輸出順序與原行一致，
    並能將腳註行（上一行或下一行）合併到圖片塊的caption中。
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # 匹配行間公式：整行只包含 $$...$$
        self.formula_pattern = re.compile(r"^\s*\${2}(?P<formula>.*?)\${2}\s*$", re.DOTALL)

        # 匹配Markdown圖片：形如 ![alt](path/to/img.png)
        self.image_pattern = re.compile(r'^!\[.*?\]\(.*?\)')

        # 匹配HTML表格：形如 <html><body><table>...</table></body></html>
        self.table_pattern = re.compile(r'^<html><body><table>.*?</table></body></html>$')

        # 匹配圖片說明
        self.figure_caption_pattern = re.compile(r'''
            ^(?:
                (?:Figure|Fig\.)                       # Figure或Fig.
                (?:\s+\(?\d+(?:\.\d+)?\)?\.?:?)       # (1), 1:, 1., (1.1), 1.1:等
                |
                (?:IMAGE|DIAGRAM)                      # IMAGE或DIAGRAM
                (?:\s+\d+:?)                          # 1:, 1
                |
                (?:Figure)                            # Figure
                (?:\s+[IVX]+:?)                       # I:, II, III, IV等
            )
        ''', re.IGNORECASE | re.VERBOSE)

        # 匹配表格說明
        self.table_caption_pattern = re.compile(r'''
            ^(?:
                (?:Table|Tab\.)                        # Table或Tab.
                (?:\s+\(?\d+(?:\.\d+)?\)?\.?:?)       # (1), 1:, 1., (1.1), 1.1:等
                |
                (?:Table)                             # Table
                (?:\s+[IVX]+:?)                       # I:, II, III, IV等
            )
        ''', re.IGNORECASE | re.VERBOSE)

    def process(self, input_path: str, output_path: str) -> Path:
        """
        讀取 input.json ，遞迴地處理其 sections（含子章節），
        對每個section的 content 做順序掃描拆分，並寫入 output.json。
        """
        try:
            input_path = Path(input_path)
            output_path = Path(output_path)

            self.logger.info(f"開始處理JSON檔案: {input_path}")
            with input_path.open('r', encoding='utf-8') as f:
                data = json.load(f)

            # 處理頂層 sections
            sections = data.get("sections", [])
            processed_sections = []
            for sec in sections:
                processed_sections.append(self._process_section(sec))

            data["sections"] = processed_sections

            # 輸出結果
            self.logger.info(f"保存處理結果到: {output_path}")
            with output_path.open('w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return output_path

        except Exception as e:
            self.logger.error(f"JSON處理失敗: {str(e)}", exc_info=True)
            raise

    def _process_section(self, section: Dict[str, Any]) -> Dict[str, Any]:
        """
        處理單個章節：
         - 對當前section的 content 做行級順序掃描，拆分成 figure / table/ formula / text 塊
         - 遞迴處理其子章節 (children)
        """
        # 如果type為references，直接返回原section
        if section.get("type") == "references":
            return section

        lines = section.get("content", [])
        blocks = self._split_content_with_order(lines)

        # 用處理後的 blocks 替換原 content
        section["content"] = blocks

        # 遞迴處理子章節
        children = section.get("children", [])
        new_children = []
        for child in children:
            new_children.append(self._process_section(child))
        section["children"] = new_children

        return section

    def _split_content_with_order(self, lines: List[str]) -> List[Dict[str, Any]]:
        """
        單次自上而下掃描，保證塊的輸出順序與原行順序一致。
        """
        blocks = []
        n = len(lines)
        used = [False] * n  # 標記哪些行已被處理

        i = 0
        while i < n:
            if used[i]:
                i += 1
                continue

            line = lines[i].rstrip('\n')
            stripped = line.strip()

            # 1) 行間公式
            m_formula = self.formula_pattern.match(stripped)
            if m_formula:
                formula_body = m_formula.group("formula")
                blocks.append({
                    "type": "formula",
                    "content": f"$$ {formula_body} $$"
                })
                used[i] = True
                i += 1
                continue

            # 2) 處理圖片
            m_img = self.image_pattern.match(stripped)
            if m_img:
                used[i] = True
                alt_text, src = self._extract_alt_and_src(stripped)
                
                caption_line = ""
                caption_index = None

                # 檢查上下文是否有圖片說明
                caption_line, caption_index = self._find_caption(
                    lines, i, used, self.figure_caption_pattern
                )

                # 如果找到說明，標記已使用
                if caption_line and caption_index is not None:
                    used[caption_index] = True

                fig_block = {
                    "type": "figure",
                    "src": src,
                    "alt": alt_text
                }
                if caption_line:
                    fig_block["caption"] = caption_line

                blocks.append(fig_block)
                i += 1
                continue

            # 3) 處理表格
            m_table = self.table_pattern.match(stripped)
            if m_table:
                used[i] = True
                
                caption_line = ""
                caption_index = None

                # 檢查上下文是否有表格說明
                caption_line, caption_index = self._find_caption(
                    lines, i, used, self.table_caption_pattern
                )

                # 如果找到說明，標記已使用
                if caption_line and caption_index is not None:
                    used[caption_index] = True

                table_block = {
                    "type": "table",
                    "content": stripped
                }
                if caption_line:
                    table_block["caption"] = caption_line

                blocks.append(table_block)
                i += 1
                continue

            # 4) 處理普通文字，跳過caption
            if (not self.figure_caption_pattern.match(stripped) and 
                not self.table_caption_pattern.match(stripped)):
                text_block = {
                    "type": "text",
                    "content": line
                }
                used[i] = True
                blocks.append(text_block)
            else:
                # 如果是caption，僅增加索引
                i += 1
                continue
            
            i += 1

        return blocks

    def _find_caption(self, lines: List[str], current_index: int, used: List[bool], 
                     caption_pattern: re.Pattern) -> Tuple[str, int]:
        """查找圖片或表格的說明文字"""
        n = len(lines)
        
        # 優先檢查上一行
        if current_index - 1 >= 0 and not used[current_index - 1]:
            prev_stripped = lines[current_index - 1].strip()
            if caption_pattern.match(prev_stripped):
                return prev_stripped, current_index - 1

        # 再檢查下一行
        if current_index + 1 < n and not used[current_index + 1]:
            next_stripped = lines[current_index + 1].strip()
            if caption_pattern.match(next_stripped):
                return next_stripped, current_index + 1

        return "", None

    def _extract_alt_and_src(self, image_markdown_line: str) -> Tuple[str, str]:
        """
        從 ![alt文字](path/to/xxx.png) 的行裡解析 alt / src。
        """
        pattern = re.compile(r'!\[(?P<alt>.*?)\]\((?P<src>.*?)\)')
        m = pattern.match(image_markdown_line)
        if not m:
            return "", ""
        return m.group("alt"), m.group("src")


if __name__ == "__main__":
    processor = JsonProcessor()
    try:
        output_path = processor.process("input.json","output.json")
        print(f"處理完成，輸出檔案：{output_path}")
    except Exception as e:
        print(f"處理失敗：{e}")