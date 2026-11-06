-- =====================================================================
-- Étape 3 – Analyses SQL
-- =====================================================================

-- ---------------------------------------------------------------------
-- Analyse 1 : évolution des ventes mois par mois
-- Question : l'activité d'Olist grandit-elle ? Quels mois sont les plus forts ?
-- Constat : pic en novembre 2017 (Black Friday). 2016 et sept./oct. 2018 incomplets.
-- ---------------------------------------------------------------------
SELECT DATE_TRUNC('month', o.order_purchase_timestamp)::date AS mois,
       COUNT(DISTINCT o.order_id)   AS nb_commandes,
       ROUND(SUM(i.price), 0)       AS chiffre_affaires
FROM orders o
JOIN order_items i ON i.order_id = o.order_id
WHERE o.order_status NOT IN ('canceled', 'unavailable')
GROUP BY mois
ORDER BY mois;


-- ---------------------------------------------------------------------
-- Analyse 2 : croissance d'un mois sur l'autre (mois complets uniquement)
-- Question : de combien les ventes évoluent-elles chaque mois ?
-- Constat : forte croissance en 2017, pic au Black Friday puis retour
--           à la normale en décembre, stabilisation en 2018.
-- ---------------------------------------------------------------------
WITH ventes_mois AS (
    SELECT DATE_TRUNC('month', o.order_purchase_timestamp)::date AS mois,
           ROUND(SUM(i.price), 0) AS chiffre_affaires
    FROM orders o
    JOIN order_items i ON i.order_id = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= '2017-01-01'
      AND o.order_purchase_timestamp <  '2018-09-01'
    GROUP BY mois
)
SELECT mois,
       chiffre_affaires,
       LAG(chiffre_affaires) OVER (ORDER BY mois) AS ca_mois_precedent,
       ROUND(100.0 * (chiffre_affaires - LAG(chiffre_affaires) OVER (ORDER BY mois))
             / LAG(chiffre_affaires) OVER (ORDER BY mois), 1) AS evolution_pct
FROM ventes_mois
ORDER BY mois;


-- ---------------------------------------------------------------------
-- Analyse 3 : les catégories les plus mal notées (au moins 500 avis)
-- Question : quels types de produits déçoivent le plus les clients ?
-- Constat : (à compléter)
-- ---------------------------------------------------------------------
WITH commandes_categories AS (
    SELECT DISTINCT i.order_id,
           COALESCE(t.product_category_name_english, 'inconnue') AS categorie
    FROM order_items i
    JOIN products p ON p.product_id = i.product_id
    LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
)
SELECT cc.categorie,
       COUNT(*)                                                    AS nb_avis,
       ROUND(AVG(r.review_score), 2)                               AS note_moyenne,
       ROUND(100.0 * AVG(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END), 1) AS pct_avis_negatifs
FROM commandes_categories cc
JOIN order_reviews r ON r.order_id = cc.order_id
GROUP BY cc.categorie
HAVING COUNT(*) >= 500
ORDER BY note_moyenne ASC
LIMIT 10;