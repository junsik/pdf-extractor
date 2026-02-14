"""등기부등본 PDF 파서 CLI

사용법:
    # 단일 파일
    uv run python cli.py upload/1575693_13501996047446.pdf

    # 여러 파일
    uv run python cli.py upload/*.pdf

    # JSON 출력
    uv run python cli.py upload/1575693_13501996047446.pdf --json

    # 요약만
    uv run python cli.py upload/*.pdf --summary

    # 특정 섹션만
    uv run python cli.py upload/1575693_13501996047446.pdf --section 을구
"""
import argparse
import glob
import json
import sys
import os
from pathlib import Path

# backend 디렉토리를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from pdf_parser import parse_registry_pdf


def format_entry_a(e: dict) -> str:
    """갑구 항목 포맷"""
    c = " [말소]" if e["is_cancelled"] else ""
    owners = ", ".join(o["name"] for o in e.get("owners", []) if o.get("name"))
    creditor = e["creditor"]["name"] if e.get("creditor") and e["creditor"].get("name") else ""
    person = owners or creditor
    amt = f" 금{e['claim_amount']:,}원" if e.get("claim_amount") else ""
    shares = [
        f'{o["name"]}({o["share"]})'
        for o in e.get("owners", [])
        if o.get("share")
    ]
    share_str = f" [{', '.join(shares)}]" if shares else ""
    cancel = f"\n         → {e['cancels_rank_number']}번 말소" if e.get("cancels_rank_number") else ""
    return (
        f"  {e['rank_number']:>6} | {e['registration_type']:<22} "
        f"| {e['receipt_date']:<15} | {person}{amt}{share_str}{c}{cancel}"
    )


def format_entry_b(e: dict) -> str:
    """을구 항목 포맷"""
    c = " [말소]" if e["is_cancelled"] else ""
    m = e["mortgagee"]["name"] if e.get("mortgagee") and e["mortgagee"].get("name") else ""
    amt = ""
    if e.get("max_claim_amount"):
        amt = f" 채권최고액 금{e['max_claim_amount']:,}원"
    elif e.get("deposit_amount"):
        amt = f" 보증금 금{e['deposit_amount']:,}원"
    purpose = f"\n         목적: {e['purpose']}" if e.get("purpose") else ""
    cancel = f"\n         → {e['cancels_rank_number']}번 말소" if e.get("cancels_rank_number") else ""
    return (
        f"  {e['rank_number']:>6} | {e['registration_type']:<22} "
        f"| {e['receipt_date']:<15} | {m}{amt}{c}{purpose}{cancel}"
    )


def print_detail(data: dict):
    """상세 출력"""
    print(f"고유번호: {data['unique_number']}")
    print(f"부동산종류: {data['property_type']}")
    print(f"주소: {data['property_address']}")

    ti = data["title_info"]
    print(f"\n[표제부]")
    if ti.get("land_type"):
        print(f"  지목: {ti['land_type']}, 면적: {ti.get('land_area', '')}")
    if ti.get("building_name"):
        print(f"  건물명: {ti['building_name']}")
    if ti.get("building_type"):
        print(f"  건물종류: {ti['building_type']}")
    if ti.get("structure"):
        print(f"  구조: {ti['structure']}")
    if ti.get("roof_type"):
        print(f"  지붕: {ti['roof_type']}")
    if ti.get("floors"):
        print(f"  층수: {ti['floors']}층")
    if ti.get("exclusive_area"):
        print(f"  전유면적: {ti['exclusive_area']}㎡")
    if ti.get("land_right_ratio"):
        print(f"  대지권비율: {ti['land_right_ratio']}")
    if ti.get("road_address"):
        print(f"  도로명주소: {ti['road_address']}")
    if ti.get("areas"):
        print(f"  층별면적: {len(ti['areas'])}건, 총 {ti.get('total_floor_area', 0):.2f}㎡")

    # 표제부 토지 항목
    if ti.get("land_entries"):
        print(f"  토지표시 {len(ti['land_entries'])}건:")
        for le in ti["land_entries"]:
            dn = (le.get("display_number") or "").replace("\n", " ")
            loc = (le.get("location") or "").replace("\n", " ")[:35]
            lt = (le.get("land_type") or "").replace("\n", " ")
            ar = (le.get("area") or "").replace("\n", " ")
            if dn or loc:
                print(f"    [{dn:>8}] {loc:<35} {lt:<6} {ar}")

    print(f"\n[갑구] 총 {data['section_a_count']}건 (활성 {data['active_section_a_count']}건)")
    for e in data["section_a"]:
        print(format_entry_a(e))

    print(f"\n[을구] 총 {data['section_b_count']}건 (활성 {data['active_section_b_count']}건)")
    for e in data["section_b"]:
        print(format_entry_b(e))


def print_summary(data: dict, fname: str):
    """요약 한줄 출력"""
    sa = data["section_a_count"]
    sa_a = data["active_section_a_count"]
    sb = data["section_b_count"]
    sb_a = data["active_section_b_count"]
    ptype = data["property_type"]
    addr = data["property_address"][:30]
    area = data["title_info"].get("land_area", "") or ""
    btype = data["title_info"].get("building_type", "") or ""
    extra = area or btype
    print(f"  {fname:<35} {ptype:<20} {addr:<30} 갑:{sa}({sa_a}) 을:{sb}({sb_a}) {extra}")


def print_section(data: dict, section: str):
    """특정 섹션만 출력"""
    section_lower = section.lower()
    if section_lower in ("갑구", "갑", "a", "section_a"):
        print(f"[갑구] 총 {data['section_a_count']}건 (활성 {data['active_section_a_count']}건)")
        for e in data["section_a"]:
            print(format_entry_a(e))
    elif section_lower in ("을구", "을", "b", "section_b"):
        print(f"[을구] 총 {data['section_b_count']}건 (활성 {data['active_section_b_count']}건)")
        for e in data["section_b"]:
            print(format_entry_b(e))
    elif section_lower in ("표제부", "표제", "title"):
        ti = data["title_info"]
        print(json.dumps(ti, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"알 수 없는 섹션: {section} (갑구/을구/표제부)", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="등기부등본 PDF 파서 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python cli.py ../upload/1575693*.pdf          단일 PDF 상세 출력
  python cli.py ../upload/*.pdf --summary       전체 요약
  python cli.py ../upload/*.pdf --json          JSON 출력
  python cli.py file.pdf --section 을구          을구만 출력
        """,
    )
    parser.add_argument("files", nargs="+", help="PDF 파일 경로 (glob 패턴 가능)")
    parser.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    parser.add_argument("--summary", action="store_true", help="요약만 출력")
    parser.add_argument("--section", type=str, help="특정 섹션만 출력 (갑구/을구/표제부)")
    args = parser.parse_args()

    # 파일 목록 확장 (Windows glob 지원)
    files = []
    for pattern in args.files:
        expanded = glob.glob(pattern)
        if expanded:
            files.extend(expanded)
        elif os.path.isfile(pattern):
            files.append(pattern)
        else:
            print(f"파일 없음: {pattern}", file=sys.stderr)
            sys.exit(1)

    files = [f for f in files if f.lower().endswith(".pdf")]
    if not files:
        print("PDF 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)

    results = []
    for fpath in sorted(files):
        fname = os.path.basename(fpath)
        with open(fpath, "rb") as f:
            data = parse_registry_pdf(f.read())

        if args.json:
            results.append(data)
            continue

        if args.summary:
            print_summary(data, fname)
            continue

        if len(files) > 1:
            print(f"\n{'=' * 80}")
            print(f"  {fname}")
            print(f"{'=' * 80}")

        if args.section:
            print_section(data, args.section)
        else:
            print_detail(data)

    if args.json:
        output = results if len(results) > 1 else results[0]
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
