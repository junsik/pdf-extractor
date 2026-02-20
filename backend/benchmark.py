"""
등기부등본 PDF 파서 벤치마크

파서 버전별 정확도를 LLM 벤치마크처럼 수치화하여 측정한다.
PDF에서 추출 가능한 모든 텍스트 대비 파서가 구조화한 비율 = 점수.

인터페이스 계약 (pdf_parser.py가 반드시 제공해야 하는 것):
  - parse_registry_pdf(pdf_buffer: bytes) -> Dict[str, Any]
  - PARSER_VERSION: str

Usage:
  python benchmark.py                        # upload/ 폴더 전체
  python benchmark.py path/to/specific.pdf   # 특정 파일
  python benchmark.py --verbose              # 누락 토큰 상세 출력
  python benchmark.py --json                 # JSON 형식 출력
"""
import os
import sys
import re
import io
import json
import glob
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any

# 스크립트 위치로 이동 (admin.py 패턴)
os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

import pdfplumber

# ==================== 인터페이스 계약 ====================
# 모든 파서 모듈은 아래 2개를 export해야 한다:
#   - PARSER_VERSION: str
#   - parse_registry_pdf(pdf_buffer: bytes) -> Dict[str, Any]
#
# parsers/ 패키지를 통해 버전별 파서를 로드한다.
from parsers import load_parser, list_parsers


# ==================== 설정 ====================

DEFAULT_UPLOAD_DIR = "../upload"
BENCHMARK_JSON = "../benchmark-history.json"
BENCHMARK_MD = "../BENCHMARK.md"
MAX_HISTORY = 5  # 리포트에 표시할 최근 버전 수

# ground truth에서 제외할 구조 노이즈 토큰 (컬럼 헤더, 섹션 제목)
NOISE_TOKENS = {
    "표시번호", "접수", "소재지번", "건물내역", "등기원인", "기타사항",
    "순위번호", "등기목적", "권리자", "표제부", "갑구", "을구",
    "토지의", "건물의", "표시", "소유권에", "관한", "사항",
    "소유권", "이외의", "권리에", "접수일자", "접수번호",
    "도로명주소", "등기명의인",
}

# 파서 출력에서 제외할 메타데이터 키
EXCLUDED_KEYS = {
    "raw_text", "parser_version", "parse_date", "errors",
    "section_a_count", "section_b_count",
    "active_section_a_count", "active_section_b_count",
    "is_cancelled", "property_type",
}

# 워터마크 패턴
_WATERMARK_RE = re.compile(r"열\s*람\s*용")

# 헤더/푸터 패턴 (pdf_parser.py와 동일)
_HEADER_RE = re.compile(
    r"^\[(?:토지|건물|집합건물)\]\s*.+$|"
    r"^표시번호\s+접\s*수|"
    r"^순위번호\s+등\s*기\s*목\s*적"
)
_FOOTER_RE = re.compile(
    r"열람일시\s*:|발행일시\s*:|^\d+/\d+$"
)

# 섹션 경계 감지 패턴 (pdf_parser.py와 동일)
_SECTION_PATTERNS = {
    "title_land": re.compile(r"표\s*제\s*부.*토지의\s*표시"),
    "title_building": re.compile(r"표\s*제\s*부.*건물의\s*표시"),
    "title_exclusive": re.compile(r"표\s*제\s*부.*전유부분"),
    "land_right": re.compile(r"대지권의\s*(?:목적인\s*토지의\s*표시|표시)"),
    "section_a": re.compile(r"갑\s*구.*소유권에\s*관한\s*사항"),
    "section_b": re.compile(r"을\s*구.*소유권\s*이외의\s*권리"),
    "_skip_collateral": re.compile(r"공\s*동\s*담\s*보\s*목\s*록"),
    "_skip_sale": re.compile(r"매\s*각\s*물\s*건\s*목\s*록"),
    "_skip_summary": re.compile(r"주\s*요\s*등\s*기\s*사\s*항\s*요\s*약"),
    "_skip_owner_summary": re.compile(r"등\s*기\s*명\s*의\s*인.*등\s*록\s*번\s*호"),
}


# ==================== 데이터 클래스 ====================

@dataclass
class GroundTruth:
    full_text: str = ""
    title_text: str = ""
    section_a_text: str = ""
    section_b_text: str = ""


@dataclass
class PDFScore:
    filename: str = ""
    property_type: str = ""
    overall: float = 0.0
    title: Optional[float] = None
    section_a: Optional[float] = None
    section_b: Optional[float] = None
    gt_tokens: int = 0
    parser_tokens: int = 0
    missing_top20: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class BenchmarkReport:
    parser_version: str = ""
    date: str = ""
    file_count: int = 0
    scores: List[PDFScore] = field(default_factory=list)
    average: float = 0.0
    title_avg: Optional[float] = None
    section_a_avg: Optional[float] = None
    section_b_avg: Optional[float] = None


# ==================== Ground Truth 추출 ====================

def _is_watermark_char(obj: dict) -> bool:
    """워터마크 문자 판별 (회색 색상 기반)"""
    if obj.get("object_type") != "char":
        return False
    color = obj.get("non_stroking_color")
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        return all(0.5 < c < 1.0 for c in color[:3])
    return False


def _clean_line(line: str) -> str:
    """라인 정리: 워터마크 텍스트 제거"""
    return _WATERMARK_RE.sub("", line).strip()


def _detect_section(line: str) -> Optional[str]:
    """라인에서 섹션 경계 감지"""
    clean = re.sub(r"\s+", " ", line).strip()
    for key, pattern in _SECTION_PATTERNS.items():
        if pattern.search(clean):
            if key.startswith("_skip"):
                return "skip"
            if key.startswith("title") or key.startswith("land_right"):
                return "title"
            return key
    return None


def extract_ground_truth(pdf_path: str) -> GroundTruth:
    """PDF에서 ground truth 텍스트 추출 (워터마크/헤더/푸터/스킵 섹션 제외)"""
    sections = {"title": [], "section_a": [], "section_b": []}
    current = "title"

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # 워터마크 제거
            clean_page = page.filter(lambda obj: not _is_watermark_char(obj))
            text = clean_page.extract_text() or ""

            for line in text.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue

                # 헤더/푸터 제거
                if _HEADER_RE.match(stripped) or _FOOTER_RE.search(stripped):
                    continue

                cleaned = _clean_line(stripped)
                if not cleaned:
                    continue

                # 섹션 경계 감지
                detected = _detect_section(cleaned)
                if detected:
                    if detected == "skip":
                        current = "skip"
                        continue
                    current = detected

                if current != "skip" and current in sections:
                    sections[current].append(cleaned)

    return GroundTruth(
        full_text="\n".join(
            sections["title"] + sections["section_a"] + sections["section_b"]
        ),
        title_text="\n".join(sections["title"]),
        section_a_text="\n".join(sections["section_a"]),
        section_b_text="\n".join(sections["section_b"]),
    )


# ==================== 파서 출력 텍스트 수집 ====================

def _numeric_tokens(value) -> List[str]:
    """숫자를 매칭 가능한 토큰으로 변환"""
    if isinstance(value, bool) or value is None or value == 0:
        return []
    if isinstance(value, float):
        tokens = [str(value)]
        if value == int(value):
            tokens.append(str(int(value)))
        return tokens
    if isinstance(value, int):
        s = str(value)
        tokens = [s]
        if value >= 1000:
            tokens.append(f"{value:,}")
        return tokens
    return []


def _collect_strings(obj: Any, excluded: set) -> List[str]:
    """딕셔너리/리스트에서 모든 문자열 값을 재귀 수집"""
    strings = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in excluded:
                continue
            if isinstance(v, str) and v:
                strings.append(v)
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                strings.extend(_numeric_tokens(v))
            elif isinstance(v, (dict, list)):
                strings.extend(_collect_strings(v, excluded))
    elif isinstance(obj, list):
        for item in obj:
            strings.extend(_collect_strings(item, excluded))
    return strings


def collect_parser_text(result: Dict[str, Any]) -> Dict[str, str]:
    """파서 결과에서 섹션별 텍스트 수집 (raw_text 제외)"""
    title_text = " ".join(_collect_strings(result.get("title_info", {}), EXCLUDED_KEYS))

    section_a_entries = result.get("section_a", [])
    section_a_text = " ".join(_collect_strings(section_a_entries, EXCLUDED_KEYS))

    section_b_entries = result.get("section_b", [])
    section_b_text = " ".join(_collect_strings(section_b_entries, EXCLUDED_KEYS))

    # 최상위 필드 (unique_number, property_address)
    top_fields = []
    for k in ("unique_number", "property_address"):
        v = result.get(k)
        if isinstance(v, str) and v:
            top_fields.append(v)

    full = " ".join(top_fields) + " " + title_text + " " + section_a_text + " " + section_b_text

    return {
        "full": full,
        "title": " ".join(top_fields) + " " + title_text,
        "section_a": section_a_text,
        "section_b": section_b_text,
    }


# ==================== 토큰화 + 스코어 ====================

def tokenize(text: str) -> Counter:
    """텍스트를 토큰 Counter로 변환"""
    if not text:
        return Counter()
    tokens = re.findall(r"[\w가-힣]+", text)
    # 2글자 미만 필터링 + 노이즈 토큰 제거
    filtered = [t for t in tokens if len(t) >= 2 and t not in NOISE_TOKENS]
    return Counter(filtered)


def compute_recall(gt: Counter, parser: Counter) -> Optional[float]:
    """토큰 리콜 계산. gt가 비어있으면 None 반환."""
    total = sum(gt.values())
    if total == 0:
        return None
    matched = sum(min(gt[t], parser.get(t, 0)) for t in gt)
    return round((matched / total) * 100, 1)


def find_missing(gt: Counter, parser: Counter, top_n: int = 20) -> List[str]:
    """gt에는 있지만 parser에 없거나 부족한 토큰 (빈도 내림차순)"""
    missing = Counter()
    for token, count in gt.items():
        diff = count - parser.get(token, 0)
        if diff > 0:
            missing[token] = diff
    return [t for t, _ in missing.most_common(top_n)]


# ==================== 단일 PDF 벤치마크 ====================

def benchmark_single(pdf_path: str, parser=None) -> PDFScore:
    """단일 PDF에 대해 벤치마크 실행"""
    if parser is None:
        parser = load_parser("latest")

    filename = os.path.basename(pdf_path)
    score = PDFScore(filename=filename)

    try:
        # 1. Ground truth 추출
        gt = extract_ground_truth(pdf_path)

        # 2. 파서 실행
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        result = parser.parse_registry_pdf(pdf_bytes)

        score.property_type = result.get("property_type", "unknown")
        score.errors = result.get("errors", [])

        # 3. 파서 출력 텍스트 수집
        parser_text = collect_parser_text(result)

        # 4. 토큰화
        gt_full = tokenize(gt.full_text)
        gt_title = tokenize(gt.title_text)
        gt_a = tokenize(gt.section_a_text)
        gt_b = tokenize(gt.section_b_text)

        p_full = tokenize(parser_text["full"])
        p_title = tokenize(parser_text["title"])
        p_a = tokenize(parser_text["section_a"])
        p_b = tokenize(parser_text["section_b"])

        # 5. 스코어
        score.overall = compute_recall(gt_full, p_full) or 0.0
        score.title = compute_recall(gt_title, p_title)
        score.section_a = compute_recall(gt_a, p_a)
        score.section_b = compute_recall(gt_b, p_b)
        score.gt_tokens = sum(gt_full.values())
        score.parser_tokens = sum(
            min(gt_full[t], p_full.get(t, 0)) for t in gt_full
        )
        score.missing_top20 = find_missing(gt_full, p_full)

    except Exception as e:
        score.errors.append(f"벤치마크 실패: {e}")

    return score


# ==================== 전체 벤치마크 ====================

def run_benchmark(pdf_paths: List[str], parser=None) -> BenchmarkReport:
    """전체 PDF에 대해 벤치마크 실행"""
    if parser is None:
        parser = load_parser("latest")

    report = BenchmarkReport(
        parser_version=parser.PARSER_VERSION,
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        file_count=len(pdf_paths),
    )

    for path in sorted(pdf_paths):
        score = benchmark_single(path, parser=parser)
        report.scores.append(score)

    # 평균 계산
    if report.scores:
        valid = [s for s in report.scores if s.gt_tokens > 0]
        if valid:
            report.average = round(sum(s.overall for s in valid) / len(valid), 1)

        title_scores = [s.title for s in report.scores if s.title is not None]
        if title_scores:
            report.title_avg = round(sum(title_scores) / len(title_scores), 1)

        a_scores = [s.section_a for s in report.scores if s.section_a is not None]
        if a_scores:
            report.section_a_avg = round(sum(a_scores) / len(a_scores), 1)

        b_scores = [s.section_b for s in report.scores if s.section_b is not None]
        if b_scores:
            report.section_b_avg = round(sum(b_scores) / len(b_scores), 1)

    return report


# ==================== 출력 ====================

def _score_str(val: Optional[float]) -> str:
    return f"{val:.1f}" if val is not None else "N/A"


def print_report(report: BenchmarkReport, verbose: bool = False):
    """LLM 벤치마크 스타일 리포트 출력"""
    w = 60
    print(f"\n{'=' * w}")
    print(f"  PDF Parser Benchmark v{report.parser_version}")
    print(f"  {report.date} | Files: {report.file_count}")
    print(f"{'=' * w}")

    for i, s in enumerate(report.scores, 1):
        status = "" if not s.errors else " [!]"
        print(f"\n [{i:2d}] {s.filename}{status}")
        print(f"      Type: {s.property_type} | "
              f"Tokens: {s.parser_tokens}/{s.gt_tokens} | "
              f"Score: {s.overall:.1f}/100")
        print(f"      "
              f"표제부: {_score_str(s.title)} | "
              f"갑구: {_score_str(s.section_a)} | "
              f"을구: {_score_str(s.section_b)}")

        if verbose and s.missing_top20:
            missing_str = ", ".join(s.missing_top20[:10])
            print(f"      Missing: {missing_str}")

        if s.errors:
            for err in s.errors:
                print(f"      Error: {err}")

    print(f"\n{'=' * w}")
    print(f"  OVERALL: {report.average:.1f}/100")
    print(f"  표제부: {_score_str(report.title_avg)} | "
          f"갑구: {_score_str(report.section_a_avg)} | "
          f"을구: {_score_str(report.section_b_avg)}")
    print(f"{'=' * w}\n")


def print_json(report: BenchmarkReport):
    """JSON 형식 출력"""
    data = asdict(report)
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ==================== JSON 히스토리 ====================

def save_to_json(report: BenchmarkReport, path: str = BENCHMARK_JSON):
    """벤치마크 결과를 JSON 히스토리에 추가"""
    history = load_history(path)

    entry = {
        "version": report.parser_version,
        "date": report.date,
        "files": report.file_count,
        "overall": report.average,
        "title": report.title_avg,
        "section_a": report.section_a_avg,
        "section_b": report.section_b_avg,
        "details": [
            {
                "file": s.filename,
                "type": s.property_type,
                "score": s.overall,
                "title": s.title,
                "section_a": s.section_a,
                "section_b": s.section_b,
                "gt_tokens": s.gt_tokens,
                "parser_tokens": s.parser_tokens,
            }
            for s in report.scores
        ],
    }

    # 같은 버전이 이미 있으면 교체
    history = [h for h in history if h["version"] != entry["version"]]
    history.append(entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"  Saved to {path} (v{report.parser_version})")


def load_history(path: str = BENCHMARK_JSON) -> List[Dict]:
    """JSON 히스토리 로드"""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==================== Markdown 리포트 생성 ====================

def generate_report_md(path: str = BENCHMARK_JSON, out: str = BENCHMARK_MD):
    """JSON 히스토리에서 최근 5개 버전 비교 Markdown 리포트 생성"""
    history = load_history(path)
    if not history:
        print("히스토리 없음. 먼저 --save로 벤치마크를 실행하세요.", file=sys.stderr)
        sys.exit(1)

    recent = history[-MAX_HISTORY:]
    latest = recent[-1]

    lines = []
    lines.append("# PDF Parser Benchmark Report")
    lines.append("")
    lines.append(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # ── 최신 요약 ──
    lines.append("## Latest")
    lines.append("")
    lines.append(f"- **Version**: v{latest['version']}")
    lines.append(f"- **Date**: {latest['date']}")
    lines.append(f"- **Overall**: **{latest['overall']}**/100")
    lines.append(f"- 표제부: {_score_str(latest.get('title'))} | "
                 f"갑구: {_score_str(latest.get('section_a'))} | "
                 f"을구: {_score_str(latest.get('section_b'))}")
    lines.append("")

    # ── Mermaid 바 차트: 버전별 Overall ──
    if len(recent) >= 2:
        lines.append("## Version History")
        lines.append("")
        lines.append("```mermaid")
        lines.append("xychart-beta")
        lines.append('  title "Overall Score by Version"')
        lines.append("  x-axis [{}]".format(
            ", ".join(f'"v{h["version"]}"' for h in recent)
        ))
        lines.append('  y-axis "Score" 0 --> 100')
        lines.append("  bar [{}]".format(
            ", ".join(str(h["overall"]) for h in recent)
        ))
        lines.append("```")
        lines.append("")

    # ── Mermaid 라인 차트: 섹션별 추이 ──
    if len(recent) >= 2:
        lines.append("### Section Breakdown")
        lines.append("")
        lines.append("```mermaid")
        lines.append("xychart-beta")
        lines.append('  title "Score by Section"')
        lines.append("  x-axis [{}]".format(
            ", ".join(f'"v{h["version"]}"' for h in recent)
        ))
        lines.append('  y-axis "Score" 0 --> 100')
        lines.append('  line "표제부" [{}]'.format(
            ", ".join(str(h.get("title") or 0) for h in recent)
        ))
        lines.append('  line "갑구" [{}]'.format(
            ", ".join(str(h.get("section_a") or 0) for h in recent)
        ))
        lines.append('  line "을구" [{}]'.format(
            ", ".join(str(h.get("section_b") or 0) for h in recent)
        ))
        lines.append("```")
        lines.append("")

    # ── 히스토리 테이블 ──
    lines.append("## Score Table")
    lines.append("")
    lines.append("| Version | Date | Overall | 표제부 | 갑구 | 을구 | Files |")
    lines.append("|---------|------|---------|--------|------|------|-------|")
    for h in reversed(recent):
        lines.append(
            f"| v{h['version']} | {h['date']} | "
            f"**{h['overall']}** | "
            f"{_score_str(h.get('title'))} | "
            f"{_score_str(h.get('section_a'))} | "
            f"{_score_str(h.get('section_b'))} | "
            f"{h['files']} |"
        )
    lines.append("")

    # ── 최신 버전 파일별 상세 ──
    lines.append("## File Details (Latest)")
    lines.append("")
    lines.append("| File | Type | Score | 표제부 | 갑구 | 을구 | Tokens |")
    lines.append("|------|------|-------|--------|------|------|--------|")
    for d in latest.get("details", []):
        lines.append(
            f"| {d['file']} | {d['type']} | "
            f"**{d['score']}** | "
            f"{_score_str(d.get('title'))} | "
            f"{_score_str(d.get('section_a'))} | "
            f"{_score_str(d.get('section_b'))} | "
            f"{d.get('parser_tokens', 0)}/{d.get('gt_tokens', 0)} |"
        )
    lines.append("")

    content = "\n".join(lines)
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  Report: {out}")


# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(
        description="등기부등본 PDF 파서 벤치마크"
    )
    parser.add_argument(
        "pdf_path", nargs="?",
        help="특정 PDF 파일 경로 (미지정 시 upload/ 전체)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="누락 토큰 상세 출력"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="JSON 형식 출력"
    )
    parser.add_argument(
        "--save", "-s", action="store_true",
        help="결과를 JSON 히스토리에 저장"
    )
    parser.add_argument(
        "--report", "-r", action="store_true",
        help="JSON 히스토리에서 Markdown 리포트 생성 (벤치마크 실행 안 함)"
    )
    parser.add_argument(
        "--parser", "-p", default="latest",
        help="파서 버전 (기본: latest, 예: v2.1.0)"
    )
    parser.add_argument(
        "--all-parsers", action="store_true",
        help="모든 파서 버전을 순차 실행하여 비교"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="사용 가능한 파서 버전 목록 출력"
    )
    parser.add_argument(
        "--upload-dir", default=DEFAULT_UPLOAD_DIR,
        help=f"PDF 디렉토리 (기본: {DEFAULT_UPLOAD_DIR})"
    )
    args = parser.parse_args()

    # --list: 파서 목록 출력
    if args.list:
        print("사용 가능한 파서:")
        for v in list_parsers():
            p = load_parser(v)
            tag = " (current)" if v == "latest" else ""
            print(f"  {v} → v{p.PARSER_VERSION}{tag}")
        return

    # --report: 리포트만 생성하고 종료
    if args.report:
        generate_report_md()
        return

    # PDF 경로 수집
    if args.pdf_path:
        if not os.path.exists(args.pdf_path):
            print(f"파일 없음: {args.pdf_path}", file=sys.stderr)
            sys.exit(1)
        pdf_paths = [args.pdf_path]
    else:
        pdf_paths = glob.glob(os.path.join(args.upload_dir, "*.pdf"))
        if not pdf_paths:
            print(f"PDF 파일 없음: {args.upload_dir}", file=sys.stderr)
            sys.exit(1)

    # --all-parsers: 모든 버전 순차 실행
    if args.all_parsers:
        versions = list_parsers()
        for ver in versions:
            p = load_parser(ver)
            report = run_benchmark(pdf_paths, parser=p)
            print_report(report, verbose=args.verbose)
            if args.save:
                save_to_json(report)
        if args.save:
            generate_report_md()
        return

    # 단일 파서 실행
    p = load_parser(args.parser)
    report = run_benchmark(pdf_paths, parser=p)

    # 출력
    if args.json:
        print_json(report)
    else:
        print_report(report, verbose=args.verbose)

    # 저장
    if args.save:
        save_to_json(report)
        generate_report_md()


if __name__ == "__main__":
    main()
