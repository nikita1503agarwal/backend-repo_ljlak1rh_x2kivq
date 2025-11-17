import os
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Product as ProductSchema, TaxRate as TaxRateSchema, Sale as SaleSchema

app = FastAPI(title="Keystone POS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"name": "Keystone POS API", "status": "ok"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = getattr(db, 'name', '✅ Connected')
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Check environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# Utility functions

def ensure_default_taxes() -> List[Dict]:
    """Ensure default Tunisian TVA tax rates exist (7%, 13%, 19%)."""
    defaults = [
        {"name": "TVA 7%", "rate": 0.07, "code": "TVA7", "is_default": False},
        {"name": "TVA 13%", "rate": 0.13, "code": "TVA13", "is_default": False},
        {"name": "TVA 19%", "rate": 0.19, "code": "TVA19", "is_default": True},
    ]
    existing = {t.get("code"): t for t in get_documents("taxrate")}
    created = []
    for d in defaults:
        if d["code"] not in existing:
            create_document("taxrate", d)
            created.append(d)
    return created


# API models to control inputs
class ProductIn(BaseModel):
    sku: str
    name: str
    price: float
    stock: float = 0
    unit: str = "unit"
    tax_code: Optional[str] = None
    barcode: Optional[str] = None
    category: Optional[str] = None
    is_active: bool = True


@app.post("/api/seed")
def seed_demo():
    """Seed database with default taxes and demo products/customers."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    created_taxes = ensure_default_taxes()

    # Seed a few products if empty
    if db["product"].count_documents({}) == 0:
        demo_products = [
            {"sku": "MILK-1L", "name": "Milk 1L", "price": 2.500, "stock": 100, "unit": "pcs", "tax_code": "TVA7", "category": "Grocery"},
            {"sku": "BREAD-STD", "name": "Bread", "price": 0.600, "stock": 200, "unit": "pcs", "tax_code": "TVA7", "category": "Bakery"},
            {"sku": "SHMP-250", "name": "Shampoo 250ml", "price": 8.900, "stock": 50, "unit": "pcs", "tax_code": "TVA19", "category": "Personal Care"},
            {"sku": "SUGAR-1KG", "name": "Sugar 1kg", "price": 3.200, "stock": 80, "unit": "kg", "tax_code": "TVA13", "category": "Grocery"},
        ]
        for p in demo_products:
            create_document("product", p)

    # Seed a demo user
    if db["user"].count_documents({}) == 0:
        create_document("user", {"username": "admin", "display_name": "Admin", "role": "admin", "is_active": True})

    return {
        "status": "ok",
        "taxes_created": len(created_taxes),
        "products": db["product"].count_documents({}),
        "users": db["user"].count_documents({}),
    }


@app.get("/api/taxes")
def list_taxes():
    ensure_default_taxes()
    return get_documents("taxrate")


@app.get("/api/products")
def list_products():
    return get_documents("product")


@app.post("/api/products")
def create_product(product: ProductIn):
    # Basic uniqueness check for SKU
    if db["product"].count_documents({"sku": product.sku}) > 0:
        raise HTTPException(status_code=400, detail="SKU already exists")
    create_document("product", product.model_dump())
    return {"status": "created"}


@app.get("/api/sales")
def list_sales():
    return get_documents("sale")


@app.post("/api/sales")
def create_sale(sale: SaleSchema):
    # Build a map of taxes
    taxes = {t.get("code"): t for t in get_documents("taxrate")}

    # Calculate totals
    subtotal = 0.0
    tax_total = 0.0
    tax_breakdown: Dict[str, float] = {}

    # Validate stock and compute line totals
    for item in sale.items:
        # fetch product for validation/price if needed
        prod = db["product"].find_one({"sku": item.sku})
        if not prod:
            raise HTTPException(status_code=400, detail=f"Unknown SKU: {item.sku}")
        line_price = item.qty * item.unit_price
        subtotal += line_price
        if item.tax_code and item.tax_code in taxes:
            rate = float(taxes[item.tax_code]["rate"])
            tax_amount = line_price * rate
            tax_total += tax_amount
            tax_breakdown[item.tax_code] = tax_breakdown.get(item.tax_code, 0.0) + tax_amount
        # reduce stock
        db["product"].update_one({"_id": prod["_id"]}, {"$inc": {"stock": -float(item.qty)}})

    total = subtotal + tax_total

    sale_record = sale.model_dump()
    sale_record.update({
        "subtotal": round(subtotal, 3),
        "tax_total": round(tax_total, 3),
        "total": round(total, 3),
        "tax_breakdown": {k: round(v, 3) for k, v in tax_breakdown.items()},
    })

    create_document("sale", sale_record)
    return {"status": "created", "totals": {"subtotal": sale_record["subtotal"], "tax_total": sale_record["tax_total"], "total": sale_record["total"]}}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
