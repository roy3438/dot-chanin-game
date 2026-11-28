// DOT CHAIN – Multi‑Level Mission (update‑game mode)
// -------------------------------------------------------
// This script implements the full game logic for the three levels
// described in the test plan. It keeps the original storage schema
// (key: "dot-chain-v1") and adds the new mission handling, audio
// effects, UI updates and mute‑state persistence.

(() => {
  const STORAGE_KEY = "dot-chain-v1";
  const BOARD_SIZE = 6; // 6×6 board → 36 cells
  const COLORS = ["red", "blue", "yellow", "green"];

  // -----------------------------------------------------------------
  // State handling (load / save)
  // -----------------------------------------------------------------
  const defaultState = () => ({
    score: 0,
    best: 0,
    moves: 20,
    phase: "idle", // idle | playing | finished
    mission: null,
    missionProgress: null,
    board: Array(36).fill("red"), // will be shuffled on new game
    level: 1,
    unlocked: 1,
    mute: false,
  });

  let state = loadState();
  function loadState() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        // Merge saved state with defaults to guarantee all required fields exist
        return Object.assign({}, defaultState(), parsed);
      } catch (_) {}
    }
    return defaultState();
  }
  function saveState() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  // -----------------------------------------------------------------
  // UI references
  // -----------------------------------------------------------------
  const $score = document.getElementById("score");
  const $moves = document.getElementById("moves");
  const $level = document.getElementById("level-indicator");
  const $missionText = document.getElementById("mission-text");
  const $missionBonus = document.getElementById("mission-bonus");
  const $board = document.getElementById("board");
  const $pathLine = document.getElementById("path-line");
  const $result = document.getElementById("result");
  const $resultTitle = document.getElementById("result-title");
  const $finalScore = document.getElementById("final-score");
  const $restartBtn = document.getElementById("restart");
  const $nextLevelBtn = document.getElementById("next-level");
  const $newGameBtn = document.getElementById("new-game");
  const $muteBtn = document.getElementById("mute-btn");

  // -----------------------------------------------------------------
  // Audio (Web Audio API) – simple beep & pop sounds
  // -----------------------------------------------------------------
  const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const sounds = {
    connect: createOscillator(440, 0.05), // short beep when a line is drawn
    clear: createOscillator(220, 0.15),   // lower tone when dots are removed
    pop: createOscillator(660, 0.08),    // score pop sound
  };
  function createOscillator(freq, dur) {
    return () => {
      if (state.mute) return;
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.frequency.value = freq;
      osc.type = "sine";
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      gain.gain.setValueAtTime(0.001, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.2, audioCtx.currentTime + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + dur);
      osc.start();
      osc.stop(audioCtx.currentTime + dur);
    };
  }

  // -----------------------------------------------------------------
  // Board rendering
  // -----------------------------------------------------------------
  function renderBoard() {
    $board.innerHTML = "";
    state.board.forEach((color, idx) => {
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.dataset.pos = idx;
      cell.setAttribute("role", "gridcell");
      const dot = document.createElement("span");
      dot.className = `dot ${color}`;
      cell.appendChild(dot);
      $board.appendChild(cell);
    });
  }

  // -----------------------------------------------------------------
  // Mission generation per level
  // -----------------------------------------------------------------
  function generateMission() {
    const lvl = state.level;
    if (lvl === 1) {
      state.mission = null; // simple 2000‑point goal, no extra mission
    } else if (lvl === 2) {
      state.mission = { kind: "length", bonus: 200 };
      state.missionProgress = { longChain: false };
    } else if (lvl === 3) {
      state.mission = { kind: "color", color: "red", target: 6 };
      // also need blue 6, we treat it as a second sub‑mission
      state.missionProgress = { red: 0, blue: 0 };
    }
  }

  // -----------------------------------------------------------------
  // UI update helpers
  // -----------------------------------------------------------------
  function updateUI() {
    $score.textContent = state.score;
    $moves.textContent = state.moves;
    $level.textContent = `레벨 ${state.level}`;
    // mission UI
    if (!state.mission) {
      $missionText.textContent = "준비 중";
      $missionBonus.textContent = "보너스 +0점";
    } else if (state.mission.kind === "length") {
      $missionText.textContent = "연결 5점 이상 달성";
      $missionBonus.textContent = `보너스 +${state.mission.bonus}점`;
    } else if (state.mission.kind === "color") {
      $missionText.textContent = `${state.mission.color} 색 6개 제거`;
      $missionBonus.textContent = "보너스 +0점";
    }
    // mute button label
    $muteBtn.textContent = state.mute ? "음소거 켜짐" : "음소거 꺼짐";
  }

  // -----------------------------------------------------------------
  // Scoring & pop‑up
  // -----------------------------------------------------------------
  function addScore(delta, x, y) {
    state.score += delta;
    if (state.score > state.best) state.best = state.score;
    const popup = document.createElement("div");
    popup.className = "score-popup";
    popup.textContent = `+${delta}`;
    popup.style.left = `${x}px`;
    popup.style.top = `${y}px`;
    document.body.appendChild(popup);
    setTimeout(() => popup.remove(), 800);
    sounds.pop();
  }

  // -----------------------------------------------------------------
  // Game flow: start / new / finish
  // -----------------------------------------------------------------
function startNewGame() {
  // Preserve mute, best score and unlocked level from the previous session
  const prevMute = state ? state.mute : false;
  const prevBest = state ? state.best : 0;
  const prevUnlocked = state ? state.unlocked : 1;

  // Initialise a fresh state
  state = defaultState();
  state.mute = prevMute;
  state.best = prevBest;
  state.unlocked = prevUnlocked;
  state.level = 1;
  state.unlocked = Math.max(state.unlocked, 1);
  randomizeBoard();
  generateMission();
  state.phase = "playing";
  state.moves = 20;

  // Hide the result overlay before rendering the new board
  if (typeof $result !== 'undefined') $result.classList.add('hidden');

  saveState();
  renderBoard();
  updateUI();
}

  function randomizeBoard() {
    const colors = [];
    for (let i = 0; i < 36; i++) colors.push(COLORS[i % COLORS.length]);
    // simple shuffle
    for (let i = colors.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [colors[i], colors[j]] = [colors[j], colors[i]];
    }
    state.board = colors;
  }

  function finishGame(victory) {
    state.phase = victory ? "won" : "lost";
    const hasNextLevel = victory && state.level < 3;
    const preview = document.getElementById("next-mission");
    if (hasNextLevel) {
      state.unlocked = Math.max(state.unlocked, state.level + 1);
      const mission = state.level === 1
        ? "같은 색 점 5개 이상을 한 번에 연결하세요."
        : "빨강과 파랑 점을 각각 6개 이상 제거하세요.";
      preview.textContent = `레벨 ${state.level} 클리어 · 레벨 ${state.level + 1} 해금 · 다음 미션: 2,000점을 얻고 ${mission}`;
    }
    preview.hidden = !hasNextLevel;
    $nextLevelBtn.classList.toggle("hidden", !hasNextLevel);
    $resultTitle.textContent = victory ? (state.level === 3 ? "전체 클리어!" : "승리!") : "패배";
    $finalScore.textContent = state.score;
    $result.classList.remove("hidden");
    saveState();
  }

  // -----------------------------------------------------------------
  // Interaction – drag to connect dots
  // -----------------------------------------------------------------
  let selected = [];
  let pathPoints = [];

  function cellAt(pos) {
    return $board.querySelector(`[data-pos='${pos}']`);
  }

  function startSelection(e) {
    if (state.phase !== "playing") return;
    const cell = e.target.closest('.cell');
    if (!cell) return;
    const pos = Number(cell.dataset.pos);
    selected = [pos];
    pathPoints = [cell.offsetLeft + cell.offsetWidth / 2, cell.offsetTop + cell.offsetHeight / 2];
    cell.classList.add('selected');
    document.addEventListener('pointermove', moveSelection);
    document.addEventListener('pointerup', endSelection);
  }

  function moveSelection(e) {
    const elem = document.elementFromPoint(e.clientX, e.clientY);
    const cell = elem?.closest('.cell');
    if (!cell) return;
    const pos = Number(cell.dataset.pos);
    if (selected.includes(pos)) return;
    const lastPos = selected[selected.length - 1];
    const lastColor = state.board[lastPos];
    if (state.board[pos] !== lastColor) return; // only same‑color chain
    selected.push(pos);
    cell.classList.add('selected');
    pathPoints.push(cell.offsetLeft + cell.offsetWidth / 2, cell.offsetTop + cell.offsetHeight / 2);
    $pathLine.setAttribute('points', pathPoints.join(' '));
    sounds.connect();
  }

  function endSelection() {
    document.removeEventListener('pointermove', moveSelection);
    document.removeEventListener('pointerup', endSelection);

    if (selected.length < 2) {
      clearSelection();
      return;
    }

    const chainLen = selected.length;
const base = 10 * chainLen * chainLen;
addScore(base, 0, 0);
if (state.level === 1) {
  // Level 1: award base points and clear the chain
} else if (state.level === 2) {
  // Level 2: need a chain of 5+ at least once, then give bonus
  if (chainLen >= 5) {
    state.missionProgress.longChain = true;
    addScore(state.mission.bonus, 0, 0);
  }
} else if (state.level === 3) {
  // Level 3: increment red or blue count based on the colour of the first selected dot
  const firstColor = state.board[selected[0]];
  if (firstColor === 'red') {
    state.missionProgress.red = (state.missionProgress.red || 0) + chainLen;
  } else if (firstColor === 'blue') {
    state.missionProgress.blue = (state.missionProgress.blue || 0) + chainLen;
  }
}
    clearDots(selected);
    // Decrease move counter after any attempted chain
    state.moves--;

    // Win / lose logic
    if (state.level === 1 && state.score >= 2000) {
      finishGame(true);
    } else if (state.level === 2 && state.score >= 2000 && state.missionProgress.longChain) {
      finishGame(true);
    } else if (state.level === 3 && state.score >= 2000 && state.missionProgress.red >= 6 && state.missionProgress.blue >= 6) {
      finishGame(true);
    } else if (state.moves <= 0) {
      finishGame(false);
    } else {
      // Continue playing
      clearSelection();
      updateUI();
    }

    saveState();
  }

function clearDots(positions) {
  // Build a set for quick lookup of cleared positions
  const clearedSet = new Set(positions);
  // For each column, compact cells toward row index 5 (zero‑based)
  for (let col = 0; col < BOARD_SIZE; col++) {
    // Collect the column values bottom‑up
    const columnVals = [];
    for (let row = BOARD_SIZE - 1; row >= 0; row--) {
      const idx = row * BOARD_SIZE + col;
      if (!clearedSet.has(idx)) {
        columnVals.push(state.board[idx]);
      }
    }
    // Pad the top with new random colors to keep board full
    while (columnVals.length < BOARD_SIZE) {
      const newColor = COLORS[Math.floor(Math.random() * COLORS.length)];
      columnVals.push(newColor);
    }
    // Write back the compacted column, preserving order (bottom to top)
    for (let row = BOARD_SIZE - 1, i = 0; row >= 0; row--, i++) {
      const idx = row * BOARD_SIZE + col;
      state.board[idx] = columnVals[i];
    }
  }
  renderBoard();
  sounds.clear();
}

  function clearSelection() {
    selected.forEach(p => cellAt(p).classList.remove('selected'));
    selected = [];
    pathPoints = [];
    $pathLine.setAttribute('points', '');
  }

  // -----------------------------------------------------------------
  // Button handlers
  // -----------------------------------------------------------------
  $newGameBtn.addEventListener('click', startNewGame);
  $restartBtn.addEventListener('click', () => {
    // Restart current level: reset moves, clear mission progress, generate new board
    state.phase = "playing";
    state.moves = 20;
    // Preserve score, best, unlocked, mute, and level number
    state.mission = null;
    state.missionProgress = null;
    randomizeBoard();
    generateMission();
    clearSelection();
    $result.classList.add('hidden');
    updateUI();
    saveState();
  });

  $nextLevelBtn.addEventListener('click', () => {
    // Advance to next level only when a win has occurred
    if (state.phase !== 'won') return;
    if (state.level < 3) {
      state.level++;
      state.unlocked = Math.max(state.unlocked, state.level);
      state.phase = "playing";
      state.score = 0; // score resets for the new level
      state.moves = 20;
      state.mission = null;
      state.missionProgress = null;
      randomizeBoard();
      generateMission();
      clearSelection();
      $result.classList.add('hidden');
      $nextLevelBtn.classList.add('hidden');
      updateUI();
      saveState();
    }
  });

  // Ensure touch activation works for result buttons – pointerup fires immediately
  $restartBtn.addEventListener('pointerup', (e) => {
    if (e.pointerType === 'touch') $restartBtn.click();
  });
  $nextLevelBtn.addEventListener('pointerup', (e) => {
    if (e.pointerType === 'touch') $nextLevelBtn.click();
  });
  $muteBtn.addEventListener('click', () => {
    state.mute = !state.mute;
    $muteBtn.textContent = state.mute ? "음소거 켜짐" : "음소거 꺼짐";
    saveState();
  });

  // -----------------------------------------------------------------
  // Initialization
  // -----------------------------------------------------------------
  $board.addEventListener('pointerdown', startSelection);
  // Restore UI from saved state
  renderBoard();
  updateUI();
function restoreGame() {
  if (state.phase === "won" || state.phase === "lost") {
    // finishGame will set the proper title, show next‑level button if applicable and persist state
    finishGame(state.phase === "won");
  }
}

  restoreGame();
})();
