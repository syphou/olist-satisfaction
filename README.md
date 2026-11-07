# Olist – Analyse et prédiction de l'insatisfaction client

> Projet portfolio Data Analyst : de la donnée brute (9 tables) à la décision métier.

## Question métier
Qu'est-ce qui fait chuter les notes clients d'une marketplace e-commerce (retards, catégories, vendeurs, régions) ?
Peut-on **détecter à l'avance** les commandes à risque d'avis négatif ?

## Données
[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) — ~100 000 commandes (2016-2018), 9 fichiers CSV liés.

## Stack
Python (pandas, NumPy, scikit-learn) · PostgreSQL · SQL · Power BI · Git

## Structure du dépôt
```
olist-satisfaction/
├── data/
│   ├── raw/          # CSV Olist bruts (non versionnés)
│   └── processed/    # données nettoyées / exports
├── sql/              # schéma, vues analytiques, requêtes KPI
├── src/              # scripts Python (ETL, contrôles qualité)
├── notebooks/        # analyses statistiques et Machine Learning
├── powerbi/          # fichier .pbix du dashboard
├── docs/             # MCD / MLD, dictionnaire de données
└── reports/          # présentation finale, figures
```

## Feuille de route
- [x] 0. Environnement et récupération des données
- [ ] 1. Modélisation (MCD / MLD)
- [x] 2. ETL Python → PostgreSQL + contrôles qualité
- [x] 3. Analyses SQL (ventes, satisfaction, retards, fidélité)
- [ ] 4. Statistiques : impact du retard sur la note
- [ ] 5. Machine Learning : classification (avis négatif) + régression (délai)
- [ ] 6. Dashboard Power BI
- [ ] 7. Restitution et recommandations

## Lancer le projet
```bash
python -m venv .venv
# Windows : .venv\Scripts\activate   |   macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # (cp sous macOS/Linux) puis renseigner le mot de passe
python src/check_setup.py      # vérifie l'installation
python src/explore.py          # découverte des données
python src/etl.py              # charge les 9 tables dans PostgreSQL
```

## Premier constat
Une commande livrée **en retard** obtient une note moyenne de **2,27 / 5**, contre **4,29 / 5** à l'heure
(6 409 commandes en retard sur ~96 000 livrées, soit ~7 %).

## Principaux résultats SQL (`sql/03_analyses.sql`)
- **Panier moyen** : 137,75 R$ (hors frais de port).
- **Saisonnalité** : pic d'activité en novembre 2017 (Black Friday).
- **Retards** : concentrés dans les États éloignés des vendeurs, qui ont aussi les notes les plus basses.
- **Fidélité** : 97 % des clients ne commandent qu'une seule fois.
- **Retard et fidélité** : 3,07 % des clients livrés à l'heure reviennent contre 2,52 % en retard
  (khi-deux, p ≈ 0,015) : effet significatif mais modeste.

## Auteur
Syphax Yahiaoui — Data Analyst
