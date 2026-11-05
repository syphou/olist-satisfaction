-- =====================================================================
-- Étape 2 – Schéma relationnel de la base "olist"
-- Exécuté automatiquement par src/etl.py (on peut aussi le lancer dans pgAdmin).
-- Les tables sont supprimées puis recréées : le script est rejouable.
-- =====================================================================

DROP TABLE IF EXISTS order_reviews, order_payments, order_items, orders,
                     products, category_translation, sellers, customers,
                     geolocation, geolocation_zip CASCADE;

-- ---------- Tables de référence ----------

CREATE TABLE customers (
    customer_id              VARCHAR(32) PRIMARY KEY,   -- id d'un client POUR UNE commande
    customer_unique_id       VARCHAR(32) NOT NULL,      -- id réel de la personne (permet de suivre les clients fidèles)
    customer_zip_code_prefix CHAR(5),
    customer_city            TEXT,
    customer_state           CHAR(2)
);

CREATE TABLE sellers (
    seller_id              VARCHAR(32) PRIMARY KEY,
    seller_zip_code_prefix CHAR(5),
    seller_city            TEXT,
    seller_state           CHAR(2)
);

CREATE TABLE category_translation (
    product_category_name         TEXT PRIMARY KEY,
    product_category_name_english TEXT NOT NULL
);

CREATE TABLE products (
    product_id                 VARCHAR(32) PRIMARY KEY,
    product_category_name      TEXT REFERENCES category_translation (product_category_name),
    product_name_length        INT,     -- corrigé : "lenght" dans le CSV d'origine
    product_description_length INT,
    product_photos_qty         INT,
    product_weight_g           INT,
    product_length_cm          INT,
    product_height_cm          INT,
    product_width_cm           INT
);

-- ---------- Tables de faits ----------

CREATE TABLE orders (
    order_id                      VARCHAR(32) PRIMARY KEY,
    customer_id                   VARCHAR(32) NOT NULL REFERENCES customers (customer_id),
    order_status                  TEXT        NOT NULL,
    order_purchase_timestamp      TIMESTAMP   NOT NULL,
    order_approved_at             TIMESTAMP,
    order_delivered_carrier_date  TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP
);

CREATE TABLE order_items (
    order_id            VARCHAR(32)   NOT NULL REFERENCES orders (order_id),
    order_item_id       INT           NOT NULL,     -- n° de l'article dans la commande (1, 2, 3…)
    product_id          VARCHAR(32)   NOT NULL REFERENCES products (product_id),
    seller_id           VARCHAR(32)   NOT NULL REFERENCES sellers (seller_id),
    shipping_limit_date TIMESTAMP,
    price               NUMERIC(10,2) NOT NULL CHECK (price >= 0),
    freight_value       NUMERIC(10,2) NOT NULL CHECK (freight_value >= 0),
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE order_payments (
    order_id             VARCHAR(32)   NOT NULL REFERENCES orders (order_id),
    payment_sequential   INT           NOT NULL,    -- n° du paiement (une commande peut avoir plusieurs moyens)
    payment_type         TEXT,
    payment_installments INT,
    payment_value        NUMERIC(10,2) CHECK (payment_value >= 0),
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE order_reviews (
    review_id               VARCHAR(32) NOT NULL,
    order_id                VARCHAR(32) NOT NULL REFERENCES orders (order_id),
    review_score            SMALLINT    NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title    TEXT,
    review_comment_message  TEXT,
    review_creation_date    TIMESTAMP,
    review_answer_timestamp TIMESTAMP,
    PRIMARY KEY (review_id, order_id)   -- un même avis peut concerner plusieurs commandes
);

-- ---------- Géolocalisation ----------

-- Table brute (sans doublons exacts) : plusieurs points GPS par code postal
CREATE TABLE geolocation (
    geolocation_zip_code_prefix CHAR(5) NOT NULL,
    geolocation_lat             DOUBLE PRECISION,
    geolocation_lng             DOUBLE PRECISION,
    geolocation_city            TEXT,
    geolocation_state           CHAR(2)
);

-- Table agrégée : UN point par code postal (médiane) -> facile à joindre
CREATE TABLE geolocation_zip (
    zip_code_prefix CHAR(5) PRIMARY KEY,
    lat             DOUBLE PRECISION,
    lng             DOUBLE PRECISION,
    state           CHAR(2)
);

-- ---------- Index pour accélérer les jointures fréquentes ----------
CREATE INDEX idx_orders_customer      ON orders (customer_id);
CREATE INDEX idx_orders_purchase      ON orders (order_purchase_timestamp);
CREATE INDEX idx_items_product        ON order_items (product_id);
CREATE INDEX idx_items_seller         ON order_items (seller_id);
CREATE INDEX idx_reviews_order        ON order_reviews (order_id);
CREATE INDEX idx_customers_unique     ON customers (customer_unique_id);
CREATE INDEX idx_geolocation_zip      ON geolocation (geolocation_zip_code_prefix);
