# Backend AI Assistant

Tài liệu hướng dẫn thiết lập và nhật ký xây dựng từng bước cho dự án **Backend AI Assistant** (SQLite + FastMCP + RAG + LangGraph).

---

## A. Khởi tạo cấu trúc mã nguồn dự án (Ngày 1: 21/10/2026)

### 1. Tạo kho lưu trữ Git (Git Repository)

Tạo một Git repository mới có tên `backend-ai-assistant`.

### 2. Tạo cấu trúc thư mục

Sắp xếp các thư mục và tệp tin trong dự án theo cấu trúc sau:

```text
backend-ai-assistant/
├── data/
│   ├── app.db              # File SQLite được tạo từ script nạp dữ liệu mẫu
│   └── docs/               # Chứa 5–10 file Markdown/PDF cho phần RAG (Ngày 4)
├── db/
│   ├── schema.sql          # Định nghĩa 3 bảng nghiệp vụ cốt lõi
│   └── seed.py             # Script khởi tạo cơ sở dữ liệu và nạp dữ liệu mẫu
├── mcp_server/             # Mã nguồn MCP Server (Ngày 2–3)
├── rag/                    # Mã nguồn chunking, embedding và Vector DB (Ngày 4–6)
├── agent/                  # Mã nguồn đồ thị LangGraph (Tuần 2)
├── .env.example
├── .gitignore
└── README.md
```

Nội dung tệp `.env.example`:

```dotenv
LLM_API_KEY=your_api_key_here
DB_PATH=./data/app.db
```

### 3. Thiết kế cơ sở dữ liệu nghiệp vụ (`db/schema.sql`)

Tạo 3 bảng quan hệ có khóa ngoại (`customers`, `orders` và `support_tickets`) để MCP Server có thể thực hiện các truy vấn thực tế (như tra cứu đơn hàng theo mã đơn hoặc lọc các phiếu hỗ trợ đang mở theo email khách hàng):

```sql
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    tier TEXT CHECK(tier IN ('standard', 'vip')) DEFAULT 'standard',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    total_amount REAL NOT NULL,
    status TEXT CHECK(status IN ('pending', 'shipping', 'delivered', 'cancelled')) NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS support_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    order_id INTEGER,
    subject TEXT NOT NULL,
    priority TEXT CHECK(priority IN ('low', 'medium', 'high')) DEFAULT 'medium',
    status TEXT CHECK(status IN ('open', 'in_progress', 'resolved')) DEFAULT 'open',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
```

### 4. Tạo script nạp dữ liệu mẫu (`db/seed.py`)

Tạo tệp `db/seed.py` để khởi tạo `data/app.db` và chèn dữ liệu mẫu vào từng bảng (khoảng 3–10 bản ghi mỗi bảng, bao gồm các trạng thái và mức ưu tiên như `shipping`, `delivered`, `open` và `high` để dễ dàng kiểm thử các công cụ lọc dữ liệu):

```python
import sqlite3
from pathlib import Path

Path("data").mkdir(exist_ok=True)
conn = sqlite3.connect("data/app.db")

with open("db/schema.sql", "r", encoding="utf-8") as f:
    conn.executescript(f.read())

conn.executemany(
    "INSERT OR IGNORE INTO customers (full_name, email, tier) VALUES (?, ?, ?)",
    [
        ("Nguyễn Văn An", "an.nguyen@example.com", "vip"),
        ("Trần Thị Bình", "binh.tran@example.com", "standard"),
        ("Lê Minh Châu", "chau.le@example.com", "vip"),
    ],
)

conn.executemany(
    "INSERT OR IGNORE INTO orders (order_code, customer_id, product_name, total_amount, status) VALUES (?, ?, ?, ?, ?)",
    [
        ("ORD-1001", 1, "Bàn phím cơ Keychron K2", 2100000, "shipping"),
        ("ORD-1002", 2, "Chuột Logitech MX Master 3S", 2450000, "delivered"),
        ("ORD-1003", 1, "Màn hình Dell UltraSharp 27", 11500000, "pending"),
    ],
)

conn.executemany(
    "INSERT OR IGNORE INTO support_tickets (customer_id, order_id, subject, priority, status) VALUES (?, ?, ?, ?, ?)",
    [
        (1, 1, "Đơn ORD-1001 giao chậm 2 ngày", "high", "open"),
        (2, 2, "Yêu cầu xuất hóa đơn VAT", "low", "resolved"),
        (1, 3, "Hỏi thời gian dự kiến giao hàng", "medium", "in_progress"),
    ],
)

conn.commit()
conn.close()
print("Đã tạo xong data/app.db!")
```

### 5. Khởi tạo cơ sở dữ liệu và đẩy commit đầu tiên

Chạy script seed để tạo và nạp dữ liệu cho cơ sở dữ liệu:

```bash
python db/seed.py
# Hoặc trên Windows với Python launcher:
py db/seed.py
```

Mở tệp `data/app.db` bằng tiện ích mở rộng **SQLite Viewer** trong VS Code (hoặc DBeaver) để kiểm tra dữ liệu, sau đó commit và push lên GitHub:

```bash
git add .
git commit -m "chore: init project structure and sample SQLite database"
git push origin main
```

---

## B. Xây dựng MCP Server bằng FastMCP: 1 Resource và 2 Tool đọc trực tiếp từ SQLite (Ngày 2: 22/10/2026)

### 1. Ôn lại sự khác biệt giữa Tool và Resource

Trước khi bắt tay vào triển khai, bạn chỉ cần nắm vững 2 khái niệm nền tảng trong kiến trúc MCP:

- **Tool (`@mcp.tool`) — Do mô hình điều khiển (Model-controlled):** Là các hàm có tham số mà LLM có thể chủ động chọn gọi khi cần truy vấn dữ liệu hoặc thực hiện một hành động. FastMCP tự động chuyển đổi type hints của Python thành JSON Schema và sử dụng docstring để giúp LLM hiểu khi nào và gọi từng tool như thế nào *(FastMCP Docs)*.
- **Resource (`@mcp.resource`) — Do ứng dụng điều khiển (Application-controlled):** Là nguồn dữ liệu chỉ đọc được định danh bằng một URI (ví dụ: `db://schema`), cho phép client cung cấp sẵn cho LLM các nội dung tĩnh hoặc thông tin hệ thống có cấu trúc.

### 2. Cài đặt môi trường ảo (Virtual Environment) và thư viện FastMCP

Tại thư mục gốc của dự án (`backend-ai-assistant`), tạo môi trường ảo, kích hoạt nó và cài đặt `fastmcp`:

```bash
python -m venv .venv
# Hoặc trên Windows với Python launcher:
py -m venv .venv
```

Kích hoạt môi trường ảo:

```bash
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

# macOS / Linux:
source .venv/bin/activate
```

Cài đặt `fastmcp` và lưu danh sách thư viện phụ thuộc:

```bash
pip install fastmcp
pip freeze > requirements.txt
```

### 3. Triển khai MCP Server (`mcp_server/server.py`)

Hai nguyên tắc quan trọng dành cho lập trình viên backend: luôn sử dụng truy vấn tham số hóa (parameterized query `?`) để phòng chống SQL injection, và xác định đường dẫn tương đối thông qua `__file__` để server luôn tìm thấy `data/app.db` dù được gọi từ bất kỳ thư mục làm việc nào:

```python
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
```

### 4. Kiểm tra hoạt động của MCP Server và commit lên GitHub (~10 phút)

Bạn có 2 cách kiểm thử nhanh ngay trên máy:

1. **Kiểm thử bằng giao diện trực quan (MCP Inspector):** Chạy lệnh sau (yêu cầu cài đặt Node.js) để mở công cụ kiểm tra trên trình duyệt. Kiểm tra tab **Tools** và **Resources**, sau đó thử gọi `get_order_by_code` với `"ORD-1001"` và `list_support_tickets` với `status="open"`:

   ```bash
   fastmcp dev inspector mcp_server/server.py
   ```

2. **Kiểm thử nhanh bằng Python Client trong cùng tiến trình (không cần cài Node.js):** Tạo tệp `mcp_server/test_client.py` và chạy `python mcp_server/test_client.py`:

   ```python
   import asyncio
   from fastmcp import Client
   from server import mcp


   async def main():
       async with Client(mcp) as client:
           tools = await client.list_tools()
           print("Tools:", [t.name for t in tools])

           order = await client.call_tool("get_order_by_code", {"order_code": "ORD-1001"})
           print("Order result:", order)

           tickets = await client.call_tool("list_support_tickets", {"status": "open"})
           print("Open tickets:", tickets)


   asyncio.run(main())
   ```

Khi cả 2 tool và resource đều trả về dữ liệu chính xác từ `data/app.db`, hãy commit và đẩy mã nguồn lên GitHub:

```bash
git add mcp_server/ requirements.txt
git commit -m "feat(mcp): add initial MCP server with order lookup and ticket filter tools"
git push origin main
```

> **Lưu ý khi chạy MCP Server qua `stdio`:** Không sử dụng lệnh `print()` để debug bên trong `server.py`, vì luồng `stdout` được dùng để truyền các gói tin JSON-RPC của giao thức MCP. Nếu cần ghi log gỡ lỗi, hãy sử dụng module `logging` của Python cấu hình xuất ra `sys.stderr` (chúng ta sẽ hoàn thiện phần này ở tác vụ Ngày 3).

---

## C. Nâng cấp MCP Server với Pydantic, Logging ra `stderr` và kết nối vào Cursor / Claude Desktop (Ngày 3: 25/11/2026)

Để hoàn thành tác vụ Ngày 3 (Thứ 4, 25/11), bạn sẽ nâng cấp `mcp_server/server.py` lên chuẩn production hơn (chặn dữ liệu sai bằng Pydantic, bắt lỗi DB, ghi log sạch ra `stderr`), sau đó kết nối trực tiếp vào Cursor hoặc Claude Desktop để kiểm thử với LLM thật.

### 1. Nâng cấp `mcp_server/server.py` với Pydantic và Logging ra `stderr` (~20 phút)

`fastmcp` đã cài sẵn `pydantic`. Bạn cập nhật lại `mcp_server/server.py` để:

- Ghi toàn bộ log vào `sys.stderr` (tránh làm hỏng luồng JSON-RPC trên `stdout`).
- Dùng `Literal`, `Field` và validator của Pydantic để ép LLM truyền đúng định dạng `order_code`, `status`, `priority` và `limit`.
- Bọc `try/except (sqlite3.Error, FileNotFoundError)` và ghi nhận thời gian thực thi (`ms`) của mỗi lần gọi tool.

```python
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Literal
from fastmcp import FastMCP
from pydantic import BaseModel, Field, ValidationError, field_validator

# 1. Cấu hình logging xuất ra stderr (tuyệt đối không dùng stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("backend-support-mcp")

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
    conn.row_factory = sqlite3.Row
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
                (validated.order_code,),
            ).fetchone()

        elapsed_ms = (time.perf_counter() - start) * 1000
        if not row:
            logger.info("Order %s not found (%.1fms)", validated.order_code, elapsed_ms)
            return {"found": False, "message": f"Không tìm thấy đơn hàng '{validated.order_code}'."}

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
    """Lọc danh sách phiếu hỗ trợ (support tickets) theo status, priority và giới hạn số bản ghi."""
    start = time.perf_counter()
    try:
        validated = TicketFilterInput(status=status, priority=priority, limit=limit)
        logger.info(
            "Tool call: list_support_tickets(status=%s, priority=%s, limit=%d)",
            validated.status,
            validated.priority,
            validated.limit,
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
```

### 2. Kết nối MCP Server vào Cursor (khuyên dùng, ~5 phút)

Theo [tài liệu MCP của Cursor](https://cursor.com/docs/mcp), bạn chỉ cần tạo tệp `.cursor/mcp.json` ngay tại thư mục gốc dự án để dùng biến `${workspaceFolder}` (không cần hardcode đường dẫn cá nhân):

**Trên Windows:**

```json
{
  "mcpServers": {
    "backend-support": {
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["${workspaceFolder}/mcp_server/server.py"]
    }
  }
}
```

**Trên macOS / Linux:** đổi `command` thành `"${workspaceFolder}/.venv/bin/python"`.

Sau đó nhấn `Ctrl+Shift+P` → **Reload Window**, vào **Settings → Tools & MCP** để đảm bảo server `backend-support` hiện chấm xanh và liệt kê đủ 2 tool.

### 3. Hoặc kết nối vào Claude Desktop (~5 phút)

Mở tệp cấu hình theo [hướng dẫn kết nối local server của MCP](https://modelcontextprotocol.io/docs/2026-07-28/develop/connect-local-servers):

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

Claude Desktop yêu cầu đường dẫn tuyệt đối (thay `D:\\projects\\backend-ai-assistant` bằng đường dẫn thật trên máy bạn):

```json
{
  "mcpServers": {
    "backend-support": {
      "command": "D:\\projects\\backend-ai-assistant\\.venv\\Scripts\\python.exe",
      "args": ["D:\\projects\\backend-ai-assistant\\mcp_server\\server.py"]
    }
  }
}
```

Tắt hẳn Claude Desktop (kể cả dưới khay hệ thống System Tray trên Windows) rồi mở lại. Nếu server không hiện, xem log `stderr` ngay bằng PowerShell:

```powershell
type "$env:AppData\Claude\logs\mcp*.log"
```

### 4. Chạy 3 kịch bản test thực tế và commit lên GitHub (~10 phút)

Mở chế độ Agent trong Cursor (hoặc chat trong Claude Desktop) và thử lần lượt 3 kịch bản sau để kiểm chứng:

1. **Test gọi chuỗi 2 tool (Happy path):** *"Kiểm tra giúp tôi đơn hàng ORD-1001 đang ở trạng thái nào và xem có ticket nào đang mở ở mức ưu tiên high không?"*
2. **Test validate input sai (Edge case):** *"Tra cứu giúp tôi đơn hàng có mã ABC-999"* → xác nhận tool không crash mà trả về lỗi `invalid_input` rõ ràng.
3. **Test kiểm tra log:** Mở bảng **Output / MCP Logs** trong Cursor (hoặc file log Claude Desktop) để xác nhận log hiển thị đủ timestamp, tên tool, tham số và thời gian xử lý (`ms`).

Cuối cùng push bản hoàn thiện MCP Server lên GitHub:

```bash
git add mcp_server/server.py .cursor/mcp.json
git commit -m "feat(mcp): add Pydantic validation, stderr logging, and Cursor MCP config"
git push origin main
```
