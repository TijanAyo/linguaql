BEGIN;

DROP TABLE IF EXISTS shipments, reviews, payments, order_items, orders,
                     products, customers, suppliers, categories CASCADE;

-- ---------------------------------------------------------------- schema ----
CREATE TABLE categories (
    id   SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE suppliers (
    id      SERIAL PRIMARY KEY,
    name    TEXT NOT NULL,
    country TEXT NOT NULL
);

CREATE TABLE customers (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT UNIQUE NOT NULL,
    country    TEXT NOT NULL,
    segment    TEXT NOT NULL,            -- consumer / business / vip
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories (id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers (id),
    sku         TEXT UNIQUE NOT NULL,
    cost        NUMERIC(10, 2) NOT NULL,
    price       NUMERIC(10, 2) NOT NULL,
    stock       INTEGER NOT NULL,
    created_at  TIMESTAMP NOT NULL
);

CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    status      TEXT NOT NULL,           -- completed / shipped / processing / refunded / cancelled
    channel     TEXT NOT NULL,           -- web / mobile / partner
    total       NUMERIC(10, 2) NOT NULL DEFAULT 0,  -- filled from order_items below
    created_at  TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    id         SERIAL PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders (id),
    product_id INTEGER NOT NULL REFERENCES products (id),
    quantity   INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);

CREATE TABLE payments (
    id       SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders (id),
    method   TEXT NOT NULL,              -- card / paypal / bank_transfer / apple_pay
    amount   NUMERIC(10, 2) NOT NULL,
    status   TEXT NOT NULL,              -- paid / refunded / failed
    paid_at  TIMESTAMP NOT NULL
);

CREATE TABLE reviews (
    id          SERIAL PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products (id),
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    rating      INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment     TEXT,
    created_at  TIMESTAMP NOT NULL
);

CREATE TABLE shipments (
    id           SERIAL PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES orders (id),
    carrier      TEXT NOT NULL,          -- DHL / FedEx / UPS / Royal Mail / GIG
    status       TEXT NOT NULL,          -- delivered / in_transit / pending
    shipped_at   TIMESTAMP,
    delivered_at TIMESTAMP
);

-- ------------------------------------------------------------- reference ----
INSERT INTO categories (name) VALUES
    ('Accessories'), ('Displays'), ('Laptops'), ('Audio'),
    ('Storage'), ('Networking'), ('Peripherals'), ('Cables');

INSERT INTO suppliers (name, country) VALUES
    ('Shenzhen TechWorks',  'CN'),
    ('Bavaria Electronics', 'DE'),
    ('Lagos Gadgets Ltd',   'NG'),
    ('Austin Components',    'US'),
    ('Nordic Peripherals',  'SE'),
    ('Kyoto Micro',          'JP'),
    ('Mumbai Hardware Co',   'IN'),
    ('Manchester Supplies',  'UK');

-- ------------------------------------------------- customers (60 rows) -------
INSERT INTO customers (name, email, country, segment, created_at)
SELECT
    (ARRAY['Alice','Bilal','Chen','Diana','Erica','Femi','Grace','Hiro','Ines','Jamal',
           'Kira','Liam','Mei','Noah','Omar','Priya','Quinn','Rosa','Sam','Tara'])[1 + (g % 20)]
      || ' ' ||
    (ARRAY['Johnson','Ahmed','Wei','Prince','Mensah','Okoro','Kim','Tanaka','Silva','Brown',
           'Patel','Nguyen','Garcia','Muller','Rossi','Haddad','Cohen','Ivanov','Santos','Adeyemi'])[1 + ((g * 7) % 20)],
    'user' || g || '@example.com',
    (ARRAY['US','UK','SG','GH','DE','FR','CA','NG','IN','JP'])[1 + (g % 10)],
    (ARRAY['consumer','business','consumer','consumer','vip'])[1 + (g % 5)],
    timestamp '2024-01-01' + (random() * 550 || ' days')::interval
FROM generate_series(1, 60) AS g;

-- --------------------------------------------------- products (48 rows) ------
WITH gen AS (
    SELECT g, round((10 + random() * 190)::numeric, 2) AS cost
    FROM generate_series(1, 48) AS g
)
INSERT INTO products (name, category_id, supplier_id, sku, cost, price, stock, created_at)
SELECT
    (ARRAY['Wireless Mouse','Mechanical Keyboard','27in Monitor','USB-C Hub','Laptop Stand',
           'Noise-Cancelling Headphones','Portable SSD 1TB','Wi-Fi 6 Router','Webcam 1080p','HDMI Cable 2m',
           'Bluetooth Speaker','NVMe SSD 2TB','8-port Switch','Mic Boom Arm','USB Microphone','Docking Station'])[1 + (g % 16)]
      || ' ' ||
    (ARRAY['Pro','Lite','Max','Plus','Air','Std'])[1 + (g % 6)],
    1 + (g % 8),
    1 + (g % 8),
    'SKU-' || lpad(g::text, 4, '0'),
    cost,
    round((cost * (1.3 + random() * 0.5))::numeric, 2),
    (5 + floor(random() * 300))::int,
    timestamp '2023-06-01' + (random() * 400 || ' days')::interval
FROM gen;

-- ----------------------------------------------------- orders (400 rows) -----
INSERT INTO orders (customer_id, status, channel, created_at)
SELECT
    1 + floor(random() * 60)::int,
    (ARRAY['completed','completed','completed','completed',
           'shipped','processing','refunded','cancelled'])[1 + floor(random() * 8)::int],
    (ARRAY['web','web','mobile','partner'])[1 + floor(random() * 4)::int],
    timestamp '2024-01-01' + (random() * 550 || ' days')::interval
FROM generate_series(1, 400) AS g;

-- Each order gets 1–3 line items. product_id/quantity are computed per output
-- row (volatile random in the SELECT list), which — unlike a LIMIT inside an
-- uncorrelated LATERAL — is genuinely re-evaluated for every row.
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
SELECT ol.order_id,
       1 + floor(random() * 48)::int,   -- random product (48 products exist)
       1 + floor(random() * 4)::int,    -- quantity 1–4
       0                                -- unit_price backfilled just below
FROM (
    SELECT o.id AS order_id,
           generate_series(1, 1 + floor(random() * 3)::int)
    FROM orders o
) AS ol;

-- Snapshot each line's unit price from the product catalog.
UPDATE order_items oi
SET unit_price = p.price
FROM products p
WHERE p.id = oi.product_id;

-- Backfill each order's total from its line items.
UPDATE orders o
SET total = s.sum
FROM (
    SELECT order_id, SUM(quantity * unit_price) AS sum
    FROM order_items GROUP BY order_id
) AS s
WHERE o.id = s.order_id;

-- ------------------------------------------------------------- payments ------
INSERT INTO payments (order_id, method, amount, status, paid_at)
SELECT
    o.id,
    (ARRAY['card','card','paypal','bank_transfer','apple_pay'])[1 + floor(random() * 5)::int],
    o.total,
    CASE o.status
        WHEN 'refunded'  THEN 'refunded'
        WHEN 'cancelled' THEN 'failed'
        ELSE 'paid'
    END,
    o.created_at + (random() * 2 || ' hours')::interval
FROM orders o;

-- ------------------------------------------------------------ shipments ------
INSERT INTO shipments (order_id, carrier, status, shipped_at, delivered_at)
SELECT
    o.id,
    (ARRAY['DHL','FedEx','UPS','Royal Mail','GIG'])[1 + floor(random() * 5)::int],
    CASE o.status
        WHEN 'completed' THEN 'delivered'
        WHEN 'shipped'   THEN 'in_transit'
        ELSE 'pending'
    END,
    CASE WHEN o.status IN ('completed','shipped')
         THEN o.created_at + (random() * 2 || ' days')::interval END,
    CASE WHEN o.status = 'completed'
         THEN o.created_at + (2 + random() * 7 || ' days')::interval END
FROM orders o
WHERE o.status IN ('completed','shipped','processing');

-- -------------------------------------------------- reviews (250 rows) -------
INSERT INTO reviews (product_id, customer_id, rating, comment, created_at)
SELECT
    1 + floor(random() * 48)::int,
    1 + floor(random() * 60)::int,
    1 + floor(random() * 5)::int,
    (ARRAY['Great product','Works as expected','A bit disappointed','Excellent value',
           'Would buy again','Stopped working after a week','Fast shipping','Not as described'])[1 + floor(random() * 8)::int],
    timestamp '2024-02-01' + (random() * 500 || ' days')::interval
FROM generate_series(1, 250) AS g;

COMMIT;
