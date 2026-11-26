'use strict';
(() => {
  const SIDE = 6;
  const COUNT = SIDE * SIDE;
  const COLORS = ['red', 'blue', 'yellow', 'green'];
  const STORE = 'dot-chain-v1';
  const GOAL = 2000;
  const START_MOVES = 20;
  const boardNode = document.getElementById('board');
  const wrapNode = document.querySelector('.board-wrap');
  const pathNode = document.getElementById('path-line');
  const scoreNode = document.getElementById('score');
  const movesNode = document.getElementById('moves');
  const missionNode = document.getElementById('mission-text');
  const bonusNode = document.getElementById('mission-bonus');
  const statusNode = document.getElementById('status');
  const resultNode = document.getElementById('result');
  const resultTitleNode = document.getElementById('result-title');
  const finalScoreNode = document.getElementById('final-score');
  let state;
  let path = [];
  let activePointer = null;
  let busy = false;
  let session = 0;

  function randomColor() { return COLORS[Math.floor(Math.random() * COLORS.length)]; }
  function neighbors(pos) {
    const row = Math.floor(pos / SIDE);
    const col = pos % SIDE;
    const result = [];
    if (row > 0) result.push(pos - SIDE);
    if (row < SIDE - 1) result.push(pos + SIDE);
    if (col > 0) result.push(pos - 1);
    if (col < SIDE - 1) result.push(pos + 1);
    return result;
  }
  function hasPair(board) {
    return board.some((color, pos) => neighbors(pos).some(next => board[next] === color));
  }
  function longestAtLeast(board, needed, colorFilter = null) {
    function walk(pos, color, visited, length) {
      if (length >= needed) return true;
      for (const next of neighbors(pos)) {
        if (board[next] === color && !visited.has(next)) {
          visited.add(next);
          if (walk(next, color, visited, length + 1)) return true;
          visited.delete(next);
        }
      }
      return false;
    }
    for (let pos = 0; pos < COUNT; pos++) {
      if (colorFilter !== null && board[pos] !== colorFilter) continue;
      if (walk(pos, board[pos], new Set([pos]), 1)) return true;
    }
    return false;
  }
  function pickMission(board) {
    const options = [];
    for (const color of COLORS) {
      if (longestAtLeast(board, 3, color)) options.push({ kind: 'color', color, bonus: 150 });
    }
    if (longestAtLeast(board, 5)) {
      options.push({ kind: 'length', bonus: 200 });
      options.push({ kind: 'points', bonus: 250 });
    }
    return options.length ? options[Math.floor(Math.random() * options.length)] : null;
  }
  function missionText(mission) {
    if (!mission) return '일반 연결 턴 (미션 없음)';
    if (mission.kind === 'length') return '점 5개 이상 연결';
    if (mission.kind === 'points') return '기본 점수 200점 이상 획득';
    const names = { red: '빨강', blue: '파랑', yellow: '노랑', green: '초록' };
    return `${names[mission.color]} 점 3개 이상 연결`;
  }
  function earnedBonus(mission, length, color) {
    if (!mission) return 0;
    if (mission.kind === 'color') return length >= 3 && color === mission.color ? 150 : 0;
    if (mission.kind === 'length') return length >= 5 ? 200 : 0;
    return 10 * length * length >= 200 ? 250 : 0;
  }
  function shuffle(board) {
    const shuffled = board.slice();
    for (let pos = shuffled.length - 1; pos > 0; pos--) {
      const other = Math.floor(Math.random() * (pos + 1));
      [shuffled[pos], shuffled[other]] = [shuffled[other], shuffled[pos]];
    }
    return shuffled;
  }
  function ensurePlayable() {
    if (hasPair(state.board)) return false;
    const original = state.board;
    const counts = COLORS.map(color => original.filter(value => value === color).length);
    if (counts.every(count => count < 2)) {
      // With 36 cells and four colors this cannot occur, but never invent a new rule.
      statusNode.textContent = '연결 가능한 점을 구성할 수 없습니다. 기획 담당 확인이 필요합니다.';
      return false;
    }
    for (let attempt = 0; attempt < 200; attempt++) {
      const candidate = shuffle(original);
      if (hasPair(candidate)) { state.board = candidate; return true; }
    }
    // Deterministic fallback: put two existing dots of one color together.
    const color = COLORS[counts.findIndex(count => count >= 2)];
    const remainder = original.slice();
    const first = remainder.indexOf(color);
    remainder.splice(first, 1);
    const second = remainder.indexOf(color);
    remainder.splice(second, 1);
    state.board = [color, color, ...remainder];
    return true;
  }
  function validMission(mission) {
    if (mission === null) return true;
    if (!mission || !['color', 'length', 'points'].includes(mission.kind)) return false;
    if (mission.kind === 'color') return COLORS.includes(mission.color) && mission.bonus === 150;
    if (mission.kind === 'length') return mission.bonus === 200;
    return mission.bonus === 250;
  }
  function achieved(data) {
    if (data.score < GOAL) return false;
    if (data.level === 2) return data.missionProgress.longChain;
    if (data.level === 3) return data.missionProgress.red >= 6 && data.missionProgress.blue >= 6;
    return true;
  }
  function validState(data) {
    if (!data || !Array.isArray(data.board) || data.board.length !== COUNT || !data.board.every(value => COLORS.includes(value))) return false;
    if (!Number.isSafeInteger(data.score) || data.score < 0 || !Number.isInteger(data.moves) || data.moves < 0 || data.moves > START_MOVES) return false;
    if (!Number.isSafeInteger(data.best) || data.best < 0 || data.best < data.score) return false;
    if (!['playing', 'won', 'lost'].includes(data.phase) || !(validMission(data.mission) ||
        (data.level === 3 && data.mission?.kind === 'color' && data.mission.target === 6))) return false;
    if (data.phase === 'playing' && (achieved(data) || data.moves === 0)) return false;
    if (data.phase === 'won' && !achieved(data)) return false;
    if (data.phase === 'lost' && (data.moves !== 0 || achieved(data))) return false;
    if (data.phase === 'playing' && !hasPair(data.board)) return false;
    if (data.phase === 'playing' && data.level === 1 && data.mission !== null) {
      const mission = data.mission;
      if (mission.kind === 'color' && !longestAtLeast(data.board, 3, mission.color)) return false;
      if (mission.kind !== 'color' && !longestAtLeast(data.board, 5)) return false;
    }
    return true;
  }
  function readSave() {
    try {
      const raw = localStorage.getItem(STORE);
      if (!raw) return null;
      const data = JSON.parse(raw);
      data.level ??= 1;
      if (![1, 2, 3].includes(data.level)) return null;
      data.unlocked = Math.max(data.level, [1,2,3].includes(data.unlocked) ? data.unlocked : 1);
      data.mute = data.mute === true;
      const progress = data.missionProgress || {};
      const count = n => Number.isSafeInteger(n) && n >= 0 ? n : 0;
      data.missionProgress = {longChain: progress.longChain === true, red: count(progress.red), blue: count(progress.blue)};
      return validState(data) ? data : null;
    } catch (_) { return null; }
  }
  function save() {
    try { localStorage.setItem(STORE, JSON.stringify(state)); } catch (_) { /* Storage is optional. */ }
  }
  function startNew(level = 1) {
    session++;
    busy = false;
    activePointer = null;
    path = [];
    const oldBest = state && Number.isSafeInteger(state.best) ? state.best : 0;
    state = { level, unlocked: Math.max(level, state?.unlocked || 1), mute:state?.mute || false,
      missionProgress:{longChain:false, red:0, blue:0}, board: Array.from({ length: COUNT }, randomColor), score: 0, moves: START_MOVES, mission: null, best: oldBest, phase: 'playing' };
    const rearranged = ensurePlayable();
    state.mission = pickMission(state.board);
    statusNode.textContent = rearranged ? '연결 가능한 게임판으로 재배열했습니다.' : '';
    save();
    render();
  }
  function render() {
    const goals = ['2,000점', '2,000점 · 5개 이상 한 번 연결', '2,000점 · 빨강과 파랑 각각 6개 제거'];
    document.getElementById('level-indicator').textContent = '레벨 ' + state.level;
    const p = state.missionProgress;
    const progress = state.level === 2 ? (p.longChain ? ' (달성)' : ' (미달성)') :
      state.level === 3 ? ' (빨강 ' + p.red + ', 파랑 ' + p.blue + ')' : '';
    document.getElementById('level-goal').textContent = goals[state.level - 1] + progress;
    document.getElementById('preview').textContent = state.level < 3 ? '다음 미션 · ' + goals[state.level] : '마지막 레벨';
    document.getElementById('mute-btn').textContent = state.mute ? '음소거 켜짐' : '음소거 꺼짐';
    document.getElementById('next-level').hidden = state.phase !== 'won' || state.level >= 3;
    scoreNode.textContent = String(state.score);
    movesNode.textContent = String(state.moves);
    missionNode.textContent = missionText(state.mission);
    bonusNode.textContent = `보너스 +${state.mission?.bonus || 0}점`;
    boardNode.replaceChildren();
    state.board.forEach((color, pos) => {
      const cell = document.createElement('div');
      cell.className = 'cell';
      cell.dataset.pos = String(pos);
      cell.setAttribute('role', 'gridcell');
      cell.setAttribute('aria-label', `${Math.floor(pos / SIDE) + 1}행 ${pos % SIDE + 1}열 ${color}`);
      const dot = document.createElement('span');
      dot.className = `dot ${color}`;
      cell.appendChild(dot);
      boardNode.appendChild(cell);
    });
    drawPath();
    resultNode.classList.toggle('hidden', state.phase === 'playing');
    if (state.phase !== 'playing') {
      resultTitleNode.textContent = state.phase === 'won' ? (state.level === 3 ? '전체 클리어!' : '승리!') : '패배';
      finalScoreNode.textContent = String(state.score);
      document.getElementById('restart').focus();
    }
  }
  function drawPath() {
    const cells = boardNode.children;
    for (let pos = 0; pos < cells.length; pos++) cells[pos].classList.toggle('selected', path.includes(pos));
    const outer = wrapNode.getBoundingClientRect();
    const points = path.map(pos => {
      const rect = cells[pos].getBoundingClientRect();
      return `${rect.left + rect.width / 2 - outer.left},${rect.top + rect.height / 2 - outer.top}`;
    });
    pathNode.setAttribute('points', points.join(' '));
  }
  function locate(clientX, clientY) {
    const rect = wrapNode.getBoundingClientRect();
    if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) return null;
    const target = document.elementFromPoint(clientX, clientY);
    const cell = target && target.closest('.cell');
    if (!cell || !boardNode.contains(cell)) return null;
    return Number(cell.dataset.pos);
  }
  function extend(pos) {
    if (pos === null || pos === undefined) return;
    if (!path.length) { path = [pos]; drawPath(); return; }
    const last = path[path.length - 1];
    if (pos === last) return;
    if (!neighbors(last).includes(pos)) return;
    if (path.length >= 2 && pos === path[path.length - 2]) { path.pop(); drawPath(); return; }
    if (path.includes(pos) || state.board[pos] !== state.board[path[0]]) return;
    path.push(pos);
    tone(380);
    drawPath();
  }
  function cancelPath() { path = []; drawPath(); }
  function pause(duration) { return new Promise(resolve => setTimeout(resolve, duration)); }
  async function finishPath() {
    if (path.length < 2) { cancelPath(); return; }
    busy = true;
    const currentSession = session;
    const chosen = path.slice();
    const color = state.board[chosen[0]];
    const base = 10 * chosen.length * chosen.length;
    const bonus = earnedBonus(state.mission, chosen.length, color);
    cancelPath();
    chosen.forEach(pos => boardNode.children[pos].classList.add('removing'));
    await pause(190);
    if (session !== currentSession) return;
    const removed = new Set(chosen);
    const nextBoard = Array(COUNT);
    for (let col = 0; col < SIDE; col++) {
      const surviving = [];
      for (let row = SIDE - 1; row >= 0; row--) {
        const pos = row * SIDE + col;
        if (!removed.has(pos)) surviving.push(state.board[pos]);
      }
      while (surviving.length < SIDE) surviving.push(randomColor());
      for (let row = SIDE - 1, offset = 0; row >= 0; row--, offset++) nextBoard[row * SIDE + col] = surviving[offset];
    }
    state.board = nextBoard;
    if (state.level === 2 && chosen.length >= 5) state.missionProgress.longChain = true;
    if (state.level === 3 && (color === 'red' || color === 'blue')) state.missionProgress[color] += chosen.length;
    state.score += base + bonus;
    const popup = document.createElement('span');
    popup.className = 'score-pop';
    popup.textContent = '+' + (base + bonus);
    wrapNode.append(popup);
    setTimeout(() => popup.remove(), 550);
    tone(660);
    state.best = Math.max(state.best, state.score);
    state.moves--;
    if (achieved(state)) { state.phase = 'won'; state.unlocked = Math.max(state.unlocked, Math.min(3, state.level + 1)); }
    else if (state.moves === 0) state.phase = 'lost';
    else {
      const rearranged = ensurePlayable();
      statusNode.textContent = rearranged ? '연결 가능한 게임판으로 재배열했습니다.' : '';
      state.mission = pickMission(state.board);
    }
    save();
    busy = false;
    render();
  }
  boardNode.addEventListener('pointerdown', event => {
    if (busy || state.phase !== 'playing' || activePointer !== null || event.button !== 0) return;
    const pos = locate(event.clientX, event.clientY);
    if (pos === null) return;
    event.preventDefault();
    activePointer = event.pointerId;
    boardNode.setPointerCapture(event.pointerId);
    extend(pos);
  });
  boardNode.addEventListener('pointermove', event => {
    if (event.pointerId !== activePointer || busy) return;
    event.preventDefault();
    extend(locate(event.clientX, event.clientY));
  });
  boardNode.addEventListener('pointerup', event => {
    if (event.pointerId !== activePointer) return;
    event.preventDefault();
    const pos = locate(event.clientX, event.clientY);
    activePointer = null;
    if (boardNode.hasPointerCapture(event.pointerId)) boardNode.releasePointerCapture(event.pointerId);
    if (pos === null) { void finishPath(); return; }
    extend(pos);
    void finishPath();
  });
  boardNode.addEventListener('pointercancel', event => {
    if (event.pointerId === activePointer) { activePointer = null; cancelPath(); }
  });
  boardNode.addEventListener('lostpointercapture', () => {
    if (activePointer !== null) { activePointer = null; cancelPath(); }
  });
  window.addEventListener('resize', drawPath);
  let audio;
  function tone(hz) {
    if (state.mute) return;
    try {
      audio ||= new AudioContext();
      if (audio.state === 'suspended') audio.resume().catch(() => {});
      const oscillator = audio.createOscillator();
      const gain = audio.createGain();
      oscillator.frequency.value = hz;
      gain.gain.setValueAtTime(.035, audio.currentTime);
      gain.gain.exponentialRampToValueAtTime(.001, audio.currentTime + .08);
      oscillator.connect(gain).connect(audio.destination);
      oscillator.start();
      oscillator.stop(audio.currentTime + .09);
    } catch (_) { /* Audio is optional. */ }
  }
  document.getElementById('new-game').addEventListener('click', () => startNew());
  function resultButton(id, activate) {
    const button = document.getElementById(id);
    button.addEventListener('pointerup', event => {
      if (event.pointerType === 'touch' && button.contains(document.elementFromPoint(event.clientX, event.clientY))) activate();
    });
    button.addEventListener('click', activate);
  }
  resultButton('restart', () => { if (state.phase !== 'playing') startNew(state.level); });
  resultButton('next-level', () => { if (state.phase === 'won' && state.level < 3) startNew(state.level + 1); });
  document.getElementById('mute-btn').addEventListener('click', () => {
    state.mute = !state.mute;
    save();
    render();
  });
  state = readSave();
  if (state) render();
  else startNew();
})();
