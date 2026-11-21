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