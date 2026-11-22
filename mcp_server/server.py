import sqlite3
from pathlib import Path
from typing import Any
from fastmcp import FastMCP

# Trỏ đúng tới data/app.db tính từ thư mục gốc dự án
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

mcp = FastMCP("BackendSupportMCP")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Trả về dạng dict-like thay vì tuple
    return conn


@mcp.resource("db://schema")
def get_database_schema() -> str:
    """Trả về cấu trúc các bảng hiện có trong cơ sở dữ liệu."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return "\n\n".join(f"-- Table: {row['name']}\n{row['sql']}" for row in rows)


@mcp.tool()
def get_order_by_code(order_code: str) -> dict[str, Any]:
    """Tra cứu chi tiết một đơn hàng theo mã order_code (ví dụ: ORD-1001), kèm thông tin khách hàng."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT o.order_code, o.product_name, o.total_amount, o.status, o.updated_at,
                   c.full_name AS customer_name, c.email AS customer_email, c.tier AS customer_tier
            FROM orders o
            JOIN customers c ON o.customer_id = c.id
            WHERE o.order_code = ?
            """,
            (order_code.strip().upper(),),
        ).fetchone()

    if not row:
        return {"found": False, "message": f"Không tìm thấy đơn hàng có mã '{order_code}'."}

    return {"found": True, "order": dict(row)}


@mcp.tool()
def list_support_tickets(
    status: str | None = None,
    priority: str | None = None,
) -> list[dict[str, Any]]:
    """
    Lọc danh sách phiếu hỗ trợ (support tickets) từ cơ sở dữ liệu.
    - status: 'open', 'in_progress', hoặc 'resolved' (để trống nếu lấy tất cả)
    - priority: 'low', 'medium', hoặc 'high' (để trống nếu lấy tất cả)
    """
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

    if status:
        query += " AND t.status = ?"
        params.append(status.strip().lower())
    if priority:
        query += " AND t.priority = ?"
        params.append(priority.strip().lower())

    query += " ORDER BY t.created_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(row) for row in rows]


if __name__ == "__main__":
    mcp.run()