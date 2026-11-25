# Power BI – Aide-mémoire

## Connexion à PostgreSQL
1. **Accueil → Obtenir les données → Plus… → Base de données PostgreSQL**
2. Serveur : `localhost` · Base de données : `olist` · Mode : **Importer**
3. Identifiants : onglet **Base de données** → utilisateur `postgres` + ton mot de passe
4. Cocher **`vw_commandes`** et **`vw_articles`** → **Charger**
5. ⚠️ Power BI nomme les tables **`public vw_commandes`** et **`public vw_articles`** :
   double-clic sur chaque nom dans le panneau **Données** → renommer en **`vw_commandes`** et **`vw_articles`**
   (sinon les formules DAX ci-dessous ne trouvent pas les tables).

> Si un message parle de **chiffrement / certificat** : clique sur **OK** pour te connecter sans chiffrement
> (normal pour une base installée sur ton propre ordinateur).

## Modèle de données
`vw_commandes[order_id]` **1 ──── \*** `vw_articles[order_id]`
(vue **Modèle**, à gauche : vérifier que le trait relie bien les deux tables par `order_id`).

## Mesures DAX
Créer chaque mesure : clic droit sur la table **vw_commandes → Nouvelle mesure**, coller la formule, Entrée.

| Mesure | Formule DAX | Format |
|---|---|---|
| Nb commandes | `Nb commandes = CALCULATE(DISTINCTCOUNT(vw_commandes[order_id]), vw_commandes[commande_valide] = 1)` | Nombre entier |
| Chiffre d'affaires | `Chiffre d'affaires = CALCULATE(SUM(vw_commandes[chiffre_affaires]), vw_commandes[commande_valide] = 1)` | Devise, 0 décimale |
| Panier moyen | `Panier moyen = DIVIDE([Chiffre d'affaires], [Nb commandes])` | Devise, 2 décimales |
| Nb clients | `Nb clients = CALCULATE(DISTINCTCOUNT(vw_commandes[client_id]), vw_commandes[commande_valide] = 1)` | Nombre entier |
| Note moyenne | `Note moyenne = AVERAGE(vw_commandes[note])` | Décimal, 2 décimales |
| % avis négatifs | `% avis négatifs = AVERAGE(vw_commandes[avis_negatif])` | Pourcentage, 1 décimale |
| % retard | `% retard = AVERAGE(vw_commandes[en_retard])` | Pourcentage, 1 décimale |
| Délai moyen (j) | `Délai moyen (j) = AVERAGE(vw_commandes[delai_jours])` | Décimal, 1 décimale |

> 💡 `AVERAGE` ignore les cases vides : les commandes non livrées n'entrent pas dans le % de retard,
> et les commandes sans avis n'entrent pas dans la note moyenne.

## Pages du dashboard
1. **Vue d'ensemble** – KPI, évolution du CA, top catégories
2. **Logistique** – délais et retards par État, carte
3. **Satisfaction** – note selon le retard, catégories les plus mal notées
4. **Commandes à risque** – prédictions du modèle de Machine Learning

## Page 4 – Commandes à risque (prédictions du modèle)
1. Lancer `python src/scoring.py` (3 à 5 min) : crée la table **`predictions`** dans PostgreSQL.
2. Power BI : **Accueil → Obtenir les données → PostgreSQL** → `localhost` / `olist` → cocher **`predictions`** → **Charger**,
   puis renommer `public predictions` en **`predictions`**.
3. Vue **Modèle** : vérifier la relation `predictions[order_id]` **1 ──── 1** `vw_commandes[order_id]`
   (sinon, faire glisser `order_id` d'une table sur l'autre).

| Colonne de `predictions` | Signification |
|---|---|
| `proba_achat` | probabilité d'avis négatif estimée juste après l'achat (scénario A) |
| `proba_livraison` | probabilité d'avis négatif estimée à la livraison (scénario B) |
| `niveau_risque` | 1. Élevé (10 % les plus à risque) · 2. Moyen (20 % suivants) · 3. Faible |
| `avis_negatif` | ce qui s'est vraiment passé (1 = avis négatif) |

Mesures (clic droit sur **predictions → Nouvelle mesure**) :

| Mesure | Formule DAX | Format |
|---|---|---|
| Commandes à risque élevé | `Commandes à risque élevé = CALCULATE(COUNTROWS(predictions), predictions[niveau_risque] = "1. Élevé")` | Nombre entier |
| % mécontents réels | `% mécontents réels = AVERAGE(predictions[avis_negatif])` | Pourcentage, 1 décimale |
| Risque moyen | `Risque moyen = AVERAGE(predictions[proba_livraison])` | Pourcentage, 1 décimale |
