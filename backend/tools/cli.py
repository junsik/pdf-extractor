"""PDF 파서 CLI

Usage:
    python tools/cli.py upload/sample.pdf              # 상세 출력
    python tools/cli.py upload/*.pdf --summary         # 요약
    python tools/cli.py upload/sample.pdf --json       # JSON
    python tools/cli.py upload/sample.pdf --section 을구  # 특정 섹션
    python tools/cli.py upload/sample.pdf --type registry --parser v1.0.0
"""
import argparse
import glob
import json
import sys
import os
from pathlib import Path

_BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)
os.chdir(_BACKEND_ROOT)

from parsers import get_parser


def format_entry_a(e: dict) -> str:
    c = " [말소]" if e["is_cancelled"] else ""
    owners = ", ".join(o["name"] for o in e.get("owners", []) if o.get("name"))
    creditor = e["creditor"]["name"] if e.get("creditor") and e["creditor"].get("name") else ""
    person = owners or creditor
    amt = f" 금{e['claim_amount']:,}원" if e.get("claim_amount") else ""
    shares = [f'{o["name"]}({o["share"]})' for o in e.get("owners", []) if o.get("share")]
    share_str = f" [{', '.join(shares)}]" if shares else ""
    cancel = f"\n         → {e['cancels_rank_number']}번 말소" if e.get("cancels_rank_number") else ""
    return (f"  {e['rank_number']:>6} | {e['registration_type']:<22} "
            f"| {e['receipt_date']:<15} | {person}{amt}{share_str}{c}{cancel}")


def format_entry_b(e: dict) -> str:
    c = " [말소]" if e["is_cancelled"] else ""
    m = e["mortgagee"]["name"] if e.get("mortgagee") and e["mortgagee"].get("name") else ""
    amt = ""
    if e.get("max_claim_amount"):
        amt = f" 채권최고액 금{e['max_claim_amount']:,}원"
    elif e.get("deposit_amount"):
        amt = f" 보증금 금{e['deposit_amount']:,}원"
    purpose = f"\n         목적: {e['purpose']}" if e.get("purpose") else ""
    cancel = f"\n         → {e['cancels_rank_number']}번 말소" if e.get("cancels_rank_number") else ""
    return (f"  {e['rank_number']:>6} | {e['registration_type']:<22} "
            f"| {e['receipt_date']:<15} | {m}{amt}{c}{purpose}{cancel}")


def print_detail(data: dict):
    print(f"고유번호: {data['unique_number']}")
    print(f"부동산종류: {data['property_type']}")
    print(f"주소: {data['property_address']}")

    ti = data["title_info"]
    print(f"\n[표제부]")
    for k, label in [("land_type", "지목"), ("building_name", "건물명"),
                      ("building_type", "건물종류"), ("structure", "구조"),
                      ("roof_type", "지붕"), ("exclusive_area", "전유면적"),
                      ("land_right_ratio", "대지권비율"), ("road_address", "도로명주소")]:
        if ti.get(k):
            suffix = "㎡" if k == "exclusive_area" else ""
            print(f"  {label}: {ti[k]}{suffix}")
    if ti.get("floors"):
        print(f"  층수: {ti['floors']}층")
    if ti.get("land_area"):
        print(f"  면적: {ti['land_area']}")
    if ti.get("areas"):
        print(f"  층별면적: {len(ti['areas'])}건, 총 {ti.get('total_floor_area', 0):.2f}㎡")
    if ti.get("land_entries"):
        print(f"  토지표시 {len(ti['land_entries'])}건")

    print(f"\n[갑구] 총 {data['section_a_count']}건 (활성 {data['active_section_a_count']}건)")
    for e in data["section_a"]:
        print(format_entry_a(e))

    print(f"\n[을구] 총 {data['section_b_count']}건 (활성 {data['active_section_b_count']}건)")
    for e in data["section_b"]:
        print(format_entry_b(e))


def print_summary(data: dict, fname: str):
    sa, sa_a = data["section_a_count"], data["active_section_a_count"]
    sb, sb_a = data["section_b_count"], data["active_section_b_count"]
    addr = data["property_address"][:30]
    extra = data["title_info"].get("land_area", "") or data["title_info"].get("building_type", "") or ""
    print(f"  {fname:<35} {data['property_type']:<20} {addr:<30} 갑:{sa}({sa_a}) 을:{sb}({sb_a}) {extra}")


def print_section(data: dict, section: str):
    s = section.lower()
    if s in ("갑구", "갑", "a", "section_a"):
        print(f"[갑구] 총 {data['section_a_count']}건")
        for e in data["section_a"]:
            print(format_entry_a(e))
    elif s in ("을구", "을", "b", "section_b"):
        print(f"[을구] 총 {data['section_b_count']}건")
        for e in data["section_b"]:
            print(format_entry_b(e))
    elif s in ("표제부", "표제", "title"):
        print(json.dumps(data["title_info"], ensure_ascii=False, indent=2, default=str))
    else:
        print(f"알 수 없는 섹션: {section}", file=sys.stderr)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="PDF 파서 CLI")
    ap.add_argument("files", nargs="+", help="PDF 파일 경로")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    ap.add_argument("--summary", action="store_true", help="요약 출력")
    ap.add_argument("--section", type=str, help="특정 섹션 (갑구/을구/표제부)")
    ap.add_argument("--type", "-t", default="registry", help="문서 타입")
    ap.add_argument("--parser", "-p", default="latest", help="파서 버전")
    args = ap.parse_args()

    files = []
    for pattern in args.files:
        expanded = glob.glob(pattern)
        files.extend(expanded if expanded else ([pattern] if os.path.isfile(pattern) else []))
    files = [f for f in files if f.lower().endswith(".pdf")]
    if not files:
        print("PDF 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)

    parser = get_parser(args.type, args.parser)
    results = []

    for fpath in sorted(files):
        fname = os.path.basename(fpath)
        with open(fpath, "rb") as f:
            parse_result = parser.parse(f.read())
        data = parse_result.data

        if args.json:
            results.append(data)
            continue
        if args.summary:
            print_summary(data, fname)
            continue
        if len(files) > 1:
            print(f"\n{'=' * 80}\n  {fname}\n{'=' * 80}")
        if args.section:
            print_section(data, args.section)
        else:
            print_detail(data)

    if args.json:
        output = results if len(results) > 1 else results[0]
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
