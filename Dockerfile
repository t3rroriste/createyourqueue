# Même version de Python qu'en local (venv : Python 3.14)
FROM python:3.14-slim

# ffmpeg : lecture des annonces vocales (discord.FFmpegPCMAudio).
# Sans lui, le bot ne peut rien jouer dans un vocal.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Dépendances d'abord : cette couche n'est reconstruite que si requirements.txt change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Le code (.dockerignore exclut .env, venv/ et data/)
COPY . .

# data/ contient la configuration de chaque serveur. Sur l'hébergeur, monte un
# volume persistant sur /app/data : sans lui, tout est effacé à chaque
# redéploiement.

# Le bot principal seul. Pour les trois bots : CMD ["python", "bot.py"]
CMD ["python", "bot.py", "--bot", "main"]
