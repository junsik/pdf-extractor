"""관리자 CLI 도구

사용법:
  [로컬]
    uv run python admin.py stats                     서비스 현황 요약
    uv run python admin.py users                     사용자 목록
    uv run python admin.py users --plan basic        플랜별 필터
    uv run python admin.py user user@example.com     사용자 상세
    uv run python admin.py user user@example.com plan enterprise  플랜 변경
    uv run python admin.py user user@example.com credit 10     크레딧 설정
    uv run python admin.py user user@example.com credit +5     크레딧 추가
    uv run python admin.py user user@example.com disable       계정 비활성화
    uv run python admin.py user user@example.com enable        계정 활성화
    uv run python admin.py parses                    최근 파싱 기록
    uv run python admin.py parses --days 7           최근 7일
    uv run python admin.py payments                  결제 내역
    uv run python admin.py revenue                   매출 요약

  [K8s 운영환경]
    MSYS_NO_PATHCONV=1 kubectl -n app exec deploy/pdf-service-aio -- python /srv/backend/admin.py stats
    MSYS_NO_PATHCONV=1 kubectl -n app exec deploy/pdf-service-aio -- python /srv/backend/admin.py users
    MSYS_NO_PATHCONV=1 kubectl -n app exec deploy/pdf-service-aio -- python /srv/backend/admin.py user user@example.com
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# DB 상대 경로가 올바르게 해석되도록 스크립트 위치로 이동
os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db_session
from models import User, ParseRecord, Payment, PlanType, UserRole, ParseStatus, PaymentStatus
from auth import hash_password, generate_api_key


# ==================== 유틸 ====================

def fmt_date(dt) -> str:
    if not dt:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M")


def fmt_plan(plan) -> str:
    if not plan:
        return "free"
    return plan.value if hasattr(plan, "value") else str(plan)


def fmt_credits(credits: int) -> str:
    return "무제한" if credits == -1 else str(credits)


def print_table(headers: list, rows: list, col_widths: list = None):
    """간단한 테이블 출력"""
    if not col_widths:
        col_widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0)) + 2
                      for i, h in enumerate(headers)]

    header_line = "".join(str(h).ljust(w) for h, w in zip(headers, col_widths))
    print(header_line)
    print("-" * len(header_line))
    for row in rows:
        print("".join(str(c).ljust(w) for c, w in zip(row, col_widths)))


# ==================== 명령어 ====================

async def cmd_stats():
    """서비스 현황 요약"""
    async with get_db_session() as s:
        # 사용자 통계
        total_users = (await s.execute(select(func.count(User.id)))).scalar()
        active_users = (await s.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )).scalar()
        plan_counts = {}
        for plan in PlanType:
            cnt = (await s.execute(
                select(func.count(User.id)).where(User.plan == plan, User.is_active == True)
            )).scalar()
            plan_counts[plan.value] = cnt

        # 오늘 파싱
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_parses = (await s.execute(
            select(func.count(ParseRecord.id)).where(ParseRecord.created_at >= today)
        )).scalar()

        # 이번 달 파싱
        month_start = today.replace(day=1)
        month_parses = (await s.execute(
            select(func.count(ParseRecord.id)).where(ParseRecord.created_at >= month_start)
        )).scalar()

        # 전체 파싱
        total_parses = (await s.execute(select(func.count(ParseRecord.id)))).scalar()

        # 이번 달 매출
        month_revenue = (await s.execute(
            select(func.sum(Payment.amount)).where(
                Payment.status == PaymentStatus.COMPLETED,
                Payment.paid_at >= month_start
            )
        )).scalar() or 0

        # 전체 매출
        total_revenue = (await s.execute(
            select(func.sum(Payment.amount)).where(Payment.status == PaymentStatus.COMPLETED)
        )).scalar() or 0

    print("=== 서비스 현황 ===\n")

    print(f"[사용자]")
    print(f"  전체: {total_users}명 (활성: {active_users}명)")
    for plan, cnt in plan_counts.items():
        label = settings.PRICING[plan]["name"]
        print(f"  {label}: {cnt}명")

    print(f"\n[파싱]")
    print(f"  오늘: {today_parses}건")
    print(f"  이번 달: {month_parses}건")
    print(f"  전체: {total_parses}건")

    print(f"\n[매출]")
    print(f"  이번 달: {month_revenue:,}원")
    print(f"  전체: {total_revenue:,}원")


async def cmd_users(plan_filter: str = None):
    """사용자 목록"""
    async with get_db_session() as s:
        q = select(User).order_by(desc(User.created_at))
        if plan_filter:
            q = q.where(User.plan == PlanType(plan_filter))
        result = await s.execute(q)
        users = result.scalars().all()

    if not users:
        print("사용자가 없습니다.")
        return

    headers = ["ID", "이메일", "이름", "플랜", "크레딧", "사용량", "상태", "가입일"]
    rows = []
    for u in users:
        status_str = "활성" if u.is_active else "비활성"
        if u.role == UserRole.ADMIN:
            status_str += "(관리자)"
        rows.append([
            u.id, u.email, u.name or "-",
            fmt_plan(u.plan), fmt_credits(u.credits), u.credits_used,
            status_str, fmt_date(u.created_at)
        ])
    print(f"사용자 {len(rows)}명:\n")
    print_table(headers, rows)


async def cmd_user_detail(email: str):
    """사용자 상세"""
    async with get_db_session() as s:
        result = await s.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"사용자를 찾을 수 없습니다: {email}")
            sys.exit(1)

        # 오늘 파싱 횟수
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = (await s.execute(
            select(func.count(ParseRecord.id)).where(
                ParseRecord.user_id == user.id,
                ParseRecord.created_at >= today
            )
        )).scalar()

        # 전체 파싱 횟수
        total_parses = (await s.execute(
            select(func.count(ParseRecord.id)).where(ParseRecord.user_id == user.id)
        )).scalar()

        # 결제 합계
        total_paid = (await s.execute(
            select(func.sum(Payment.amount)).where(
                Payment.user_id == user.id,
                Payment.status == PaymentStatus.COMPLETED
            )
        )).scalar() or 0

        # 최근 파싱 5건
        recent_parses = (await s.execute(
            select(ParseRecord)
            .where(ParseRecord.user_id == user.id)
            .order_by(desc(ParseRecord.created_at))
            .limit(5)
        )).scalars().all()

    plan_key = fmt_plan(user.plan)
    daily_limit = settings.PRICING.get(plan_key, {}).get("daily_limit", 3)
    daily_limit_str = "무제한" if daily_limit == -1 else str(daily_limit)

    print(f"=== 사용자 상세 ===\n")
    print(f"  ID:       {user.id}")
    print(f"  이메일:    {user.email}")
    print(f"  이름:      {user.name or '-'}")
    print(f"  전화:      {user.phone or '-'}")
    print(f"  회사:      {user.company or '-'}")
    print(f"  역할:      {user.role.value}")
    print(f"  상태:      {'활성' if user.is_active else '비활성'}")
    print(f"  가입일:    {fmt_date(user.created_at)}")
    print(f"  최근로그인: {fmt_date(user.last_login_at)}")

    print(f"\n[요금제]")
    print(f"  플랜:      {settings.PRICING.get(plan_key, {}).get('name', plan_key)}")
    print(f"  크레딧:    {fmt_credits(user.credits)} (누적 사용: {user.credits_used})")
    print(f"  일일한도:  {daily_limit_str} (오늘 사용: {today_count})")
    print(f"  기간:      {fmt_date(user.plan_start_date)} ~ {fmt_date(user.plan_end_date)}")

    print(f"\n[통계]")
    print(f"  전체 파싱: {total_parses}건")
    print(f"  총 결제:   {total_paid:,}원")

    if user.webhook_enabled:
        print(f"\n[웹훅]")
        print(f"  URL:    {user.webhook_url}")
        print(f"  Secret: {'설정됨' if user.webhook_secret else '-'}")

    if user.api_key:
        print(f"\n[API 키]")
        print(f"  {user.api_key[:8]}...{user.api_key[-4:]}")

    if recent_parses:
        print(f"\n[최근 파싱]")
        for p in recent_parses:
            addr = (p.property_address or "")[:25]
            print(f"  {fmt_date(p.created_at)}  {p.status.value:<10}  {p.file_name[:20]:<20}  {addr}")


async def cmd_user_plan(email: str, new_plan: str):
    """플랜 변경"""
    try:
        plan = PlanType(new_plan)
    except ValueError:
        print(f"잘못된 플랜: {new_plan} (free/basic/enterprise)")
        sys.exit(1)

    async with get_db_session() as s:
        result = await s.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"사용자를 찾을 수 없습니다: {email}")
            sys.exit(1)

        old_plan = fmt_plan(user.plan)
        user.plan = plan
        user.credits = settings.PRICING[plan.value]["credits"]
        user.plan_start_date = datetime.utcnow()
        user.plan_end_date = datetime.utcnow() + timedelta(days=30)

    print(f"{email}: {old_plan} -> {plan.value} (크레딧: {fmt_credits(user.credits)})")


async def cmd_user_credit(email: str, amount_str: str):
    """크레딧 설정/추가"""
    async with get_db_session() as s:
        result = await s.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"사용자를 찾을 수 없습니다: {email}")
            sys.exit(1)

        old_credits = user.credits
        if amount_str.startswith("+") or amount_str.startswith("-"):
            delta = int(amount_str)
            user.credits = max(0, user.credits + delta) if user.credits != -1 else -1
        else:
            user.credits = int(amount_str)

    print(f"{email}: 크레딧 {fmt_credits(old_credits)} -> {fmt_credits(user.credits)}")


async def cmd_user_password(email: str, new_password: str):
    """비밀번호 변경"""
    async with get_db_session() as s:
        result = await s.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"사용자를 찾을 수 없습니다: {email}")
            sys.exit(1)

        user.password_hash = hash_password(new_password)

    print(f"{email}: 비밀번호 변경 완료")


async def cmd_user_create(email: str, password: str, name: str = None):
    """사용자 생성"""
    async with get_db_session() as s:
        result = await s.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            print(f"이미 존재하는 이메일입니다: {email}")
            sys.exit(1)

        user = User(
            email=email,
            password_hash=hash_password(password),
            name=name or email.split("@")[0],
            role=UserRole.USER,
            plan=PlanType.FREE,
            credits=settings.PRICING["free"]["credits"],
            api_key=generate_api_key(),
        )
        s.add(user)

    print(f"사용자 생성 완료: {email}")


async def cmd_user_toggle(email: str, enable: bool):
    """계정 활성/비활성"""
    async with get_db_session() as s:
        result = await s.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"사용자를 찾을 수 없습니다: {email}")
            sys.exit(1)

        user.is_active = enable

    action = "활성화" if enable else "비활성화"
    print(f"{email}: {action} 완료")


async def cmd_parses(days: int = 1):
    """최근 파싱 기록"""
    since = datetime.utcnow() - timedelta(days=days)
    async with get_db_session() as s:
        result = await s.execute(
            select(ParseRecord, User.email)
            .join(User, ParseRecord.user_id == User.id)
            .where(ParseRecord.created_at >= since)
            .order_by(desc(ParseRecord.created_at))
            .limit(100)
        )
        rows_raw = result.all()

    if not rows_raw:
        print(f"최근 {days}일간 파싱 기록이 없습니다.")
        return

    headers = ["일시", "사용자", "상태", "파일명", "주소", "처리시간"]
    rows = []
    for record, email in rows_raw:
        addr = (record.property_address or "")[:25]
        time_str = f"{record.processing_time:.1f}s" if record.processing_time else "-"
        rows.append([
            fmt_date(record.created_at), email[:20],
            record.status.value, record.file_name[:20], addr, time_str
        ])

    print(f"최근 {days}일 파싱 기록 ({len(rows)}건):\n")
    print_table(headers, rows)


async def cmd_payments(days: int = 30):
    """결제 내역"""
    since = datetime.utcnow() - timedelta(days=days)
    async with get_db_session() as s:
        result = await s.execute(
            select(Payment, User.email)
            .join(User, Payment.user_id == User.id)
            .where(Payment.created_at >= since)
            .order_by(desc(Payment.created_at))
            .limit(100)
        )
        rows_raw = result.all()

    if not rows_raw:
        print(f"최근 {days}일간 결제 내역이 없습니다.")
        return

    headers = ["일시", "사용자", "플랜", "금액", "상태", "결제수단"]
    rows = []
    for pay, email in rows_raw:
        method = f"{pay.card_company or ''} {pay.card_number or ''}".strip() or pay.method or "-"
        rows.append([
            fmt_date(pay.paid_at or pay.created_at), email[:20],
            pay.plan_name, f"{pay.amount:,}원", pay.status.value, method[:15]
        ])

    print(f"최근 {days}일 결제 내역 ({len(rows)}건):\n")
    print_table(headers, rows)


async def cmd_revenue():
    """매출 요약"""
    async with get_db_session() as s:
        now = datetime.utcnow()

        print("=== 매출 요약 ===\n")

        # 월별 매출 (최근 6개월)
        headers = ["월", "건수", "매출"]
        rows = []
        for i in range(6):
            m_start = (now.replace(day=1) - timedelta(days=30 * i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if i == 0:
                m_end = now
            else:
                m_end = (m_start + timedelta(days=32)).replace(day=1)

            count = (await s.execute(
                select(func.count(Payment.id)).where(
                    Payment.status == PaymentStatus.COMPLETED,
                    Payment.paid_at >= m_start,
                    Payment.paid_at < m_end
                )
            )).scalar() or 0

            amount = (await s.execute(
                select(func.sum(Payment.amount)).where(
                    Payment.status == PaymentStatus.COMPLETED,
                    Payment.paid_at >= m_start,
                    Payment.paid_at < m_end
                )
            )).scalar() or 0

            rows.append([m_start.strftime("%Y-%m"), count, f"{amount:,}원"])

        print_table(headers, rows)

        # 플랜별 매출
        print(f"\n[플랜별 누적 매출]")
        for plan in PlanType:
            if plan == PlanType.FREE:
                continue
            amount = (await s.execute(
                select(func.sum(Payment.amount)).where(
                    Payment.status == PaymentStatus.COMPLETED,
                    Payment.plan_type == plan
                )
            )).scalar() or 0
            count = (await s.execute(
                select(func.count(Payment.id)).where(
                    Payment.status == PaymentStatus.COMPLETED,
                    Payment.plan_type == plan
                )
            )).scalar() or 0
            label = settings.PRICING[plan.value]["name"]
            print(f"  {label}: {count}건, {amount:,}원")


# ==================== 메인 ====================

def main():
    parser = argparse.ArgumentParser(
        description="등기부등본 PDF 서비스 관리 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
명령어:
  stats                              서비스 현황 요약
  users [--plan free|basic|enterprise]  사용자 목록
  user <email>                         사용자 상세
  user <email> plan <free|basic|enterprise> 플랜 변경
  user <email> credit <N|+N|-N>      크레딧 설정/증감
  user <email> password <new_pw>     비밀번호 변경
  user <email> create <password>     사용자 생성
  user <email> disable               계정 비활성화
  user <email> enable                계정 활성화
  parses [--days N]                  최근 파싱 기록 (기본 1일)
  payments [--days N]                결제 내역 (기본 30일)
  revenue                            매출 요약
        """,
    )
    parser.add_argument("command", help="명령어")
    parser.add_argument("args", nargs="*", help="추가 인자")
    parser.add_argument("--plan", help="플랜 필터 (users 명령)")
    parser.add_argument("--days", type=int, help="조회 기간 (일)")

    args = parser.parse_args()
    cmd = args.command

    if cmd == "stats":
        asyncio.run(cmd_stats())

    elif cmd == "users":
        asyncio.run(cmd_users(args.plan))

    elif cmd == "user":
        if not args.args:
            parser.error("이메일을 지정해주세요: admin.py user <email>")
        email = args.args[0]
        if len(args.args) == 1:
            asyncio.run(cmd_user_detail(email))
        elif args.args[1] == "plan":
            if len(args.args) < 3:
                parser.error("플랜을 지정해주세요: admin.py user <email> plan <free|basic|enterprise>")
            asyncio.run(cmd_user_plan(email, args.args[2]))
        elif args.args[1] == "credit":
            if len(args.args) < 3:
                parser.error("크레딧을 지정해주세요: admin.py user <email> credit <N|+N|-N>")
            asyncio.run(cmd_user_credit(email, args.args[2]))
        elif args.args[1] == "password":
            if len(args.args) < 3:
                parser.error("비밀번호를 지정해주세요: admin.py user <email> password <new_pw>")
            asyncio.run(cmd_user_password(email, args.args[2]))
        elif args.args[1] == "create":
            if len(args.args) < 3:
                parser.error("비밀번호를 지정해주세요: admin.py user <email> create <password> [name]")
            name = args.args[3] if len(args.args) > 3 else None
            asyncio.run(cmd_user_create(email, args.args[2], name))
        elif args.args[1] == "disable":
            asyncio.run(cmd_user_toggle(email, False))
        elif args.args[1] == "enable":
            asyncio.run(cmd_user_toggle(email, True))
        else:
            parser.error(f"알 수 없는 하위 명령: {args.args[1]}")

    elif cmd == "parses":
        days = args.days or 1
        asyncio.run(cmd_parses(days))

    elif cmd == "payments":
        days = args.days or 30
        asyncio.run(cmd_payments(days))

    elif cmd == "revenue":
        asyncio.run(cmd_revenue())

    else:
        parser.error(f"알 수 없는 명령: {cmd}")


if __name__ == "__main__":
    main()
