"""붉은 선/글자 기반 말소 감지"""
from typing import Dict, List, Tuple, Set


class CancellationDetector:
    """페이지별 붉은 선/글자 기반 말소 감지"""

    def __init__(self):
        # page_index -> set of y-coordinate ranges that are cancelled
        self._cancelled_y_ranges: Dict[int, List[Tuple[float, float]]] = {}
        # page_index -> set of cancelled char y-coords
        self._cancelled_char_ys: Dict[int, Set[float]] = {}

    def analyze_page(self, page, page_index: int):
        """페이지의 붉은 선, 붉은 사각형, 붉은 글자 분석"""
        # 붉은 선 수집
        red_line_ys = set()
        for line in (page.lines or []):
            color = line.get('stroking_color')
            if self._is_red(color):
                y = round(line['top'], 0)
                red_line_ys.add(y)

        # 붉은 사각형(박스형 말소 표시) 수집
        for rect in (page.rects or []):
            color = rect.get('stroking_color') or rect.get('non_stroking_color')
            if self._is_red(color):
                top = round(rect['top'], 0)
                bottom = round(rect['bottom'], 0)
                # 사각형의 전체 높이 범위를 말소 영역으로 등록
                for y in range(int(top), int(bottom) + 1):
                    red_line_ys.add(float(y))

        if red_line_ys:
            ranges = []
            for y in sorted(red_line_ys):
                ranges.append((y - 6, y + 6))  # 선 위아래 6pt 범위
            self._cancelled_y_ranges[page_index] = self._merge_ranges(ranges)

        # 붉은 글자 y좌표 수집
        red_char_ys = set()
        for ch in (page.chars or []):
            sc = ch.get('stroking_color')
            nsc = ch.get('non_stroking_color')
            if self._is_red(sc) or self._is_red(nsc):
                red_char_ys.add(round(ch['top'], 0))
        if red_char_ys:
            self._cancelled_char_ys[page_index] = red_char_ys

    def is_row_cancelled(self, page_index: int, row_y: float) -> bool:
        """해당 페이지의 y좌표가 말소 영역인지 확인"""
        y = round(row_y, 0)

        # 붉은 선 범위 체크
        ranges = self._cancelled_y_ranges.get(page_index, [])
        for y_min, y_max in ranges:
            if y_min <= y <= y_max:
                return True

        # 붉은 글자 y좌표 체크
        char_ys = self._cancelled_char_ys.get(page_index, set())
        for cy in char_ys:
            if abs(cy - y) <= 6:
                return True

        return False

    def is_table_row_cancelled(self, page_index: int, row_cells_y: List[float]) -> bool:
        """테이블 행의 셀들 y좌표로 말소 여부 판단"""
        if not row_cells_y:
            return False
        # 셀 y좌표 중 하나라도 말소 영역에 있으면 말소
        for y in row_cells_y:
            if self.is_row_cancelled(page_index, y):
                return True
        return False

    @staticmethod
    def _is_red(color) -> bool:
        if not color:
            return False
        if isinstance(color, (list, tuple)):
            if len(color) >= 3:
                r, g, b = color[0], color[1], color[2]
                if isinstance(r, (int, float)):
                    # RGB 0-1 스케일
                    if r > 0.7 and g < 0.3 and b < 0.3:
                        return True
                    # RGB 0-255 스케일
                    if r > 180 and g < 80 and b < 80:
                        return True
            elif len(color) == 4:
                c, m, y_val, k = color
                if m > 0.5 and y_val > 0.3 and c < 0.2:
                    return True
        return False

    @staticmethod
    def _merge_ranges(ranges: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        if not ranges:
            return []
        sorted_ranges = sorted(ranges)
        merged = [sorted_ranges[0]]
        for start, end in sorted_ranges[1:]:
            if start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged
