-- =====================================================================
-- Étape 6 – Vues pour Power BI
-- Une "vue" est une requête enregistrée dans la base : Power BI la lit
-- comme une table, mais elle se recalcule toujours à partir des données.
--
-- À exécuter UNE fois dans pgAdmin (Query Tool sur la base "olist") :
-- tout sélectionner (Ctrl + A) puis F5.
--
-- Modèle de données dans Power BI :
--     vw_commandes (1 ligne par commande)  1 ──── *  vw_articles (1 ligne par article)
-- =====================================================================

DROP VIEW IF EXISTS vw_articles;
DROP VIEW IF EXISTS vw_commandes;

-- ---------------------------------------------------------------------
-- vw_commandes : la table centrale du dashboard
-- ---------------------------------------------------------------------
CREATE VIEW vw_commandes AS
WITH notes AS (
    SELECT order_id, AVG(review_score) AS note
    FROM order_reviews
    GROUP BY order_id
),
articles AS (
    SELECT order_id,
           COUNT(*)                  AS nb_articles,
           COUNT(DISTINCT seller_id) AS nb_vendeurs,
           SUM(price)                AS chiffre_affaires,
           SUM(freight_value)        AS frais_port
    FROM order_items
    GROUP BY order_id
),
categorie_principale AS (          -- catégorie de l'article le plus cher
    SELECT DISTINCT ON (i.order_id)
           i.order_id,
           COALESCE(t.product_category_name_english, 'inconnue') AS categorie_principale
    FROM order_items i
    JOIN products p ON p.product_id = i.product_id
    LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
    ORDER BY i.order_id, i.price DESC
)
SELECT o.order_id,
       o.order_purchase_timestamp::date                                     AS date_achat,
       DATE_TRUNC('month', o.order_purchase_timestamp)::date                AS mois_achat,
       o.order_status                                                       AS statut,
       CASE WHEN o.order_status IN ('canceled', 'unavailable') THEN 0 ELSE 1 END AS commande_valide,
       c.customer_unique_id                                                 AS client_id,
       c.customer_state                                                     AS etat_client,
       INITCAP(c.customer_city)                                             AS ville_client,
       g.lat                                                                AS lat_client,
       g.lng                                                                AS lng_client,
       COALESCE(a.nb_articles, 0)                                           AS nb_articles,
       COALESCE(a.nb_vendeurs, 0)                                           AS nb_vendeurs,
       COALESCE(a.chiffre_affaires, 0)                                      AS chiffre_affaires,
       COALESCE(a.frais_port, 0)                                            AS frais_port,
       cp.categorie_principale,
       -- Livraison (vide si la commande n'est pas livrée)
       CASE WHEN o.order_delivered_customer_date IS NOT NULL THEN 1 ELSE 0 END AS livree,
       o.order_estimated_delivery_date::date - o.order_purchase_timestamp::date      AS delai_promis_jours,
       o.order_delivered_customer_date::date - o.order_purchase_timestamp::date      AS delai_jours,
       o.order_delivered_customer_date::date - o.order_estimated_delivery_date::date AS ecart_jours,
       CASE WHEN o.order_delivered_customer_date IS NULL THEN NULL
            WHEN o.order_delivered_customer_date::date > o.order_estimated_delivery_date::date THEN 1
            ELSE 0 END                                                      AS en_retard,
       -- Satisfaction (vide si pas d'avis)
       ROUND(n.note, 2)                                                     AS note,
       CASE WHEN n.note IS NULL THEN NULL
            WHEN n.note <= 2 THEN 1 ELSE 0 END                              AS avis_negatif
FROM orders o
JOIN customers c                 ON c.customer_id = o.customer_id
LEFT JOIN geolocation_zip g      ON g.zip_code_prefix = c.customer_zip_code_prefix
LEFT JOIN articles a             ON a.order_id = o.order_id
LEFT JOIN categorie_principale cp ON cp.order_id = o.order_id
LEFT JOIN notes n                ON n.order_id = o.order_id;


-- ---------------------------------------------------------------------
-- vw_articles : le détail par article (catégories, vendeurs)
-- ---------------------------------------------------------------------
CREATE VIEW vw_articles AS
SELECT i.order_id,
       i.order_item_id,
       i.product_id,
       COALESCE(t.product_category_name_english, 'inconnue') AS categorie,
       i.seller_id                                            AS vendeur_id,
       s.seller_state                                         AS etat_vendeur,
       INITCAP(s.seller_city)                                 AS ville_vendeur,
       i.price                                                AS prix,
       i.freight_value                                        AS frais_port
FROM order_items i
JOIN products p                  ON p.product_id = i.product_id
LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
JOIN sellers s                   ON s.seller_id = i.seller_id;


-- ---------------------------------------------------------------------
-- Vérification : les chiffres doivent correspondre à tes analyses SQL
-- ---------------------------------------------------------------------
SELECT COUNT(*)                                        AS nb_commandes,
       ROUND(SUM(chiffre_affaires) FILTER (WHERE commande_valide = 1), 0) AS ca_total,
       ROUND(AVG(note), 2)                             AS note_moyenne,
       ROUND(100.0 * AVG(en_retard), 1)                AS pct_retard,
       ROUND(100.0 * AVG(avis_negatif), 1)             AS pct_avis_negatifs
FROM vw_commandes;
