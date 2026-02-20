"""도메인 예외"""


class DomainError(Exception):
    """도메인 레이어 기본 예외"""
    pass


class InsufficientCreditsError(DomainError):
    def __init__(self):
        super().__init__("크레딧이 부족합니다.")


class DailyLimitExceededError(DomainError):
    def __init__(self, limit: int):
        super().__init__(f"일일 파싱 한도({limit}회)를 초과했습니다.")


class ProductNotFoundError(DomainError):
    def __init__(self, product_id: str):
        super().__init__(f"상품을 찾을 수 없습니다: {product_id}")


class ProductDisabledError(DomainError):
    def __init__(self, product_id: str):
        super().__init__(f"비활성화된 상품입니다: {product_id}")


class ParserNotFoundError(DomainError):
    def __init__(self, doc_type: str, version: str):
        super().__init__(f"파서를 찾을 수 없습니다: {doc_type} v{version}")


class UserNotFoundError(DomainError):
    def __init__(self):
        super().__init__("사용자를 찾을 수 없습니다.")


class InvalidCredentialsError(DomainError):
    def __init__(self):
        super().__init__("유효하지 않은 인증 정보입니다.")
