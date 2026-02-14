"""샘플 PDF 구조 분석 스크립트 — pdfplumber의 lines/chars/rects 활용"""
import sys
import json
import pdfplumber

def analyze_pdf(path: str):
    print(f"\n{'='*80}")
    print(f"PDF: {path}")
    print(f"{'='*80}")

    with pdfplumber.open(path) as pdf:
        print(f"총 페이지: {len(pdf.pages)}")

        for i, page in enumerate(pdf.pages):
            print(f"\n--- 페이지 {i+1} (w={page.width:.0f}, h={page.height:.0f}) ---")

            # 텍스트
            text = page.extract_text() or ""
            print(f"\n[텍스트 ({len(text)}자)]")
            # 처음 500자만
            for line in text.split('\n')[:30]:
                print(f"  {line}")
            if len(text.split('\n')) > 30:
                print(f"  ... ({len(text.split(chr(10)))}줄 더)")

            # 테이블
            tables = page.extract_tables()
            print(f"\n[테이블] {len(tables)}개")
            for ti, table in enumerate(tables):
                print(f"  테이블 {ti}: {len(table)}행")
                for ri, row in enumerate(table[:3]):
                    cells = [str(c)[:40] if c else "None" for c in row]
                    print(f"    행{ri}: {cells}")
                if len(table) > 3:
                    print(f"    ... ({len(table)-3}행 더)")

            # Lines (취소선/대각선 감지용)
            lines = page.lines or []
            print(f"\n[Lines] {len(lines)}개")
            red_lines = []
            for ln in lines:
                color = ln.get('stroking_color')
                if color and _is_reddish(color):
                    red_lines.append(ln)
            print(f"  붉은색 라인: {len(red_lines)}개")
            for rl in red_lines[:10]:
                print(f"    color={rl.get('stroking_color')} "
                      f"x0={rl['x0']:.1f} y0={rl['top']:.1f} "
                      f"x1={rl['x1']:.1f} y1={rl['bottom']:.1f} "
                      f"width={rl.get('linewidth',0)}")

            # Rects
            rects = page.rects or []
            print(f"\n[Rects] {len(rects)}개")
            red_rects = [r for r in rects if _is_reddish(r.get('stroking_color'))]
            print(f"  붉은색 사각형: {len(red_rects)}개")
            for rr in red_rects[:5]:
                print(f"    color={rr.get('stroking_color')} "
                      f"x0={rr['x0']:.1f} y0={rr['top']:.1f} "
                      f"x1={rr['x1']:.1f} y1={rr['bottom']:.1f}")

            # Chars 색상 분석
            chars = page.chars or []
            print(f"\n[Chars] {len(chars)}개")
            color_groups = {}
            for ch in chars:
                sc = str(ch.get('stroking_color', ''))
                nsc = str(ch.get('non_stroking_color', ''))
                key = f"stroke={sc} fill={nsc}"
                if key not in color_groups:
                    color_groups[key] = {'count': 0, 'sample': ''}
                color_groups[key]['count'] += 1
                if len(color_groups[key]['sample']) < 30:
                    color_groups[key]['sample'] += ch.get('text', '')

            print("  색상별 문자 분포:")
            for key, info in sorted(color_groups.items(), key=lambda x: -x[1]['count']):
                print(f"    {key}: {info['count']}자 | 예: '{info['sample'][:30]}'")

            # 붉은 글자만 추출
            red_chars = [ch for ch in chars
                        if _is_reddish(ch.get('non_stroking_color'))
                        or _is_reddish(ch.get('stroking_color'))]
            if red_chars:
                red_text = ''.join(ch.get('text', '') for ch in red_chars)
                print(f"\n  [붉은색 텍스트] {len(red_chars)}자: '{red_text[:200]}'")

            # Annotations
            annots = page.annots or []
            print(f"\n[Annotations] {len(annots)}개")
            for a in annots[:5]:
                print(f"    {a}")

            # 페이지 헤더/푸터 패턴 분석
            lines_text = text.split('\n')
            if lines_text:
                print(f"\n[첫줄] '{lines_text[0]}'")
                print(f"[끝줄] '{lines_text[-1]}'")


def _is_reddish(color) -> bool:
    """붉은색 계열인지 판별"""
    if not color:
        return False
    if isinstance(color, (list, tuple)):
        if len(color) >= 3:
            r, g, b = color[0], color[1], color[2]
            # RGB: R이 높고 G,B가 낮은 경우
            if isinstance(r, (int, float)):
                if r > 0.5 and g < 0.3 and b < 0.3:
                    return True
                # 정수형 (0-255)
                if r > 128 and g < 80 and b < 80:
                    return True
        elif len(color) == 4:
            # CMYK
            c, m, y, k = color
            if m > 0.5 and y > 0.3 and c < 0.2:
                return True
        elif len(color) == 1:
            pass  # grayscale
    return False


if __name__ == '__main__':
    import glob
    pdfs = glob.glob('c:/work/pdf-service/upload/*.pdf')
    if not pdfs:
        print("PDF 파일 없음")
        sys.exit(1)
    for p in pdfs:
        analyze_pdf(p)
