"""PDF 구조 분석 도구 — pdfplumber의 lines/chars/rects/tables 분석

Usage:
    python tools/analyze_pdf.py upload/sample.pdf
    python tools/analyze_pdf.py upload/*.pdf
"""
import sys
import os
import glob
from pathlib import Path

_BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

import pdfplumber
from parsers.common.cancellation import CancellationDetector


def _is_reddish(color) -> bool:
    """붉은색 계열 판별"""
    if not color:
        return False
    if isinstance(color, (list, tuple)):
        if len(color) >= 3:
            r, g, b = color[0], color[1], color[2]
            if isinstance(r, (int, float)):
                if r > 0.5 and g < 0.3 and b < 0.3:
                    return True
                if r > 128 and g < 80 and b < 80:
                    return True
        elif len(color) == 4:
            c, m, y, k = color
            if m > 0.5 and y > 0.3 and c < 0.2:
                return True
    return False


def analyze_pdf(path: str):
    print(f"\n{'='*80}")
    print(f"PDF: {path}")
    print(f"{'='*80}")

    with pdfplumber.open(path) as pdf:
        print(f"총 페이지: {len(pdf.pages)}")

        for i, page in enumerate(pdf.pages):
            print(f"\n--- 페이지 {i+1} (w={page.width:.0f}, h={page.height:.0f}) ---")

            text = page.extract_text() or ""
            print(f"\n[텍스트 ({len(text)}자)]")
            for line in text.split('\n')[:30]:
                print(f"  {line}")
            if len(text.split('\n')) > 30:
                print(f"  ... ({len(text.split(chr(10)))}줄 더)")

            tables = page.extract_tables()
            print(f"\n[테이블] {len(tables)}개")
            for ti, table in enumerate(tables):
                print(f"  테이블 {ti}: {len(table)}행")
                for ri, row in enumerate(table[:3]):
                    cells = [str(c)[:40] if c else "None" for c in row]
                    print(f"    행{ri}: {cells}")
                if len(table) > 3:
                    print(f"    ... ({len(table)-3}행 더)")

            lines = page.lines or []
            red_lines = [ln for ln in lines if _is_reddish(ln.get('stroking_color'))]
            print(f"\n[Lines] {len(lines)}개 (붉은색: {len(red_lines)}개)")
            for rl in red_lines[:10]:
                print(f"    color={rl.get('stroking_color')} "
                      f"x0={rl['x0']:.1f} y0={rl['top']:.1f} "
                      f"x1={rl['x1']:.1f} y1={rl['bottom']:.1f}")

            rects = page.rects or []
            red_rects = [r for r in rects if _is_reddish(r.get('stroking_color'))]
            print(f"\n[Rects] {len(rects)}개 (붉은색: {len(red_rects)}개)")

            chars = page.chars or []
            color_groups = {}
            for ch in chars:
                key = f"stroke={ch.get('stroking_color', '')} fill={ch.get('non_stroking_color', '')}"
                if key not in color_groups:
                    color_groups[key] = {'count': 0, 'sample': ''}
                color_groups[key]['count'] += 1
                if len(color_groups[key]['sample']) < 30:
                    color_groups[key]['sample'] += ch.get('text', '')

            print(f"\n[Chars] {len(chars)}개")
            for key, info in sorted(color_groups.items(), key=lambda x: -x[1]['count']):
                print(f"    {key}: {info['count']}자 | 예: '{info['sample'][:30]}'")

            red_chars = [ch for ch in chars
                        if _is_reddish(ch.get('non_stroking_color'))
                        or _is_reddish(ch.get('stroking_color'))]
            if red_chars:
                red_text = ''.join(ch.get('text', '') for ch in red_chars)
                print(f"\n  [붉은색 텍스트] {len(red_chars)}자: '{red_text[:200]}'")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        files = []
        for arg in sys.argv[1:]:
            files.extend(glob.glob(arg) or [arg])
    else:
        files = glob.glob(os.path.join(_BACKEND_ROOT, 'upload', '*.pdf'))

    if not files:
        print("PDF 파일 없음")
        sys.exit(1)
    for p in files:
        analyze_pdf(p)
