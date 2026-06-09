from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room
import random, time, threading, math
from collections import deque

app = Flask(__name__)
app.config['SECRET_KEY'] = 'snake-battle-secret-2024'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ── Constants ────────────────────────────────────────────────────────────────
GRID_W          = 40
GRID_H          = 30
TICK_RATE       = 0.12
MAX_FOOD        = 8
MAX_PLAYERS     = 6
NUM_BOTS        = 5

BOT_NAMES = ['Viper', 'Cobra', 'Mamba', 'Python', 'Taipan']
COLORS    = ['#00ff88','#ff4466','#4488ff','#ffcc00','#ff8800','#cc44ff','#00ccff','#ff6699']

DIRS = [[1,0],[-1,0],[0,1],[0,-1]]

rooms   = {}   # room_id -> room dict
players = {}   # sid -> {room_id, player_id}

# ── Helpers ───────────────────────────────────────────────────────────────────
def all_body_cells(room):
    cells = set()
    for p in room['players'].values():
        cells.update(map(tuple, p['body']))
    return cells

def rand_pos(blocked=None):
    blocked = blocked or set()
    for _ in range(300):
        p = (random.randint(2, GRID_W-3), random.randint(2, GRID_H-3))
        if p not in blocked:
            return p
    return (1,1)

def spawn_food(room):
    blocked = all_body_cells(room)
    blocked.update(map(tuple, room['food']))
    while len(room['food']) < MAX_FOOD:
        room['food'].append(list(rand_pos(blocked)))

def init_player(pid, color_idx, name=None):
    x = random.randint(5, GRID_W-6)
    y = random.randint(5, GRID_H-6)
    return {
        'id': pid,
        'body': [[x,y],[x-1,y],[x-2,y]],
        'dir': [1,0], 'next_dir': [1,0],
        'color': COLORS[color_idx % len(COLORS)],
        'score': 0, 'alive': True,
        'name': name or f'Snake {pid[:4]}',
        'is_bot': False,
    }

def init_bot(bid, color_idx, name):
    p = init_player(bid, color_idx, name)
    p['is_bot'] = True
    p['personality'] = random.choice(['hunter', 'collector', 'aggressive'])
    p['think_timer'] = 0   # ticks before next decision
    return p

def make_room(room_id):
    return {
        'id': room_id,
        'players': {},
        'food': [],
        'running': False,
        'thread': None,
    }

def find_or_create_room():
    for rid, room in rooms.items():
        if len(room['players']) < MAX_PLAYERS and not room['running']:
            return rid
    rid = f'room_{int(time.time()*1000) % 99999}'
    rooms[rid] = make_room(rid)
    return rid

def human_players(room):
    return [p for p in room['players'].values() if not p['is_bot']]

def build_state(room):
    return {
        'players': {
            pid: {
                'body': p['body'], 'color': p['color'],
                'score': p['score'], 'alive': p['alive'],
                'name': p['name'], 'is_bot': p['is_bot'],
            } for pid, p in room['players'].items()
        },
        'food': room['food'],
        'grid': [GRID_W, GRID_H],
    }

# ── BFS pathfinding ──────────────────────────────────────────────────────────
def bfs_next_dir(start, goal, blocked, fallback_dir):
    """Return the first step direction from start toward goal, avoiding blocked."""
    sx, sy = start
    gx, gy = goal
    if [sx,sy] == [gx,gy]:
        return fallback_dir

    visited = {(sx,sy)}
    # queue: (x, y, first_dir_taken)
    q = deque()
    for d in DIRS:
        nx, ny = (sx+d[0])%GRID_W, (sy+d[1])%GRID_H
        if (nx,ny) not in blocked:
            q.append((nx, ny, d))
            visited.add((nx,ny))

    while q:
        cx, cy, first_dir = q.popleft()
        if (cx,cy) == (gx,gy):
            return first_dir
        for d in DIRS:
            nx, ny = (cx+d[0])%GRID_W, (cy+d[1])%GRID_H
            if (nx,ny) not in visited and (nx,ny) not in blocked:
                visited.add((nx,ny))
                q.append((nx, ny, first_dir))

    return None  # no path found

def manhattan(a, b):
    dx = abs(a[0]-b[0]); dy = abs(a[1]-b[1])
    return min(dx, GRID_W-dx) + min(dy, GRID_H-dy)

def safe_dirs(head, blocked):
    sx, sy = head
    safe = []
    for d in DIRS:
        nx, ny = (sx+d[0])%GRID_W, (sy+d[1])%GRID_H
        if (nx,ny) not in blocked:
            safe.append(d)
    return safe

def flood_fill_size(start, blocked):
    """Count reachable cells from start (to prefer open space)."""
    visited = {tuple(start)}
    q = deque([start])
    count = 0
    while q and count < 60:   # cap for speed
        cx, cy = q.popleft()
        count += 1
        for d in DIRS:
            nx, ny = (cx+d[0])%GRID_W, (cy+d[1])%GRID_H
            if (nx,ny) not in visited and (nx,ny) not in blocked:
                visited.add((nx,ny))
                q.append([nx,ny])
    return count

# ── AI decision making ────────────────────────────────────────────────────────
def bot_think(bot, room):
    """Compute next_dir for a bot based on its personality."""
    if not bot['alive']:
        return

    bot['think_timer'] = max(0, bot['think_timer'] - 1)

    head = bot['body'][0]
    cur_dir = bot['dir']

    # Build obstacle set: all bodies except bot's own tail (it will move)
    blocked = set()
    for p in room['players'].values():
        if p['alive']:
            tail_skip = 1 if not p['is_bot'] else 1
            cells = p['body'][:-tail_skip] if len(p['body']) > tail_skip else p['body']
            blocked.update(map(tuple, cells))

    # Remove own head from blocked so we can reason about moves
    blocked.discard(tuple(head))

    food_list  = room['food']
    humans     = [p for p in room['players'].values() if not p['is_bot'] and p['alive']]
    other_bots = [p for p in room['players'].values() if p['is_bot'] and p['alive'] and p['id'] != bot['id']]

    # ── Personality logic ────────────────────────────────────────────────────
    target = None

    if bot['personality'] == 'collector':
        # Pure food chaser — nearest food
        if food_list:
            target = min(food_list, key=lambda f: manhattan(head, f))

    elif bot['personality'] == 'hunter':
        # Chase nearest human; fall back to food
        if humans:
            nearest_human = min(humans, key=lambda h: manhattan(head, h['body'][0]))
            dist = manhattan(head, nearest_human['body'][0])
            if dist < 10:
                target = nearest_human['body'][0]
            else:
                if food_list:
                    target = min(food_list, key=lambda f: manhattan(head, f))
        else:
            if food_list:
                target = min(food_list, key=lambda f: manhattan(head, f))

    elif bot['personality'] == 'aggressive':
        # Try to cut off humans by targeting cells ahead of them
        if humans:
            best_human = min(humans, key=lambda h: manhattan(head, h['body'][0]))
            # Aim 3 cells ahead of human's head
            hh = best_human['body'][0]
            hd = best_human['dir']
            intercept = [(hh[0]+hd[0]*i)%GRID_W, (hh[1]+hd[1]*i)%GRID_H]
            for i in range(3, 0, -1):
                cand = [(hh[0]+hd[0]*i)%GRID_W, (hh[1]+hd[1]*i)%GRID_H]
                if tuple(cand) not in blocked:
                    intercept = cand
                    break
            target = intercept
        else:
            if food_list:
                target = min(food_list, key=lambda f: manhattan(head, f))

    # ── Path to target via BFS ───────────────────────────────────────────────
    chosen_dir = None
    if target:
        d = bfs_next_dir(head, target, blocked, cur_dir)
        if d:
            # Verify direction doesn't cause immediate 180
            if d[0] != -cur_dir[0] or d[1] != -cur_dir[1]:
                chosen_dir = d

    # ── Fallback: pick safest direction ─────────────────────────────────────
    if not chosen_dir:
        safe = safe_dirs(head, blocked)
        # Filter out 180
        safe = [d for d in safe if not (d[0]==-cur_dir[0] and d[1]==-cur_dir[1])]
        if not safe:
            safe = safe_dirs(head, blocked)  # allow 180 if truly trapped
        if safe:
            # Prefer direction with most open space (flood fill)
            def score_dir(d):
                nx = (head[0]+d[0])%GRID_W
                ny = (head[1]+d[1])%GRID_H
                return flood_fill_size([nx,ny], blocked)
            chosen_dir = max(safe, key=score_dir)
        else:
            chosen_dir = cur_dir   # no safe move, going to die anyway

    bot['next_dir'] = chosen_dir

# ── Tick ─────────────────────────────────────────────────────────────────────
def tick(room):
    spawn_food(room)

    # Run bot AI before moving
    for p in room['players'].values():
        if p['is_bot'] and p['alive']:
            bot_think(p, room)

    food_set   = set(map(tuple, room['food']))
    heads_next = {}

    for pid, p in room['players'].items():
        if not p['alive']:
            continue
        p['dir'] = p['next_dir'][:]
        head = [(p['body'][0][0]+p['dir'][0])%GRID_W,
                (p['body'][0][1]+p['dir'][1])%GRID_H]
        heads_next[pid] = head

    # All live body cells
    all_bodies = set()
    for p in room['players'].values():
        if p['alive']:
            all_bodies.update(map(tuple, p['body']))

    for pid, head in heads_next.items():
        p  = room['players'][pid]
        t  = tuple(head)
        body_check = set(map(tuple, p['body'][:-1]))
        others     = all_bodies - set(map(tuple, p['body']))
        if t in body_check or t in others:
            p['alive'] = False
            continue
        for pid2, head2 in heads_next.items():
            if pid2 != pid and head == head2:
                p['alive'] = False
                break

    for pid, head in heads_next.items():
        p = room['players'][pid]
        if not p['alive']:
            continue
        ate = tuple(head) in food_set
        p['body'].insert(0, head)
        if ate:
            p['score'] += 10
            room['food'] = [f for f in room['food'] if f != list(head)]
        else:
            p['body'].pop()

# ── Game loop ─────────────────────────────────────────────────────────────────
def game_loop(room_id):
    room = rooms.get(room_id)
    if not room:
        return

    for i in range(3, 0, -1):
        socketio.emit('countdown', {'count': i}, room=room_id)
        time.sleep(1)

    room['running'] = True
    socketio.emit('game_start', {}, room=room_id)

    while room['running'] and rooms.get(room_id):
        # Stop if no humans left
        if not human_players(room):
            room['running'] = False
            break

        tick(room)

        alive_all    = [p for p in room['players'].values() if p['alive']]
        alive_humans = [p for p in alive_all if not p['is_bot']]
        total        = len(room['players'])

        game_ended = False

        # Solo human + bots: end when human dies OR all bots dead
        if total > 1:
            alive_bots = [p for p in alive_all if p['is_bot']]
            # Human died
            if not alive_humans:
                winner = alive_bots[0] if alive_bots else None
                socketio.emit('game_over', {
                    'winner': winner['name'] if winner else 'Nobody',
                    'scores': {p['name']: p['score'] for p in room['players'].values()}
                }, room=room_id)
                game_ended = True
            # Only one snake alive total
            elif len(alive_all) <= 1:
                winner = alive_all[0] if alive_all else None
                socketio.emit('game_over', {
                    'winner': winner['name'] if winner else 'Nobody',
                    'scores': {p['name']: p['score'] for p in room['players'].values()}
                }, room=room_id)
                game_ended = True

        if game_ended:
            room['running'] = False
            # Remove bots so room is clean for restart
            for bid in [k for k,v in room['players'].items() if v['is_bot']]:
                del room['players'][bid]
            break

        socketio.emit('state', build_state(room), room=room_id)
        time.sleep(TICK_RATE)


def spawn_bots(room):
    """Add 5 AI bots to a room."""
    existing = len(room['players'])
    for i in range(NUM_BOTS):
        bid   = f'bot_{i}_{room["id"]}'
        cidx  = (existing + i) % len(COLORS)
        bot   = init_bot(bid, cidx, BOT_NAMES[i % len(BOT_NAMES)])
        room['players'][bid] = bot


# ── SocketIO events ───────────────────────────────────────────────────────────
@socketio.on('connect')
def on_connect():
    print(f'[+] {request.sid}')

@socketio.on('disconnect')
def on_disconnect():
    sid  = request.sid
    info = players.pop(sid, None)
    if not info:
        return
    room = rooms.get(info['room_id'])
    if room:
        room['players'].pop(info['player_id'], None)
        # Remove bots if no humans remain
        if not human_players(room):
            room['running'] = False
            for bid in [k for k,v in list(room['players'].items()) if v['is_bot']]:
                del room['players'][bid]
        socketio.emit('player_left', {'id': info['player_id']}, room=info['room_id'])
        if not room['players']:
            room['running'] = False
            rooms.pop(info['room_id'], None)
    print(f'[-] {sid}')

@socketio.on('join')
def on_join(data):
    sid  = request.sid
    name = (data.get('name') or 'Snake')[:16]
    rid  = find_or_create_room()
    room = rooms[rid]

    cidx   = len(room['players'])
    pid    = sid
    player = init_player(pid, cidx, name)
    room['players'][pid] = player
    players[sid] = {'room_id': rid, 'player_id': pid}

    join_room(rid)
    spawn_food(room)

    emit('joined', {
        'room_id': rid, 'player_id': pid,
        'color': player['color'],
        'grid': [GRID_W, GRID_H],
        'state': build_state(room),
    })

    num_humans = len(human_players(room))

    if num_humans == 1 and not room['running'] and room['thread'] is None:
        # Solo: spawn bots and start after short delay
        def solo_bot_start():
            time.sleep(2)
            r = rooms.get(rid)
            if r and not r['running'] and r['thread'] is None and human_players(r):
                spawn_bots(r)
                spawn_food(r)
                socketio.emit('bots_added', {'count': NUM_BOTS}, room=rid)
                tt = threading.Thread(target=game_loop, args=(rid,), daemon=True)
                r['thread'] = tt
                tt.start()
        threading.Thread(target=solo_bot_start, daemon=True).start()

    elif num_humans >= 2 and not room['running'] and room['thread'] is None:
        t = threading.Thread(target=game_loop, args=(rid,), daemon=True)
        room['thread'] = t
        t.start()

@socketio.on('dir')
def on_dir(data):
    sid  = request.sid
    info = players.get(sid)
    if not info:
        return
    room = rooms.get(info['room_id'])
    if not room:
        return
    p = room['players'].get(info['player_id'])
    if not p or not p['alive'] or p['is_bot']:
        return
    d = data.get('dir')
    if not d or len(d) != 2:
        return
    dx, dy  = int(d[0]), int(d[1])
    cur     = p['dir']
    if dx != -cur[0] or dy != -cur[1]:
        p['next_dir'] = [dx, dy]

@socketio.on('restart')
def on_restart(data):
    sid  = request.sid
    info = players.get(sid)
    if not info:
        return
    room = rooms.get(info['room_id'])
    if not room or room['running']:
        return

    # Keep only human players, reset them
    for bid in [k for k,v in list(room['players'].items()) if v['is_bot']]:
        del room['players'][bid]

    for i, pid in enumerate(list(room['players'])):
        old_name = room['players'][pid]['name']
        room['players'][pid] = init_player(pid, i, old_name)

    room['food']   = []
    room['thread'] = None
    spawn_food(room)

    # If solo, re-add bots
    if len(human_players(room)) == 1:
        spawn_bots(room)
        spawn_food(room)
        socketio.emit('bots_added', {'count': NUM_BOTS}, room=info['room_id'])

    t = threading.Thread(target=game_loop, args=(info['room_id'],), daemon=True)
    room['thread'] = t
    t.start()

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    print('🐍 Snake Battle (with AI Bots) — http://localhost:5000')
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)