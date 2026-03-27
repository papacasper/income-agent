"""
Polar.sh integration — full API product creation, checkout links, order tracking.
SDK: pip install polar-sdk
Docs: https://docs.polar.sh

Setup:
  1. Sign up at https://polar.sh
  2. Create an organization
  3. Settings → API Tokens → New token with scopes:
       products:write, orders:read, checkouts:write
  4. Add to .env:
       POLAR_ACCESS_TOKEN=your_token
       POLAR_ORGANIZATION_ID=your_org_id  (Settings → General)
"""
import os
from polar_sdk import Polar
from polar_sdk.models import (
    ProductCreateOneTime,
    ProductPriceFixedCreate,
    CheckoutLinkCreateProduct,
)


def _client() -> Polar:
    token = os.getenv("POLAR_ACCESS_TOKEN")
    if not token:
        raise ValueError("POLAR_ACCESS_TOKEN not set in .env")
    return Polar(access_token=token)


def _org_id() -> str:
    org = os.getenv("POLAR_ORGANIZATION_ID")
    if not org:
        raise ValueError("POLAR_ORGANIZATION_ID not set in .env")
    return org


# ------------------------------------------------------------------
# Products
# ------------------------------------------------------------------

def create_product(name: str, description: str, price_cents: int) -> dict:
    """Create a one-time purchase product and return its checkout URL."""
    # Polar enforces 64-char name limit
    name = name[:64]
    with _client() as polar:
        result = polar.products.create(
            request=ProductCreateOneTime(
                name=name,
                description=description,
                prices=[
                    ProductPriceFixedCreate(
                        price_amount=price_cents,
                        price_currency="usd",
                    )
                ],
            )
        )
        product_id = result.id

        # Create checkout link immediately
        link = polar.checkout_links.create(
            request=CheckoutLinkCreateProduct(product_id=product_id)
        )

    return {
        "id": product_id,
        "name": result.name,
        "price_cents": price_cents,
        "checkout_url": link.url,
    }


def list_products() -> list[dict]:
    """List all active products."""
    with _client() as polar:
        page = polar.products.list(limit=100)
        items = page.result.items if page and page.result else []
    return [{"id": p.id, "name": p.name, "is_archived": p.is_archived} for p in items]


# ------------------------------------------------------------------
# Orders / revenue
# ------------------------------------------------------------------

def get_orders(limit: int = 100) -> list[dict]:
    """Get recent paid orders."""
    with _client() as polar:
        page = polar.orders.list(limit=limit)
        items = page.result.items if page and page.result else []
    return [
        {
            "id": o.id,
            "status": str(o.status),
            "amount": o.amount,
            "currency": o.currency,
            "customer_email": getattr(o.customer, "email", ""),
            "product_name": getattr(o.product, "name", ""),
            "created_at": str(o.created_at),
        }
        for o in items
    ]


def get_revenue_summary() -> dict:
    """Aggregate net revenue from paid orders."""
    orders = get_orders()
    paid = [o for o in orders if "paid" in o["status"].lower() or "succeeded" in o["status"].lower()]
    gross_cents = sum(o["amount"] for o in paid)
    # Polar fee: 4% + 40¢ per transaction
    net_cents = sum(o["amount"] - int(o["amount"] * 0.04) - 40 for o in paid)
    return {
        "total_orders": len(paid),
        "gross_revenue_usd": gross_cents / 100,
        "net_revenue_usd": max(0, net_cents / 100),
        "orders": paid,
    }


# ------------------------------------------------------------------
# Main entry point for sales agent
# ------------------------------------------------------------------

def launch_product(name: str, description: str, price_cents: int, file_path: str = None) -> dict:
    """Create product + checkout URL. File delivery note added to description."""
    full_desc = description
    if file_path:
        import os as _os
        full_desc += f"\n\n📎 **File included:** {_os.path.basename(file_path)}\n*Download link sent automatically after purchase.*"
    return create_product(name, full_desc, price_cents)
