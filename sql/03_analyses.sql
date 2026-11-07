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

-- ---------------------------------------------------------------------
-- Analyse 4 : délais et retards de livraison par État du client
-- Question : où les retards se produisent-ils ?
-- Constat : les États éloignés des vendeurs (nord / nord-est) ont plus de
--           retards et des notes plus basses ; SP est livré vite.
-- Reco : revoir les délais annoncés et la logistique pour ces régions.
-- ---------------------------------------------------------------------
WITH notes AS (
    SELECT order_id, AVG(review_score) AS note
    FROM order_reviews
    GROUP BY order_id
)
SELECT c.customer_state                                         AS etat,
       COUNT(*)                                                 AS nb_commandes,
       ROUND(AVG(o.order_delivered_customer_date::date
                 - o.order_purchase_timestamp::date), 1)        AS delai_moyen_jours,
       ROUND(100.0 * AVG(CASE WHEN o.order_delivered_customer_date::date
                                 > o.order_estimated_delivery_date::date
                              THEN 1 ELSE 0 END), 1)            AS pct_retard,
       ROUND(AVG(n.note), 2)                                    AS note_moyenne
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
LEFT JOIN notes n ON n.order_id = o.order_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY etat
ORDER BY pct_retard DESC;


-- ---------------------------------------------------------------------
-- Analyse 5 : fidélité – combien de clients commandent plusieurs fois ?
-- Constat : 96,96 % des clients n'ont passé qu'une seule commande.
--           La fidélité est quasi inexistante.
-- ---------------------------------------------------------------------
WITH commandes_par_client AS (
    SELECT c.customer_unique_id,
           COUNT(DISTINCT o.order_id) AS nb_commandes
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY c.customer_unique_id
)
SELECT CASE WHEN nb_commandes = 1 THEN '1 commande'
            WHEN nb_commandes = 2 THEN '2 commandes'
            ELSE '3 commandes ou plus' END            AS profil_client,
       COUNT(*)                                     AS nb_clients,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_clients
FROM commandes_par_client
GROUP BY profil_client
ORDER BY profil_client;


-- ---------------------------------------------------------------------
-- Analyse 6 : un retard à la 1re commande fait-il fuir le client ?
-- Constat : 3,07 % des clients livrés à l'heure reviennent, contre 2,52 %
--           des clients livrés en retard (86 946 vs 6 347 clients).
--           Test du khi-deux : p ≈ 0,015 < 0,05 -> écart significatif.
-- Conclusion : l'effet est réel mais modeste ; le retard n'est pas la
--              cause principale du manque de fidélité.
-- ---------------------------------------------------------------------
WITH commandes AS (
    SELECT c.customer_unique_id,
           o.order_delivered_customer_date::date
             > o.order_estimated_delivery_date::date                AS en_retard,
           ROW_NUMBER() OVER (PARTITION BY c.customer_unique_id
                              ORDER BY o.order_purchase_timestamp)  AS rang,
           COUNT(*)     OVER (PARTITION BY c.customer_unique_id)    AS nb_commandes
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
)
SELECT CASE WHEN en_retard THEN 'B - 1re commande en retard'
            ELSE 'A - 1re commande à l''heure' END                  AS premiere_experience,
       COUNT(*)                                                     AS nb_clients,
       ROUND(100.0 * AVG(CASE WHEN nb_commandes > 1 THEN 1 ELSE 0 END), 2) AS pct_clients_revenus
FROM commandes
WHERE rang = 1
  AND en_retard IS NOT NULL
GROUP BY premiere_experience
ORDER BY premiere_experience;
