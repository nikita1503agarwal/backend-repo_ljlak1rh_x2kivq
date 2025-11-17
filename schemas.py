"""
Database Schemas for Keystone POS

Each Pydantic model represents a MongoDB collection. The collection name is the
lowercase of the class name (e.g., Product -> "product").

These schemas validate data for products, customers, taxes, users, and sales.
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime

# Core domain models

class TaxRate(BaseModel):
    name: str = Field(..., description="Display name e.g., TVA 19%")
    rate: float = Field(..., ge=0, le=1, description="Tax rate as decimal (e.g., 0.19 for 19%)")
    code: str = Field(..., description="Tax code identifier e.g., TVA19")
    is_default: bool = Field(False, description="Whether this is the default tax")

class Product(BaseModel):
    sku: str = Field(..., description="Stock Keeping Unit")
    name: str = Field(..., description="Product name")
    price: float = Field(..., ge=0, description="Unit price")
    stock: float = Field(0, ge=0, description="Current stock quantity")
    unit: str = Field("unit", description="Measurement unit (unit, kg, pcs, etc.)")
    tax_code: Optional[str] = Field(None, description="Tax code to apply (e.g., TVA19)")
    barcode: Optional[str] = Field(None, description="Barcode value if available")
    category: Optional[str] = Field(None, description="Category name")
    is_active: bool = Field(True)

class Customer(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    note: Optional[str] = None

class User(BaseModel):
    username: str
    display_name: str
    role: Literal["cashier", "manager", "admin"] = "cashier"
    is_active: bool = True

class SaleItem(BaseModel):
    sku: str
    name: str
    qty: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    tax_code: Optional[str] = None

class Payment(BaseModel):
    method: Literal["cash", "card", "mixed"] = "cash"
    paid: float = Field(..., ge=0)
    change: float = 0

class Sale(BaseModel):
    items: List[SaleItem]
    customer_name: Optional[str] = None
    subtotal: float = 0
    tax_total: float = 0
    total: float = 0
    tax_breakdown: Optional[dict] = None
    payment: Payment
    user: Optional[str] = None
    timestamp: Optional[datetime] = None
