import time
from pydantic import BaseModel, Field, field_validator, ValidationError
import sys
import logging
import sqlite3
from pathlib import Path
from typing import Any, Literal
from fastmcp import FastMCP

# 1. Cấu hình logging xuất ra stderr (tuyệt đối không dùng stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    stream=sys.stderr,
    )
logger = logging.getLogger("backend-support-mcp")

# Trỏ đúng tới data/app.db tính từ thư mục gốc dự án
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"
mcp = FastMCP("BackendSupportMCP")

# 2. Schema validate đầu vào bằng Pydantic
class OrderLookupInput(BaseModel):
    order_code: str = Field(..., min_length=4, max_length=20, description="Mã đơn hàng dạng ORD-1001")

    @field_validator("order_code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        code = v.strip().upper()
        if not code.startswith("ORD-"):
            raise ValueError("Mã đơn hàng phải bắt đầu bằng 'ORD-' (ví dụ: ORD-1001).")
        return code

class TicketFilterInput(BaseModel):
    status: Literal["open", "in_progress", "resolved"] | None = None
    priority: Literal["low", "medium", "high"] | None = None
    limit: int = Field(default=20, ge=1, le=100)

def get_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy file database tại {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Trả về dạng dict-like thay vì tuple
    return conn


@mcp.resource("db://schema")
def get_database_schema() -> str:
    """Trả về cấu trúc các bảng hiện có trong cơ sở dữ liệu."""
    logger.info("Resource requested: db://schema")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return "\n\n".join(f"-- Table: {row['name']}\n{row['sql']}" for row in rows)


@mcp.tool()
def get_order_by_code(order_code: str) -> dict[str, Any]:
    """Tra cứu chi tiết một đơn hàng theo mã order_code (ví dụ: ORD-1001), kèm thông tin khách hàng."""
    start = time.perf_counter()
    try:
        validated = OrderLookupInput(order_code=order_code)
        logger.info("Tool call: get_order_by_code(order_code=%s)", validated.order_code)

        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT o.order_code, o.product_name, o.total_amount, o.status, o.updated_at,
                    c.full_name AS customer_name, c.email AS customer_email, c.tier AS customer_tier
                FROM orders o
                JOIN customers c ON o.customer_id = c.id
                WHERE o.order_code = ?
                """,
                (validated.order_code.strip().upper(),),
            ).fetchone()

        elapsed_ms = (time.perf_counter() - start) * 1000
        if not row:
            logger.info("Order %s not found (%.1fms)", validated.order_code, elapsed_ms)
            return {"found": False, "message": f"Không tìm thấy đơn hàng có mã '{validated.order_code}'."}

        logger.info("Order %s fetched successfully (%.1fms)", validated.order_code, elapsed_ms)
        return {"found": True, "order": dict(row)}

    except ValidationError as e:
        logger.warning("Validation error in get_order_by_code: %s", e)
        return {"found": False, "error": "invalid_input", "details": e.errors()[0]["msg"]}
    except (sqlite3.Error, FileNotFoundError) as e:
        logger.exception("Database error in get_order_by_code")
        return {"found": False, "error": "database_error", "details": str(e)}

@mcp.tool()
def list_support_tickets(
    status: Literal["open", "in_progress", "resolved"] | None = None,
    priority: Literal["low", "medium", "high"] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Lọc danh sách phiếu hỗ trợ (support tickets) từ cơ sở dữ liệu.
    - status: 'open', 'in_progress', hoặc 'resolved' (để trống nếu lấy tất cả)
    - priority: 'low', 'medium', hoặc 'high' (để trống nếu lấy tất cả)
    """
    start = time.perf_counter()
    try:
        validated = TicketFilterInput(status=status, priority=priority, limit=limit)
        logger.info(
            "Tool call: list_support_tickets(status=%s, priority=%s, limit=%d)",
            validated.status,
            validated.priority,
            validated.limit
        )

        query = """
            SELECT t.id, t.subject, t.priority, t.status, t.created_at,
                c.full_name AS customer_name, c.tier AS customer_tier,
                o.order_code
            FROM support_tickets t
            JOIN customers c ON t.customer_id = c.id
            LEFT JOIN orders o ON t.order_id = o.id
            WHERE 1=1
        """
        params: list[Any] = []

        if validated.status:
            query += " AND t.status = ?"
            params.append(validated.status)
        if validated.priority:
            query += " AND t.priority = ?"
            params.append(validated.priority)

        query += " ORDER BY t.created_at DESC LIMIT ?"
        params.append(validated.limit)

        with get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("Fetched %d tickets (%.1fms)", len(rows), elapsed_ms)

        return {"count": len(rows), "tickets": [dict(row) for row in rows]}

    except ValidationError as e:
        logger.warning("Validation error in list_support_tickets: %s", e)
        return {"count": 0, "error": "invalid_input", "details": e.errors()[0]["msg"]}
    except (sqlite3.Error, FileNotFoundError) as e:
        logger.exception("Database error in list_support_tickets")
        return {"count": 0, "error": "database_error", "details": str(e)}

if __name__ == "__main__":
    logger.info("Starting BackendSupportMCP server (DB=%s)", DB_PATH)
    mcp.run()