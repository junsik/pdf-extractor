"""상품(문서 파서 타입) 라우터 — NEW"""
from fastapi import APIRouter
from parsers import list_document_types, list_versions
from api.schemas.products import ProductInfo, ProductListResponse

router = APIRouter(prefix="/api/products", tags=["상품"])


@router.get("", response_model=ProductListResponse)
async def get_products():
    """사용 가능한 문서 파서 타입 목록"""
    doc_types = list_document_types()
    products = []
    for dt in doc_types:
        versions = list_versions(dt.type_id)
        products.append(ProductInfo(
            id=dt.type_id,
            name=dt.display_name,
            description=dt.description,
            available_versions=[f"v{v}" for v in versions],
        ))
    return ProductListResponse(products=products)
