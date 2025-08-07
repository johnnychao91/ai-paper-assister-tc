import re
import json
import logging
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path

# 配置日誌
logger = logging.getLogger(__name__)

@dataclass
class Section:
    title: str            # 完整標題（包含編號和文字）
    number: str           # 章節編號（如 "1.2.3"）
    level: int           # 層級深度（根據編號中的點數確定）
    content: List[str]   # 章節內容，每個段落作為列表的一個元素
    raw_title: str       # 不含編號的標題文字
    type: Optional[str] = None   # 章節類型,如 'abstract', 'references'

class MarkdownProcessor:
    """Markdown處理器：將Markdown解析為結構化JSON"""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # 匹配標題的正則表達式（匹配 # 開頭的行）
        self.title_pattern = re.compile(r'^(#+)\s*(\S.*?)$')
        
        # 匹配摘要標題的正則表達式（匹配 ABSTRACT 或其變體）
        self.abstract_pattern = re.compile(r'^#?\s*(?:\d+\.)?\s*(?:ABSTRACT|Abstract|abstract)')
        
        # 匹配參考文獻標題的正則表達式
        self.reference_pattern = re.compile(r'^#?\s*(?:\d+\.)?\s*(?:REFERENCES?|References?|references?)')

        # 匹配不帶#的參考文獻行
        self.reference_line_pattern = re.compile(r'^(?:REFERENCES?|References?|references?)(?:\s*:|\s*\.)?\s*$')
        
        # 匹配章節編號的正則表達式（如 1.2.3）
        self.section_number_pattern = re.compile(r'^(\d+(?:\.\d+)*)(\.?)\s*(.*?)$')
        
        # 匹配可能的標題行（非 # 開頭，但包含數字編號和大寫標題）
        self.potential_title_pattern = re.compile(r'^(?!#)(\d+(?:\.\d+)*)\s+([A-Z][A-Z\s\d:]+(?:\s*[A-Z][A-Za-z\s\d:]+)*)')

        # 匹配可能的圖表說明
        self.figure_table_pattern = re.compile(r'''
            ^(?:
                (?:Figure|Fig\.|Table|Tab\.)          # Figure, Fig., Table, Tab.
                (?:\s+\(?\d+(?:\.\d+)?\)?\.?:?)       # (1), 1:, 1., (1.1), 1.1:, etc.
                |
                (?:IMAGE|DIAGRAM)                     # IMAGE, DIAGRAM
                (?:\s+\d+:?)                          # 1:, 1
                |
                (?:Figure|Table)                      # Figure, Table  
                (?:\s+[IVX]+:?)                       # I:, II, III, IV, etc.
            )
            ''', re.IGNORECASE | re.VERBOSE)

        # 匹配Markdown格式的圖片
        self.image_pattern = re.compile(r'^!\[.*?\]\(.*?\)')
        
        # 匹配數學公式塊
        self.latex_block_pattern = re.compile(r'^\$\$')

        self.logger.debug("初始化Markdown處理器完成")
        
    def parse_section_number(self, title: str) -> tuple[str, str, int]:
        """解析章節標題，提取編號、原始標題和層級深度"""
        match = self.section_number_pattern.match(title)
        if match:
            number, dot, raw_title = match.groups()
            # 忽略末尾的點號
            level = len(number.split('.'))  # 通過點號數量確定層級
            return number.strip(), raw_title.strip(), level
        return '', title.strip(), 1  # 如果沒有編號，返回預設值

    def parse_references(self, content: str) -> List[str]:
        """將參考文獻內容解析為列表"""
        # 按換行符分割內容並過濾空行
        references = [line.strip() for line in content.split('\n') if line.strip()]
        return references

    def parse_content(self, content: List[str]) -> List[str]:
        """將內容解析為段落列表"""
        text = '\n'.join(content)
        paragraphs = []
        current_para = []
        
        in_latex_block = False
        latex_content = []
        
        for line in text.split('\n'):
            line = line.strip()
            
            # 檢查是否是LaTeX塊的開始或結束
            if self.latex_block_pattern.match(line):
                if in_latex_block:
                    # LaTeX塊結束
                    latex_content.append(line)
                    paragraphs.append('\n'.join(latex_content))
                    latex_content = []
                    in_latex_block = False
                else:
                    # LaTeX塊開始
                    if current_para:
                        paragraphs.append('\n'.join(current_para).strip())
                        current_para = []
                    latex_content.append(line)
                    in_latex_block = True
                continue
                
            if in_latex_block:
                latex_content.append(line)
                continue
            
            if not line:
                if current_para:
                    paragraphs.append('\n'.join(current_para).strip())
                    current_para = []
                continue
                
            # 檢查是否是圖片引用或圖表說明
            if self.image_pattern.match(line) or self.figure_table_pattern.match(line):
                if current_para:
                    paragraphs.append('\n'.join(current_para).strip())
                    current_para = []
                paragraphs.append(line)
                continue
                
            current_para.append(line)
            
        if current_para:
            paragraphs.append('\n'.join(current_para).strip())
            
        return paragraphs

    def find_missing_sections(self, content: str, current_prefix: str) -> Tuple[List[Section], List[str]]:
        """在章節內容中查找可能遺漏的章節標題，並重新分配內容"""
        missing_sections = []
        lines = content.split('\n')
        section_start_indices = []
        
        # 查找所有可能的章節標題行
        for i, line in enumerate(lines):
            match = self.potential_title_pattern.match(line)
            if match:
                number, title_text = match.groups()
                # 只處理與當前前綴匹配的章節
                if number.startswith(current_prefix):
                    section_start_indices.append((i, number, title_text))
        
        if not section_start_indices:
            return [], self.parse_content(lines)
            
        # 更新原章節的內容（只保留第一個遺漏章節之前的內容）
        original_content = self.parse_content(lines[:section_start_indices[0][0]])
        
        # 處理找到的每個章節
        for idx in range(len(section_start_indices)):
            start_idx, number, title_text = section_start_indices[idx]
            # 確定章節內容的結束位置
            end_idx = section_start_indices[idx + 1][0] if idx < len(section_start_indices) - 1 else len(lines)
            section_content = self.parse_content(lines[start_idx + 1:end_idx])
            
            # 解析章節資訊並建立 Section 物件
            number, raw_title, level = self.parse_section_number(f"{number} {title_text}")
            missing_sections.append(Section(
                title=f"{number} {title_text}",
                number=number,
                level=level,
                content=section_content,
                raw_title=raw_title
            ))
        
        return missing_sections, original_content

    def remove_empty_sections(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """遞迴移除內容和子章節都為空的章節"""
        if not sections:
            return []

        result = []
        for section in sections:
            # 遞迴處理子章節
            if 'children' in section:
                section['children'] = self.remove_empty_sections(section['children'])
            
            # 檢查章節是否為空（沒有內容且沒有子章節）
            content_empty = not section.get('content', [])
            children_empty = not section.get('children', [])
            references_empty = not section.get('references', [])
            
            # 如果章節不為空，或者有參考文獻，保留該章節
            if not (content_empty and children_empty and references_empty):
                result.append(section)

        return result

    def check_section_continuity(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """檢查同級章節的編號連續性，查找並補充遺漏的章節"""
        # 按章節編號排序
        sections.sort(key=lambda x: int(x['number'].split('.')[-1]))
        
        all_sections = sections.copy()
        section_numbers = [int(s['number'].split('.')[-1]) for s in sections]
        
        # 檢查相鄰章節編號的連續性
        i = 0
        while i < len(section_numbers) - 1:
            current_num = section_numbers[i]
            next_num = section_numbers[i + 1]
            
            # 如果存在編號跳躍
            if next_num - current_num > 1:
                current_section = sections[i]
                # 構造章節編號前綴
                prefix = '.'.join(current_section['number'].split('.')[:-1])
                if prefix:
                    prefix += '.'
                
                # 在當前章節內容中查找遺漏的章節
                missing_sections, updated_content = self.find_missing_sections(
                    '\n'.join(current_section['content']), 
                    prefix
                )
                
                if missing_sections:
                    print(f"在 {current_section['number']} 之後找到遺漏的章節：")
                    for section in missing_sections:
                        print(f"  - {section.title}")
                    
                    # 更新原章節的內容
                    current_section['content'] = updated_content
                    
                    # 將找到的章節插入到適當位置
                    for missing_section in missing_sections:
                        missing_dict = vars(missing_section)
                        # 確保每個章節字典都有 children 欄位
                        missing_dict['children'] = []
                        # 找到正確的插入位置
                        insert_idx = next((j for j, s in enumerate(all_sections) 
                                        if s['number'] > missing_section.number), len(all_sections))
                        all_sections.insert(insert_idx, missing_dict)
                    
                    # 更新章節編號列表
                    section_numbers = [int(s['number'].split('.')[-1]) for s in all_sections]
                    i = 0  # 重新開始檢查，因為可能有新的不連續性
                    continue
            
            i += 1
        
        return all_sections

    def build_hierarchy(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """構建章節的層級結構"""
        hierarchy = []
        section_map = {}  # 用於快速查找章節
        level_groups = defaultdict(list)  # 按父章節分組的子章節
        
        # 第一次遍歷：構建基本的層級關係
        for section in sections:
            section['children'] = []
            if not section['number']:  # 處理沒有編號的章節
                hierarchy.append(section)
                continue
                
            numbers = section['number'].split('.')
            
            if len(numbers) == 1:  # 頂層章節
                hierarchy.append(section)
                section_map[section['number']] = section
            else:
                parent_number = '.'.join(numbers[:-1])
                if parent_number in section_map:
                    # 將同級章節歸類
                    level_groups[parent_number].append(section)
                    section_map[section['number']] = section
                else:
                    # 如果找不到父章節，作為頂層章節處理
                    hierarchy.append(section)
                    section_map[section['number']] = section
        
        # 第二次遍歷：處理每組同級章節
        for parent_number, group in level_groups.items():
            # 檢查同級章節的連續性
            updated_group = self.check_section_continuity(group)
            
            # 更新父章節的 children
            if parent_number in section_map:
                section_map[parent_number]['children'] = updated_group
                
                # 更新 section_map
                for section in updated_group:
                    section_map[section['number']] = section
        
        return hierarchy

    def parse(self, content: str) -> Dict[str, Any]:
        """解析整個 Markdown 文檔"""
        lines = content.split('\n')
        result = {
            'title': '',           # 文檔標題
            'authors_info': '',    # 作者資訊
            'sections': []         # 章節列表
        }
        
        current_section = None     # 當前正在處理的章節
        current_content = []       # 當前章節的內容行
        collecting_authors = False # 是否正在收集作者資訊
        in_references = False      # 是否已到參考文獻部分
        authors_content = []       # 作者資訊內容
        has_started = False       # 文檔解析是否已開始
        
        # 逐行處理文檔
        for line in lines:
            title_match = self.title_pattern.match(line)

            # 檢查是否是非標準格式的參考文獻行
            reference_line_match = None
            if not in_references and not title_match:
                reference_line_match = self.reference_line_pattern.match(line)
            
            # 跳過文檔開始前的空行
            if not has_started and not title_match:
                continue

            # 處理僅包含 # 但後面無內容的行
            if line.strip().startswith('#') and not title_match:
                # 直接忽略這一行，不作為內容處理
                continue
            

            # 處理非標準格式的參考文獻行
            if reference_line_match:
                # 保存當前章節（如果有）
                if current_section:
                    current_section.content = self.parse_content(current_content)
                    result['sections'].append(vars(current_section))
                
                # 建立新的參考文獻章節
                current_section = Section(
                    title="REFERENCES",
                    number="",
                    level=1,
                    content=[],
                    raw_title="REFERENCES",
                    type='references'
                )
                # 提取參考文獻行中REFERENCES後面的內容作為第一條參考文獻
                reference_content = re.sub(r'^(?:REFERENCES?|References?|references?)\s*', '', line).strip()
                current_content = [reference_content] if reference_content else []
                in_references = True
                continue

            elif title_match:
                heading_level = len(title_match.group(1))  # 標題級別（# 的數量）
                title_text = title_match.group(2).strip()  # 標題文字
                
                # 處理文檔標題
                if not has_started:
                    result['title'] = title_text
                    # collecting_authors = True
                    has_started = True
                    continue
                
                # 處理摘要部分
                if self.abstract_pattern.match(line):
                    # 獲取完整的作者資訊文字
                    authors_text = '\n'.join(authors_content).strip()
                    authors_lines = authors_text.split('\n')
                    
                    # 使用已有的正則表達式篩選圖片和圖表說明
                    image_lines = []
                    clean_authors_lines = []
                    
                    for line in authors_lines:
                        if self.image_pattern.match(line) or self.figure_table_pattern.match(line):
                            image_lines.append(line)
                        else:
                            clean_authors_lines.append(line)
                    
                    # 保存清理後的作者資訊
                    result['authors_info'] = '\n'.join(clean_authors_lines).strip()
                    collecting_authors = False
                    
                    # 建立 abstract 章節
                    number, raw_title, level = self.parse_section_number(title_text)
                    current_section = Section(
                        title=title_text,
                        number=number,
                        level=level,
                        content=[],
                        raw_title=raw_title,
                        type='abstract'
                    )
                    current_content = []
                    # 將找到的圖片資訊添加到 current_content
                    current_content.extend(image_lines)
                    continue
                
                # 收集作者資訊
                if collecting_authors:
                    authors_content.append(title_text)
                    continue
                
                # 保存當前章節並開始新章節
                if current_section and not collecting_authors:
                    if in_references:
                        # 如果是參考文獻章節，將內容解析為列表
                        current_section.content = self.parse_references('\n'.join(current_content))
                        result['sections'].append(vars(current_section))
                        break  # 處理完參考文獻後直接跳出
                    else:
                        # 如果是摘要章節，需要特殊處理
                        if self.abstract_pattern.match(current_section.title):
                            # 分離圖片/圖表內容和其他內容
                            parsed_content = []
                            other_lines = []
                            
                            for line in current_content:
                                if self.image_pattern.match(line) or self.figure_table_pattern.match(line):
                                    # 將圖片和圖表說明作為單獨的項
                                    parsed_content.append(line)
                                else:
                                    other_lines.append(line)
                            
                            # 將其他內容作為一個整體添加
                            if other_lines:
                                parsed_content.extend(self.parse_content(other_lines))
                                
                            current_section.content = parsed_content
                        else:
                            current_section.content = self.parse_content(current_content)
                        
                        result['sections'].append(vars(current_section))
                
                # 建立新章節
                number, raw_title, level = self.parse_section_number(title_text)
                current_section = Section(
                    title=title_text,
                    number=number,
                    level=level,
                    content=[],
                    raw_title=raw_title
                )
                current_content = []
                
                # 檢查是否進入參考文獻部分
                if self.reference_pattern.match(line):
                    in_references = True
                    current_section.type = 'references'
                    
            else:
                # 收集當前行的內容
                if collecting_authors:
                    authors_content.append(line)
                else:
                    current_content.append(line)
        
        # 構建層級結構（包含連續性檢查）
        result['sections'] = self.build_hierarchy(result['sections'])

        # 移除空章節
        result['sections'] = self.remove_empty_sections(result['sections'])
        
        return result

    def process(self, markdown_path: str, output_path: str) -> Path:
        """將原來獨立的 process_markdown_file 函數集成為類方法"""
        try:
            markdown_path = Path(markdown_path)
            output_path = Path(output_path)
            
            # 讀取檔案
            self.logger.info(f"開始解析Markdown檔案: {markdown_path}")
            content = markdown_path.read_text(encoding='utf-8')
            
            # 使用原有的 parse 方法解析
            result = self.parse(content)
            
            # 保存結果
            self.logger.info(f"保存解析結果到: {output_path}")
            output_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            
            return output_path
            
        except Exception as e:
            self.logger.error(f"Markdown處理失敗: {str(e)}", exc_info=True)
            raise

if __name__ == "__main__":
    processor = MarkdownProcessor()
    try:
        json_path = processor.process("input.md", "output.json")
    except Exception as e:
        print(f"處理失敗：{e}")