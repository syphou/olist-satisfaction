-- =====================================================================
-- Premières requêtes : vérifier le chargement et prendre la base en main
-- À lancer dans pgAdmin : clic droit sur la base "olist" > Query Tool,
-- sélectionner UNE requête, puis F5 (ou le bouton ▶).
-- =====================================================================

-- 1) Combien de lignes dans chaque table ?
SELECT 'customers' AS table_name, COUNT(*) AS nb_lignes FROM customers
UNION ALL SELECT 'orders',         COUNT(*) FROM orders
UNION ALL SELECT 'order_items',    COUNT(*) FROM order_items
UNION ALL SELECT 'order_payments', COUNT(*) FROM order_payments
UNION ALL SELECT 'order_reviews',  COUNT(*) FROM order_reviews
UNION ALL SELECT 'products',       COUNT(*) FROM products
UNION ALL SELECT 'sellers',        COUNT(*) FROM sellers;


-- 2) Répartition des commandes par statut
SELECT order_status,
       COUNT(*) AS nb_commandes,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pourcentage
FROM orders
GROUP BY order_status
ORDER BY nb_commandes DESC;


-- 3) Répartition des notes clients (1 à 5 étoiles)
SELECT review_score,
       COUNT(*) AS nb_avis,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pourcentage
FROM order_reviews
GROUP BY review_score
ORDER BY review_score;


-- 4) Le résultat de explore.py, mais en SQL : retard vs note moyenne
SELECT CASE WHEN o.order_delivered_customer_date::date > o.order_estimated_delivery_date::date
            THEN 'Livrée en retard' ELSE 'Livrée à l''heure' END AS livraison,
       COUNT(*)                         AS nb_commandes,
       ROUND(AVG(r.review_score), 2)    AS note_moyenne
FROM orders o
JOIN order_reviews r ON r.order_id = o.order_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY livraison;


-- 5) Les 10 catégories qui rapportent le plus (chiffre d'affaires)
SELECT COALESCE(t.product_category_name_english, 'inconnue') AS categorie,
       COUNT(*)                AS nb_articles_vendus,
       ROUND(SUM(i.price), 0)  AS chiffre_affaires
FROM order_items i
JOIN products p              ON p.product_id = i.product_id
LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
GROUP BY categorie
ORDER BY chiffre_affaires DESC
LIMIT 10;


-- =====================================================================
-- 🎯 À TOI DE JOUER (réponses à m'envoyer)
-- a) Combien de clients DIFFÉRENTS (customer_unique_id) ont commandé ?
-- b) Quels sont les 5 États (customer_state) avec le plus de commandes ?
-- c) Quel est le panier moyen (prix moyen d'une commande) ?
--    Indice : additionner d'abord price par order_id, puis faire la moyenne.
-- =====================================================================
