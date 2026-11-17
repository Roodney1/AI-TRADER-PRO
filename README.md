# AI TRADER PRO

Bot Telegram d'analyse technique manuelle, conçu pour afficher des analyses séparées sur demande.

## Configuration

- Plateforme visée : Pocket Option
- Expiration demandée : 10 secondes
- Source de données : BiQuote (API publique)
- Langue : français
- Seuil : 90/100 de score de confluence technique
- Indicateurs : RSI 14, EMA 9/21, MACD, bandes de Bollinger, Stochastique
- Marchés : EUR/USD, GBP/USD, USD/JPY, AUD/USD, Gold, GBP/JPY, EUR/JPY, USD/CAD

## Important avant toute utilisation

Le score sur 100 est un **score interne de confluence des règles**, pas une probabilité statistique de gain et jamais une garantie. Les indicateurs sont calculés sur des bougies BiQuote de 1 minute alors que l'expiration visée est de 10 secondes : ce décalage ne permet pas de prétendre que le bot prédit fiablement le mouvement des 10 prochaines secondes. Utiliser uniquement en compte démo et vérifier les prix avec Pocket Option. Le bot affiche « AUCUN SIGNAL » si les données sont manquantes, trop anciennes ou si le seuil n'est pas atteint.

BiQuote fournit des données de marché indicatives; elles peuvent différer des cotations et des prix d'exécution de Pocket Option.

## Lancer le bot

Python 3.11 ou plus récent :

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="votre_token"
python bot.py
```

Ne publiez jamais le token Telegram dans le dépôt ou dans une conversation. Configurez-le comme variable secrète `TELEGRAM_BOT_TOKEN` chez l'hébergeur choisi.

## Commandes Telegram

- `/start` ou `/help`
- `/eurusd`
- `/gbpusd`
- `/usdjpy`
- `/audusd`
- `/gold`
- `/gbpjpy`
- `/eurjpy`
- `/usdcad`
- `/signal`

Chaque commande lance une analyse individuelle. Le bot ne passe aucun ordre et n'est pas connecté au compte Pocket Option.

## Hébergement

GitHub conserve le code, mais ne fait pas tourner le bot 24 h/24 à lui seul. Il faut ensuite le déployer sur un hébergeur qui accepte un processus Python permanent (worker). Ajouter `TELEGRAM_BOT_TOKEN` dans les variables secrètes de cet hébergeur.

## Documentation des données

BiQuote API : https://biquote.io/docs/
