CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  country VARCHAR(8) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE products (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  category VARCHAR(50) NOT NULL,
  price DECIMAL(10,2) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  product_id INT NOT NULL,
  quantity INT NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  status VARCHAR(20) NOT NULL,
  created_at TIMESTAMP NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB;

INSERT INTO users (name, email, country) VALUES
  ('Alice Johnson','alice@example.com','US'),
  ('Bilal Ahmed','bilal@example.com','UK'),
  ('Chen Wei','chen@example.com','SG');

INSERT INTO products (name, category, price) VALUES
  ('Wireless Mouse','Accessories',25.00),
  ('27in Monitor','Displays',320.00),
  ('USB-C Hub','Accessories',45.00);

INSERT INTO orders (user_id, product_id, quantity, amount, status, created_at) VALUES
  (1,2,1,320.00,'completed','2024-01-08 10:15:00'),
  (2,1,2,50.00,'completed','2024-01-22 14:30:00'),
  (3,2,1,320.00,'completed','2024-02-05 09:00:00'),
  (1,3,3,135.00,'completed','2024-02-19 16:45:00'),
  (2,1,4,100.00,'completed','2024-03-18 08:05:00'),
  (3,2,2,640.00,'completed','2024-03-29 19:40:00');
