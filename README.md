# mallanet-discord-bots

Dos procesos, un repo:

| Entrypoint | Comando | App Discord | Qué hace |
|---|---|---|---|
| **onboard** | `python -m mallabot.onboard` | MallaOnboard (recomendado) | Botón Aplicar + modal KYC + aprobar/rechazar |
| **watch** | `python -m mallabot.watch` | MallaWatch | Joins/leaves, roles, bans/kicks → `#logs` |

VISOR (admin) no corre aquí.

## Setup rápido (local / VPS)

1. Crear **dos** aplicaciones en [Discord Developer Portal](https://discord.com/developers/applications):
   - **MallaOnboard** — Bot + Privileged Intent **Server Members**
   - **MallaWatch** — Bot + Privileged Intents **Server Members** (+ **Moderation** via scope)
2. Invitar:
   - Onboard: `applications.commands`, Manage Roles, Send Messages, Embed Links, Read History (en `#verificacion` y `#bot-admin`). Su rol debe estar **por encima** de `Pendiente` y `Verificado`.
   - Watch: Send Messages + Embed Links en `#logs`, View Audit Log.
3. `cp .env.example .env` y pega tokens + IDs (ya van los de Mallanet.org).
4. ```bash
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   python -m mallabot.onboard   # terminal 1
   python -m mallabot.watch     # terminal 2
   ```

## Modal KYC

1. ¿Cómo te presentas? *(req)*
2. ¿Qué haces? *(req)*
3. ¿Qué quieres aportar o qué idea tienes? *(req)*
4. Ciudad
5. Website, Instagram o LinkedIn *(req)*

Flujo: `#verificacion` → Aplicar → ficha en `#bot-admin` → Aprobar (rol **Verificado**, quita **Pendiente**) / Rechazar.

Aprobadores: roles en `APPROVER_ROLE_IDS` (por defecto Root + MallaNet).

## systemd (VPS, al final)

Ver `deploy/*.service`. Ejemplo:

```bash
sudo cp -r . /opt/mallanet-discord-bots
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl enable --now malla-onboard malla-watch
```

## Runbook corto

- Raid de spam: Automod nativo ya corta spam/menciones; Watch deja traza en `#logs`.
- Revisar cola KYC: canal `#bot-admin`.
- Re-publicar panel Aplicar: borrar el mensaje viejo del bot en `#verificacion` y reiniciar onboard.
