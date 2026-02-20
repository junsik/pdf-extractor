"""
PDF 파서 벤치마크

파서 버전별 정확도를 LLM 벤치마크처럼 수치화하여 측정한다.
PDF에서 추출 가능한 모든 텍스트 대비 파서가 구조화한 비율 = 점수.

Usage:
  python tools/benchmark.py                                # upload/ 폴더 전체
  python tools/benchmark.py path/to/specific.pdf           # 특정 파일
  python tools/benchmark.py --verbose                      # 누락 토큰 상세 출력
  python tools/benchmark.py --json                         # JSON 형식 출력
  python tools/benchmark.py --type registry --parser v1.0.0 # 특정 파서
  python tools/benchmark.py --list                         # 파서 목록
  python tools/benchmark.py --all-parsers                  # 전 버전 비교
"""
import os
import sys
import re
import json
import glob
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any

# 백엔드 루트를 sys.path에 추가 (tools/ 에서 실행)
_BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)
os.chdir(_BACKEND_ROOT)

import pdfplumber

from parsers import get_parser, list_document_types, list_versions
from parsers.base import BaseParser
from parsers.common.pdf_utils import is_watermark_char, WATERMARK_RE


# ==================== 설정 ====================

DEFAULT_UPLOAD_DIR = "upload"
BENCHMARK_JSON = "benchmark-history.json"
BENCHMARK_MD = "BENCHMARK.md"
MAX_HISTORY = 5

# ground truth에서 제외할 구조 노이즈 토큰
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

# 헤더/푸터 패턴
_HEADER_RE = re.compile(
    r"^\[(?:토지|건물|집합건물)\]\s*.+$|"
    r"^표시번호\s+접\s*수|"
    r"^순위번호\s+등\s*기\s*목\s*적"
)
_FOOTER_RE = re.compile(
    r"열람일시\s*:|발행일시\s*:|^\d+/\d+$"
)

# 섹션 경계 감지 패턴
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
    document_type: str = ""
    parser_version: str = ""
    date: str = ""
    file_count: int = 0
    scores: List[PDFScore] = field(default_factory=list)
    average: float = 0.0
    title_avg: Optional[float] = None
    section_a_avg: Optional[float] = None
    section_b_avg: Optional[float] = None


# ==================== Ground Truth 추출 ====================

def _clean_line(line: str) -> str:
    return WATERMARK_RE.sub("", line).strip()


def _detect_section(line: str) -> Optional[str]:
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
    """PDF에서 ground truth 텍스트 추출"""
    sections = {"title": [], "section_a": [], "section_b": []}
    current = "title"

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            clean_page = page.filter(lambda obj: not is_watermark_char(obj))
            text = clean_page.extract_text() or ""

            for line in text.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue
                if _HEADER_RE.match(stripped) or _FOOTER_RE.search(stripped):
                    continue

                cleaned = _clean_line(stripped)
                if not cleaned:
                    continue

                detected = _detect_section(cleaned)
                if detected:
                    if detected == "skip":
                        current = "skip"
                        continue
                    current = detected

                if current != "skip" and current in sections:
                    sections[current].append(cleaned)

    return GroundTruth(
        full_text="\n".join(sections["title"] + sections["section_a"] + sections["section_b"]),
        title_text="\n".join(sections["title"]),
        section_a_text="\n".join(sections["section_a"]),
        section_b_text="\n".join(sections["section_b"]),
    )


# ==================== 파서 출력 텍스트 수집 ====================

def _numeric_tokens(value) -> List[str]:
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
    """파서 결과에서 섹션별 텍스트 수집"""
    title_text = " ".join(_collect_strings(result.get("title_info", {}), EXCLUDED_KEYS))
    section_a_text = " ".join(_collect_strings(result.get("section_a", []), EXCLUDED_KEYS))
    section_b_text = " ".join(_collect_strings(result.get("section_b", []), EXCLUDED_KEYS))

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
    if not text:
        return Counter()
    tokens = re.findall(r"[\w가-힣]+", text)
    return Counter(t for t in tokens if len(t) >= 2 and t not in NOISE_TOKENS)


def compute_recall(gt: Counter, parser: Counter) -> Optional[float]:
    total = sum(gt.values())
    if total == 0:
        return None
    matched = sum(min(gt[t], parser.get(t, 0)) for t in gt)
    return round((matched / total) * 100, 1)


def find_missing(gt: Counter, parser: Counter, top_n: int = 20) -> List[str]:
    missing = Counter()
    for token, count in gt.items():
        diff = count - parser.get(token, 0)
        if diff > 0:
            missing[token] = diff
    return [t for t, _ in missing.most_common(top_n)]


# ==================== 벤치마크 실행 ====================

def benchmark_single(pdf_path: str, parser: BaseParser) -> PDFScore:
    """단일 PDF 벤치마크"""
    filename = os.path.basename(pdf_path)
    score = PDFScore(filename=filename)

    try:
        gt = extract_ground_truth(pdf_path)

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # 새 파서 인터페이스: parser.parse() → ParseResult
        parse_result = parser.parse(pdf_bytes)
        result = parse_result.data

        score.property_type = result.get("property_type", parse_result.document_sub_type or "unknown")
        score.errors = result.get("errors", []) + parse_result.errors

        parser_text = collect_parser_text(result)

        gt_full = tokenize(gt.full_text)
        gt_title = tokenize(gt.title_text)
        gt_a = tokenize(gt.section_a_text)
        gt_b = tokenize(gt.section_b_text)

        p_full = tokenize(parser_text["full"])
        p_title = tokenize(parser_text["title"])
        p_a = tokenize(parser_text["section_a"])
        p_b = tokenize(parser_text["section_b"])

        score.overall = compute_recall(gt_full, p_full) or 0.0
        score.title = compute_recall(gt_title, p_title)
        score.section_a = compute_recall(gt_a, p_a)
        score.section_b = compute_recall(gt_b, p_b)
        score.gt_tokens = sum(gt_full.values())
        score.parser_tokens = sum(min(gt_full[t], p_full.get(t, 0)) for t in gt_full)
        score.missing_top20 = find_missing(gt_full, p_full)

    except Exception as e:
        score.errors.append(f"벤치마크 실패: {e}")

    return score


def run_benchmark(pdf_paths: List[str], parser: BaseParser,
                  document_type: str = "registry") -> BenchmarkReport:
    """전체 벤치마크 실행"""
    report = BenchmarkReport(
        document_type=document_type,
        parser_version=parser.parser_version(),
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        file_count=len(pdf_paths),
    )

    for path in sorted(pdf_paths):
        score = benchmark_single(path, parser)
        report.scores.append(score)

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
    w = 60
    print(f"\n{'=' * w}")
    print(f"  PDF Parser Benchmark — {report.document_type} v{report.parser_version}")
    print(f"  {report.date} | Files: {report.file_count}")
    print(f"{'=' * w}")

    for i, s in enumerate(report.scores, 1):
        status = "" if not s.errors else " [!]"
        print(f"\n [{i:2d}] {s.filename}{status}")
        print(f"      Type: {s.property_type} | "
              f"Tokens: {s.parser_tokens}/{s.gt_tokens} | "
              f"Score: {s.overall:.1f}/100")
        print(f"      표제부: {_score_str(s.title)} | "
              f"갑구: {_score_str(s.section_a)} | "
              f"을구: {_score_str(s.section_b)}")

        if verbose and s.missing_top20:
            print(f"      Missing: {', '.join(s.missing_top20[:10])}")
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
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))


# ==================== JSON 히스토리 ====================

def save_to_json(report: BenchmarkReport, path: str = BENCHMARK_JSON):
    history = load_history(path)
    key = f"{report.document_type}:{report.parser_version}"

    entry = {
        "document_type": report.document_type,
        "version": report.parser_version,
        "date": report.date,
        "files": report.file_count,
        "overall": report.average,
        "title": report.title_avg,
        "section_a": report.section_a_avg,
        "section_b": report.section_b_avg,
        "details": [
            {"file": s.filename, "type": s.property_type, "score": s.overall,
             "title": s.title, "section_a": s.section_a, "section_b": s.section_b,
             "gt_tokens": s.gt_tokens, "parser_tokens": s.parser_tokens}
            for s in report.scores
        ],
    }

    history = [h for h in history
               if f"{h.get('document_type', 'registry')}:{h['version']}" != key]
    history.append(entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  Saved to {path} ({report.document_type} v{report.parser_version})")


def load_history(path: str = BENCHMARK_JSON) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==================== Markdown 리포트 ====================

def generate_report_md(doc_type: str = "registry",
                       path: str = BENCHMARK_JSON, out: str = BENCHMARK_MD):
    history = [h for h in load_history(path)
               if h.get("document_type", "registry") == doc_type]
    if not history:
        print("히스토리 없음. 먼저 --save로 벤치마크를 실행하세요.", file=sys.stderr)
        return

    recent = history[-MAX_HISTORY:]
    latest = recent[-1]
    doc_info = next((t for t in list_document_types() if t.type_id == doc_type), None)
    doc_name = doc_info.display_name if doc_info else doc_type

    lines = [
        f"# PDF Parser Benchmark Report — {doc_name}",
        "",
        f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Latest",
        "",
        f"- **Document Type**: {doc_name} (`{doc_type}`)",
        f"- **Version**: v{latest['version']}",
        f"- **Date**: {latest['date']}",
        f"- **Overall**: **{latest['overall']}**/100",
        f"- 표제부: {_score_str(latest.get('title'))} | "
        f"갑구: {_score_str(latest.get('section_a'))} | "
        f"을구: {_score_str(latest.get('section_b'))}",
        "",
    ]

    if len(recent) >= 2:
        lines += [
            "## Version History", "",
            "```mermaid", "xychart-beta",
            '  title "Overall Score by Version"',
            "  x-axis [{}]".format(", ".join(f'"v{h["version"]}"' for h in recent)),
            '  y-axis "Score" 0 --> 100',
            "  bar [{}]".format(", ".join(str(h["overall"]) for h in recent)),
            "```", "",
        ]

    lines += [
        "## Score Table", "",
        "| Version | Date | Overall | 표제부 | 갑구 | 을구 | Files |",
        "|---------|------|---------|--------|------|------|-------|",
    ]
    for h in reversed(recent):
        lines.append(
            f"| v{h['version']} | {h['date']} | "
            f"**{h['overall']}** | {_score_str(h.get('title'))} | "
            f"{_score_str(h.get('section_a'))} | {_score_str(h.get('section_b'))} | "
            f"{h['files']} |"
        )
    lines.append("")

    lines += [
        "## File Details (Latest)", "",
        "| File | Type | Score | 표제부 | 갑구 | 을구 | Tokens |",
        "|------|------|-------|--------|------|------|--------|",
    ]
    for d in latest.get("details", []):
        lines.append(
            f"| {d['file']} | {d['type']} | **{d['score']}** | "
            f"{_score_str(d.get('title'))} | {_score_str(d.get('section_a'))} | "
            f"{_score_str(d.get('section_b'))} | "
            f"{d.get('parser_tokens', 0)}/{d.get('gt_tokens', 0)} |"
        )
    lines.append("")

    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Report: {out}")


# ==================== CLI ====================

def main():
    ap = argparse.ArgumentParser(description="PDF 파서 벤치마크")
    ap.add_argument("pdf_path", nargs="?", help="특정 PDF 파일 경로")
    ap.add_argument("--verbose", "-v", action="store_true", help="누락 토큰 상세")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    ap.add_argument("--save", "-s", action="store_true", help="히스토리 저장")
    ap.add_argument("--report", "-r", action="store_true", help="Markdown 리포트 생성")
    ap.add_argument("--type", "-t", default="registry", help="문서 타입 (기본: registry)")
    ap.add_argument("--parser", "-p", default="latest", help="파서 버전 (기본: latest)")
    ap.add_argument("--all-parsers", action="store_true", help="전 버전 순차 비교")
    ap.add_argument("--list", action="store_true", help="파서 목록")
    ap.add_argument("--upload-dir", default=DEFAULT_UPLOAD_DIR, help="PDF 디렉토리")
    args = ap.parse_args()

    # --list
    if args.list:
        print("등록된 문서 타입:")
        for dt in list_document_types():
            versions = list_versions(dt.type_id)
            ver_str = ", ".join(f"v{v}" for v in versions)
            print(f"  {dt.type_id} ({dt.display_name}): {ver_str}")
            if dt.sub_types:
                print(f"    sub-types: {', '.join(dt.sub_types)}")
        return

    # --report
    if args.report:
        generate_report_md(doc_type=args.type)
        return

    # PDF 수집
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

    # --all-parsers
    if args.all_parsers:
        for ver in list_versions(args.type):
            p = get_parser(args.type, ver)
            report = run_benchmark(pdf_paths, parser=p, document_type=args.type)
            print_report(report, verbose=args.verbose)
            if args.save:
                save_to_json(report)
        if args.save:
            generate_report_md(doc_type=args.type)
        return

    # 단일 실행
    p = get_parser(args.type, args.parser)
    report = run_benchmark(pdf_paths, parser=p, document_type=args.type)

    if args.json:
        print_json(report)
    else:
        print_report(report, verbose=args.verbose)

    if args.save:
        save_to_json(report)
        generate_report_md(doc_type=args.type)


if __name__ == "__main__":
    main()
