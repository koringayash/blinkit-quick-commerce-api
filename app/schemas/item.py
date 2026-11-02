from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

ItemSortBy = Literal[
    "relevance",
    "name_asc",
    "name_desc",
    "price_asc",
    "price_desc",
    "stock_desc",
]


class ItemCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50, examples=["MILK-NANDINI-500ML"])
    name: str = Field(..., min_length=1, max_length=100, examples=["Nandini GoodLife Toned Milk 500ml"])
    category: str | None = Field(None, min_length=1, max_length=50, examples=["Dairy & Breakfast"])
    brand: str | None = Field(None, min_length=1, max_length=50, examples=["Nandini"])
    description: str | None = Field(
        None,
        max_length=500,
        examples=["Pasteurized toned milk, rich in calcium and protein."],
    )
    price: float = Field(..., gt=0, examples=[27.0])
    available_qty: int = Field(..., ge=0, examples=[15])


class ItemUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    category: str | None = Field(None, min_length=1, max_length=50)
    brand: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = Field(None, max_length=500)
    price: float | None = Field(None, gt=0)


class StockUpdateRequest(BaseModel):
    # Positive to restock (e.g., +10), Negative when user buys (e.g., -2)
    delta_qty: int = Field(..., description="Negative to deduct stock, positive to add stock", examples=[-2])


class ItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    category: str | None = None
    brand: str | None = None
    description: str | None = None
    price: float
    available_qty: int

    @computed_field
    @property
    def in_stock(self) -> bool:
        return self.available_qty > 0


class FacetCount(BaseModel):
    name: str
    total_items: int
    in_stock_items: int


class SearchFacets(BaseModel):
    categories: list[FacetCount] = Field(default_factory=list, description="Category counts matching the search")
    brands: list[FacetCount] = Field(default_factory=list, description="Brand counts matching the search")
    min_price: float | None = Field(None, description="Lowest price among matching items")
    max_price: float | None = Field(None, description="Highest price among matching items")


class ItemSearchResponse(BaseModel):
    store_id: int | None = Field(None, description="Dark Store ID if results are scoped to a specific dark store")
    store_code: str | None = Field(None, description="Dark Store code if results are scoped to a specific dark store")
    eta_minutes: int | None = Field(None, description="Estimated delivery ETA in minutes when customer coordinates are provided")
    distance_km: float | None = Field(None, description="Distance in km to the matched dark store")
    items: list[ItemResponse]
    total: int = Field(..., description="Total number of items matching the search/filters")
    limit: int
    offset: int
    has_more: bool
    facets: SearchFacets = Field(default_factory=SearchFacets)


class ProductSuggestion(BaseModel):
    sku: str
    name: str
    category: str | None = None
    brand: str | None = None
    price: float
    in_stock: bool


class SearchSuggestionsResponse(BaseModel):
    query: str
    products: list[ProductSuggestion]
    matching_categories: list[str]
    matching_brands: list[str]
