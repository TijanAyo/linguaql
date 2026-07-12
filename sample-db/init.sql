-- Sample source database for LinguaQL demos: a tiny e-commerce schema with
-- explicit foreign keys (orders -> users, orders -> products) so the
-- RelationshipGraph has real edges to resolve.

CREATE TABLE users (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT UNIQUE NOT NULL,
    country    TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE products (
    id       SERIAL PRIMARY KEY,
    name     TEXT NOT NULL,
    category TEXT NOT NULL,
    price    NUMERIC(10, 2) NOT NULL
);

CREATE TABLE orders (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users (id),
    product_id INTEGER NOT NULL REFERENCES products (id),
    quantity   INTEGER NOT NULL,
    amount     NUMERIC(10, 2) NOT NULL,
    status     TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

INSERT INTO users (name, email, country) VALUES
    ('Alice Johnson',  'alice@example.com',  'US'),
    ('Bilal Ahmed',    'bilal@example.com',  'UK'),
    ('Chen Wei',       'chen@example.com',   'SG'),
    ('Diana Prince',   'diana@example.com',  'US'),
    ('Erica Mensah',   'erica@example.com',  'GH');

INSERT INTO products (name, category, price) VALUES
    ('Wireless Mouse',   'Accessories', 25.00),
    ('Mechanical Keyboard', 'Accessories', 90.00),
    ('27in Monitor',     'Displays',    320.00),
    ('USB-C Hub',        'Accessories', 45.00),
    ('Laptop Stand',     'Accessories', 35.00);

-- Orders spread across 2024 months so "revenue by month" yields a time series.
INSERT INTO orders (user_id, product_id, quantity, amount, status, created_at) VALUES
    (1, 3, 1, 320.00, 'completed', '2024-01-08 10:15:00'),
    (2, 1, 2,  50.00, 'completed', '2024-01-22 14:30:00'),
    (3, 2, 1,  90.00, 'completed', '2024-02-05 09:00:00'),
    (1, 4, 3, 135.00, 'completed', '2024-02-19 16:45:00'),
    (4, 5, 1,  35.00, 'refunded',  '2024-02-27 11:10:00'),
    (5, 3, 1, 320.00, 'completed', '2024-03-03 13:20:00'),
    (2, 2, 1,  90.00, 'completed', '2024-03-18 08:05:00'),
    (3, 1, 4, 100.00, 'completed', '2024-03-29 19:40:00'),
    (1, 2, 1,  90.00, 'completed', '2024-04-11 12:00:00'),
    (4, 3, 2, 640.00, 'completed', '2024-04-25 15:30:00'),
    (5, 4, 1,  45.00, 'completed', '2024-05-06 10:50:00'),
    (2, 5, 2,  70.00, 'completed', '2024-05-20 17:15:00'),
    (3, 3, 1, 320.00, 'completed', '2024-06-02 09:25:00'),
    (1, 1, 1,  25.00, 'completed', '2024-06-17 14:05:00'),
    (4, 2, 1,  90.00, 'completed', '2024-06-28 20:10:00');
