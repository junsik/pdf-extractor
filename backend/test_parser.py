"""파서 검증 스크립트"""
import glob
import json
from pdf_parser import parse_registry_pdf

for path in glob.glob('c:/work/pdf-service/upload/*.pdf'):
    print(f"\n{'='*80}")
    print(f"PDF: {path.split('/')[-1]}")
    print(f"{'='*80}")

    with open(path, 'rb') as f:
        data = parse_registry_pdf(f.read())

    # 기본 정보
    print(f"고유번호: {data['unique_number']}")
    print(f"부동산종류: {data['property_type']}")
    print(f"주소: {data['property_address']}")

    # 표제부
    ti = data['title_info']
    print(f"\n[표제부]")
    if ti.get('land_type'):
        print(f"  지목: {ti['land_type']}, 면적: {ti['land_area']}")
    if ti.get('building_name'):
        print(f"  건물명: {ti['building_name']}")
    if ti.get('structure'):
        print(f"  구조: {ti['structure']}")
    if ti.get('roof_type'):
        print(f"  지붕: {ti['roof_type']}")
    if ti.get('floors'):
        print(f"  층수: {ti['floors']}층")
    if ti.get('building_type'):
        print(f"  건물종류: {ti['building_type']}")
    if ti.get('exclusive_area'):
        print(f"  전유면적: {ti['exclusive_area']}㎡")
    if ti.get('land_right_ratio'):
        print(f"  대지권비율: {ti['land_right_ratio']}")
    if ti.get('road_address'):
        print(f"  도로명주소: {ti['road_address']}")
    if ti.get('areas'):
        print(f"  층별면적: {len(ti['areas'])}건, 총 {ti['total_floor_area']:.2f}㎡")

    # 갑구
    print(f"\n[갑구] 총 {data['section_a_count']}건 (활성 {data['active_section_a_count']}건)")
    for e in data['section_a']:
        cancelled = " [말소]" if e['is_cancelled'] else ""
        owner_name = e['owner']['name'] if e.get('owner') else ""
        creditor_name = e['creditor']['name'] if e.get('creditor') else ""
        person = owner_name or creditor_name
        amount = f" 금{e['claim_amount']:,}원" if e.get('claim_amount') else ""
        print(f"  {e['rank_number']:>5} | {e['registration_type']:<20} | "
              f"{e['receipt_date']:<15} | {person}{amount}{cancelled}")
        if e.get('cancels_rank_number'):
            print(f"         → {e['cancels_rank_number']}번 말소")

    # 을구
    print(f"\n[을구] 총 {data['section_b_count']}건 (활성 {data['active_section_b_count']}건)")
    for e in data['section_b']:
        cancelled = " [말소]" if e['is_cancelled'] else ""
        mortgagee = e['mortgagee']['name'] if e.get('mortgagee') else ""
        amount = ""
        if e.get('max_claim_amount'):
            amount = f" 채권최고액 금{e['max_claim_amount']:,}원"
        elif e.get('deposit_amount'):
            amount = f" 보증금 금{e['deposit_amount']:,}원"
        print(f"  {e['rank_number']:>5} | {e['registration_type']:<20} | "
              f"{e['receipt_date']:<15} | {mortgagee}{amount}{cancelled}")
        if e.get('purpose'):
            print(f"         목적: {e['purpose']}")
        if e.get('cancels_rank_number'):
            print(f"         → {e['cancels_rank_number']}번 말소")
