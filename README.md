# 🐍 Snake Battle — Multiplayer Arena with AI Bots

Real-time multiplayer Snake game built with **Flask + Flask-SocketIO** on the backend and **HTML5 Canvas + Socket.IO** on the frontend. Features intelligent AI bots with pathfinding that auto-join when you play solo.

## Features

- 🤖 **5 AI Bots** auto-spawn when only 1 human player joins
- 🧠 **3 Bot personalities** — Collector, Hunter, Aggressive
- 🗺️ **BFS Pathfinding** — bots find shortest path to targets
- 🌊 **Flood fill** — bots avoid dead ends and trapped spaces
- 🔄 **Wrap-around walls** — exit one edge, enter the other
- 👥 Up to **6 human players** per room — auto-matched
- ⚡ Real-time game loop via WebSockets (~8 ticks/second)
- 💥 Collision detection — body, self, head-on crashes
- 🏆 Score system — +10 pts per food pellet eaten
- ⏱️ Countdown timer before each round
- 📱 Touch D-pad for mobile players

## Project Structure

```
snake-battle/
├── server.py               ← Flask + SocketIO game server + AI bot logic
├── requirements.txt        ← Python dependencies
├── README.md
├── templates/
│   └── index.html          ← Single-page app (CSS + JS all inline)
└── static/
    ├── css/style.css       ← (legacy, not used — styles are inline)
    └── js/game.js          ← (legacy, not used — JS is inline)
```

## Setup & Run

```powershell
# 1. Create virtual environment
python -m venv venv

# 2. Activate it (Windows PowerShell)
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the server
python server.py
```

Open **http://localhost:5000** in your browser.

> **Linux / Mac users:** use `source venv/bin/activate` in step 2.

## Controls

| Action | Keyboard | Mobile |
|--------|----------|--------|
| Move Up    | `↑` / `W` | D-pad ▲ |
| Move Down  | `↓` / `S` | D-pad ▼ |
| Move Left  | `←` / `A` | D-pad ◀ |
| Move Right | `→` / `D` | D-pad ▶ |

## Game Rules

1. Eat **yellow pellets** to grow and score points (+10 each).
2. Avoid running into **your own body** or **other snakes**.
3. Walls **wrap around** — no boundary deaths.
4. Last snake alive wins. In solo mode, survive all 5 bots.

## AI Bot System

When only **1 human** joins a room, 5 AI bots spawn automatically after a 2-second delay.

### Bot Personalities

| Personality | Behavior |
|-------------|----------|
| **Collector** | BFS pathfinds to the nearest food every tick |
| **Hunter** | Chases the nearest human if within 10 cells, else eats food |
| **Aggressive** | Projects 3 cells ahead of the human's path to intercept and cut off |

### Pathfinding Stack (per bot, per tick)

1. **BFS** toward target — shortest path through live grid avoiding all bodies
2. **Flood fill** fallback — if no path found, picks direction with most open space
3. **Safe direction** last resort — avoids 180° reversal, picks any non-lethal move

Bots are visually distinct: **orange glow**, **red pupils**, and a circuit mark on the head. They show a `BOT` tag in the scoreboard.

## Wall Behavior

By default walls **wrap around** (Pac-Man style). To make walls lethal, replace this in `server.py`:

```python
# Current (wrap-around)
head[0] %= GRID_W
head[1] %= GRID_H
```

```python
# Replace with (wall = death)
if head[0] < 0 or head[0] >= GRID_W or head[1] < 0 or head[1] >= GRID_H:
    p['alive'] = False
    continue
```

## Common Issues

| Problem | Fix |
|---------|-----|
| `python` not found | Try `python3` instead |
| `activate` script blocked | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| Port already in use | Change `port=5000` to `port=5001` in `server.py` |

## Optional Database Integration

### SQLite (simple, local)
```python
import sqlite3
conn = sqlite3.connect('scores.db')
conn.execute('CREATE TABLE IF NOT EXISTS scores (name TEXT, score INT, is_bot INT, ts DATETIME DEFAULT CURRENT_TIMESTAMP)')
# On game_over:
conn.execute('INSERT INTO scores VALUES (?,?,?)', (name, score, is_bot))
conn.commit()
```

### MongoDB (scalable, cloud-ready)
```bash
pip install pymongo
```
```python
from pymongo import MongoClient
client = MongoClient('mongodb://localhost:27017/')
db = client['snakebattle']
db.scores.insert_one({'name': name, 'score': score, 'is_bot': is_bot})
```

## Extending the Game

- **Bot difficulty** — reduce `TICK_RATE` or add reaction delay to `think_timer` for easier bots
- **More personalities** — add `'cautious'` (avoids players) or `'random'` for variety
- **Power-ups** — speed boost, invincibility, score multiplier food types
- **Private rooms** — let players share a room code instead of auto-matching
- **Leaderboard** — connect SQLite/MongoDB and expose a `/leaderboard` endpoint
