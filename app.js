(() => {
  const $ = (id) => document.getElementById(id);
  // Independent quizzes (tabs) sharing one engine. Each keeps its own stats, missed list and
  // options under its own storage prefix. `regions` is the place list; `all` names the everything button.
  const WORLD = { regions: REGIONS, all: "World", noun: "country", nouns: "countries", group: "continent" };
  const US = { regions: US_REGIONS, all: "All states", noun: "state", nouns: "states", group: "region" };
  const KINDS = {
    flags: {
      ...WORLD, one: "flag", many: "flags", prefix: "flagquiz",
      img: (code) => `flags/${code}.svg`,
    },
    shapes: {
      ...WORLD, one: "shape", many: "shapes", prefix: "shapequiz", shape: true,
      img: (code) => `shapes/${code}.svg`,
    },
    "state-flags": {
      ...US, one: "flag", many: "flags", prefix: "stateflagquiz",
      img: (code) => `stateflags/${code}.svg`,
    },
    map: {
      ...WORLD, one: "country", many: "countries", prefix: "mapquiz", map: "world",
      img: (code) => `flags/${code}.svg`,
    },
    "state-map": {
      ...US, one: "state", many: "states", prefix: "statemapquiz", map: "us",
      img: (code) => `stateflags/${code}.svg`,
    },
    connect: {
      ...WORLD, one: "country", many: "countries", prefix: "connectquiz",
      map: "world", connect: true,
      img: (code) => `flags/${code}.svg`,
    },
    "state-connect": {
      ...US, one: "state", many: "states", prefix: "stateconnectquiz",
      map: "us", connect: true,
      img: (code) => `stateflags/${code}.svg`,
    },
    "state-shapes": {
      ...US, one: "shape", many: "shapes", prefix: "stateshapequiz", shape: true,
      img: (code) => `stateshapes/${code}.svg`,
    },
  };
  // Each quiz is its own page (built by tools/build_pages.py), which says which one it is.
  const PAGES = {
    flags: "flag-quiz/", shapes: "country-shape-quiz/", map: "./", connect: "connect-countries/",
    "state-flags": "us-state-flags-quiz/", "state-shapes": "us-state-shapes-quiz/",
    "state-map": "us-states-map-quiz/", "state-connect": "connect-us-states/",
  };
  // Old links used #map etc. on a single page: send them to the quiz's own page.
  if (location.hash.slice(1) in PAGES) location.replace(PAGES[location.hash.slice(1)]);
  const kindFromPage = () => (document.body.dataset.kind in KINDS ? document.body.dataset.kind : "map");
  let K = KINDS[kindFromPage()];
  const key = (name) => `${K.prefix}.${name}`;
  const cap = (w) => w[0].toUpperCase() + w.slice(1);
  const REVEAL_MS = 1600;
  // In weighted mode a skip or wrong guess counts as an answer that took this long.
  const MISS_PENALTY_S = 5;
  // Weighted mode only looks at this many of a flag's most recent showings.
  const RECENT_N = 5;
  // Heatmap bins (seconds, last-5 average): up to 2s is lightest green, over 8s is darkest.
  const HEAT_BINS = [2, 3.5, 5, 8];

  // ---- Place data (countries or US states, depending on the tab; rebuilt by loadKind) ----
  let COUNTRIES = {}; // code -> { code, name, region, answers:Set, keys:[] }
  let ALPHABETICAL = [];
  function buildPlaces(regions) {
    COUNTRIES = {};
    for (const [region, list] of Object.entries(regions)) {
      for (const [code, name, ...aliases] of list) {
        const all = [name, ...aliases];
        COUNTRIES[code] = {
          code, name, region,
          answers: new Set(all.map(normalize)),
          // Dropdown search matches any of these (name and aliases) containing the typed text.
          keys: all.map(searchKey),
        };
      }
    }
    ALPHABETICAL = Object.values(COUNTRIES).sort((a, b) => a.name.localeCompare(b.name));
  }

  // For dropdown search: like normalize() but keeps "and"/"the"/"of", so typing "and" finds Andorra.
  function searchKey(s) {
    return s
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/&/g, "and")
      .replace(/\bsaint\b/g, "st")
      .replace(/[^a-z0-9]/g, "");
  }

  function normalize(s) {
    return s
      .normalize("NFD").replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/\bsaint\b/g, "st")
      .replace(/\b(the|and|of)\b/g, "")
      .replace(/[^a-z0-9]/g, "");
  }

  const flagUrl = (code) => K.img(code);

  function shuffle(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function fmtSecs(ms) {
    if (ms == null) return "—";
    const s = ms / 1000;
    return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
  }
  // Speed-run clock: m:ss.cc
  function fmtRun(ms) {
    const cs = Math.floor(ms / 10);
    return `${Math.floor(cs / 6000)}:${String(Math.floor(cs / 100) % 60).padStart(2, "0")}.${String(cs % 100).padStart(2, "0")}`;
  }
  function fmtWhen(at) {
    const d = new Date(at);
    const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(at).setHours(0, 0, 0, 0)) / 86400000);
    const time = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    if (days === 0) return `today ${time}`;
    if (days === 1) return `yesterday ${time}`;
    if (days < 7) return `${days} days ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }
  function fmtClock(ms) {
    const s = Math.floor(ms / 1000);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }
  const fmtPct = (p) => (p >= 0.1 ? `${(p * 100).toFixed(0)}%` : `${(p * 100).toFixed(1)}%`);

  // ---- Persistence (best effort; the app works without storage) ----
  function load(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
  }
  // Per-tab state, (re)loaded by loadKind().
  let bank, stats, opts, records;
  // records[region label] = { ms, at } — best speed-run time for each full region (World or a continent).
  const saveRecords = () => save(key("records"), records);
  // runs = every completed speed run, oldest first: { label, ms, at, prevMs (best before this run, if ranked) }
  let runs;
  const saveRuns = () => save(key("runs"), runs);
  const isRanked = (label) => label === K.all || label in K.regions;
  // stats[code] = { c: times correct, m: times missed, t: total ms to correct, best: fastest ms,
  //                 r: ms for each of the last RECENT_N showings (a miss counts as at least MISS_PENALTY_S) }
  const saveBank = () => save(key("missed"), [...bank]);
  const saveStats = () => save(key("stats"), stats);
  const statFor = (code) => (stats[code] ??= { c: 0, m: 0, t: 0, best: null });
  const avgMs = (s) => (s && s.c ? s.t / s.c : null);
  const recentMs = (s) => (s?.r?.length ? s.r.reduce((a, b) => a + b, 0) / s.r.length : null);
  function pushRecent(code, ms) {
    const s = statFor(code);
    s.r = [...(s.r || []), ms].slice(-RECENT_N);
    // Weighted mode and the heatmap only use this session's history.
    if (session) session.recent[code] = [...(session.recent[code] || []), ms].slice(-RECENT_N);
  }

  // ---- Options ----
  function loadKind() {
    K = KINDS[kindFromPage()];
    buildPlaces(K.regions);
    bank = new Set(load(key("missed"), []));
    stats = load(key("stats"), {});
    records = load(key("records"), {});
    runs = load(key("runs"), []);
    opts = {
      requeue: true, infinite: false, weighted: false, speedrun: false, temp: 2,
      answer: "dropdown", layout: "single", rotate: "none", spin: 90, borders: "shown", highlight: true,
      ...load(key("options"), {}),
    };
    for (const name of ["answer", "layout", "rotate", "borders"]) {
      document.querySelector(`input[name=${name}][value=${opts[name]}]`).checked = true;
    }
    $("opt-highlight").checked = opts.highlight;
    $("opt-spin").value = opts.spin;
    $("opt-speedrun").checked = opts.speedrun;
    $("opt-requeue").checked = opts.requeue;
    $("opt-infinite").checked = opts.infinite;
    $("opt-weighted").checked = opts.weighted;
    $("opt-temp").value = opts.temp;
    syncOptions();
    // Wording and tab highlight
    document.querySelectorAll(".n-one").forEach((el) => { el.textContent = K.one; });
    document.querySelectorAll(".n-many").forEach((el) => { el.textContent = K.many; });
    document.querySelectorAll(".n-Many").forEach((el) => { el.textContent = cap(K.many); });
    $("flag").alt = `${cap(K.one)} to guess`;
    $("guess").placeholder = `Type the ${K.noun}…`;
    $("guess").setAttribute("aria-label", `${cap(K.noun)} name`);
    $("stats-name-th").textContent = cap(K.noun);
    for (const a of document.querySelectorAll(".tabs a")) {
      a.classList.toggle("active", a.dataset.kind === kindFromPage());
      if (a.classList.contains("active")) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    }
  }

  function syncOptions() {
    opts.requeue = $("opt-requeue").checked;
    opts.infinite = $("opt-infinite").checked;
    opts.weighted = $("opt-weighted").checked;
    opts.speedrun = $("opt-speedrun").checked;
    opts.temp = Number($("opt-temp").value);
    for (const name of ["answer", "layout", "rotate", "borders"]) {
      opts[name] = document.querySelector(`input[name=${name}]:checked`).value;
    }
    opts.highlight = $("opt-highlight").checked;
    opts.spin = Number($("opt-spin").value);
    save(key("options"), opts);
    $("spin-value").textContent = `${opts.spin}°/s`;
    // Rotation only applies to shapes.
    $("rotate-row").hidden = !K.shape;
    $("spin-row").hidden = !K.shape || opts.rotate !== "spin";
    // Map quizzes are answered by clicking, so answer style and layout don't apply.
    $("answer-row").hidden = $("layout-row").hidden = !!K.map;
    $("borders-row").hidden = !K.map;
    $("highlight-label").hidden = !K.map || !!K.connect;
    // Connect is its own game: none of the round options, records or per-place stats apply.
    for (const id of ["opt-speedrun", "opt-requeue", "opt-infinite", "opt-weighted"]) {
      $(id).closest(".option").hidden = !!K.connect;
    }
    $("records").hidden = $("stats-btn").hidden = !!K.connect;
    const grid = !K.map && opts.layout === "grid";
    $("temp-value").textContent = `${opts.temp.toFixed(1)}s`;
    $("temp-row").hidden = !opts.weighted || opts.speedrun || !!K.connect;
    // Weighted mode brings slow/missed flags back by itself; a speed run is one straight pass with no misses.
    // A grid shows everything at once, so the round options don't apply either.
    const off = {
      "opt-requeue": opts.weighted || opts.speedrun || grid,
      "opt-infinite": opts.speedrun || grid,
      "opt-weighted": opts.speedrun || grid,
    };
    for (const [id, disabled] of Object.entries(off)) {
      $(id).disabled = disabled;
      $(id).closest(".option").classList.toggle("disabled", disabled);
    }
    renderRecords();
  }

  // Speed-run records and runs are kept per variant, since e.g. multiple choice is much quicker than typing.
  function variantTag(o = opts) {
    if (K.map) return o.borders === "hidden" ? "borderless" : "";
    const parts = [];
    if (o.layout === "grid") parts.push("grid");
    if (o.answer === "mc") parts.push("multiple choice");
    if (o.answer === "type") parts.push("typed");
    if (K.shape && o.rotate !== "none") {
      parts.push({ right: "90° steps", any: "any angle", spin: "spinning" }[o.rotate]);
    }
    return parts.join(" · ");
  }
  const recKey = (label, tag) => (tag ? `${label} · ${tag}` : label);

  // ---- Weighted (softmax) selection ----
  // Weighted mode only uses timings from the current session: a flag's score is the average of its
  // last RECENT_N showings this session, where a showing with a miss counts as at least MISS_PENALTY_S.
  function sessionScoreSecs(code) {
    const r = session?.recent[code];
    return r?.length ? r.reduce((a, b) => a + b, 0) / r.length / 1000 : null;
  }

  // All-time version for the stats screen: last RECENT_N showings across every session. Stats saved
  // before recent history existed fall back to the all-time average until the flag is played again.
  function scoreSecs(code) {
    const s = stats[code];
    const recent = recentMs(s);
    if (recent != null) return recent / 1000;
    if (!s || s.c + s.m === 0) return null;
    return (s.t / 1000 + s.m * MISS_PENALTY_S) / (s.c + s.m);
  }

  // Probability of each code in `pool`: softmax(score / temperature), with a strict floor of
  // 1 / (2 × pool size) applied by water-filling: floored flags get exactly the floor, and the rest
  // share what's left in proportion to their softmax weights. Repeats until nothing new drops below
  // the floor (the floors use at most half the mass, so this always succeeds).
  // Only called once every flag in `pool` has been played this session.
  function probabilities(pool, temp = opts.temp) {
    const scores = pool.map(sessionScoreSecs);
    const top = Math.max(...scores);
    const w = scores.map((x) => Math.exp((x - top) / temp));

    const floor = 1 / (2 * pool.length);
    const floored = new Set();
    let p;
    for (;;) {
      const remaining = 1 - floored.size * floor;
      let freeSum = 0;
      w.forEach((x, i) => { if (!floored.has(i)) freeSum += x; });
      p = w.map((x, i) => (floored.has(i) ? floor : (remaining * x) / freeSum));
      const before = floored.size;
      p.forEach((x, i) => { if (!floored.has(i) && x < floor) floored.add(i); });
      if (floored.size === before) break;
    }
    return new Map(pool.map((code, i) => [code, p[i]]));
  }

  const unseenIn = (pool) => pool.filter((code) => !session.seen.has(code));

  // First pass: every flag in the session is shown once, in random order, before any repeats.
  // After that, picks follow the probabilities, computed over the whole pool (so the floor uses the
  // full flag count) with the flag just shown excluded so it can't repeat back to back.
  function sampleWeighted(pool, exclude) {
    const unseen = unseenIn(pool);
    if (unseen.length) return unseen[Math.floor(Math.random() * unseen.length)];
    const probs = probabilities(pool);
    if (pool.length > 1) probs.delete(exclude);
    let total = 0;
    for (const p of probs.values()) total += p;
    let r = Math.random() * total;
    for (const [code, p] of probs) {
      if ((r -= p) <= 0) return code;
    }
    return [...probs.keys()].pop();
  }

  // ---- Screens ----
  function show(id) {
    for (const s of document.querySelectorAll(".screen")) s.hidden = s.id !== id;
  }

  function renderHome() {
    session = null;
    const list = $("region-list");
    list.innerHTML = "";
    list.append(regionButton(K.all, Object.keys(COUNTRIES), "world"));
    for (const [region, entries] of Object.entries(K.regions)) {
      list.append(regionButton(region, entries.map((e) => e[0])));
    }
    const pb = $("practice-btn");
    pb.hidden = bank.size === 0;
    pb.textContent = `Practice my missed ${K.many} (${bank.size})`;
    renderRecords();
    show("home");
  }

  function regionButton(label, codes, cls) {
    const b = document.createElement("button");
    if (cls) b.className = cls;
    if (K.connect) {
      const n = connectPairs(codes).length;
      b.innerHTML = `<strong>${label}</strong><span>${n ? `${n} puzzles` : "no land routes"}</span>`;
      b.disabled = !n;
      b.onclick = () => startConnect(label, codes);
      return b;
    }
    b.innerHTML = `<strong>${label}</strong><span>${codes.length} ${K.many}</span>`;
    b.onclick = () => startSession(label, codes);
    return b;
  }

  // ---- Correct-answer feedback: sound, confetti, streaks ----
  // Sounds are synthesised with Web Audio, so there's nothing to load and no delay. Every correct
  // answer plays the same chime; streaks and speed only change the visuals.
  let soundOn = load("quiz.sound", true);
  let audio = null;
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

  function audioReady() {
    if (!soundOn) return false;
    try { audio ??= new AudioContext(); } catch { return false; }
    if (audio.state === "suspended") audio.resume();
    return true;
  }
  function tone(hz, at, dur, { type = "triangle", vol = 0.16, slideTo } = {}) {
    const t = audio.currentTime + at;
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(hz, t);
    if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, t + dur);
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(vol, t + 0.006);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(gain).connect(audio.destination);
    osc.start(t);
    osc.stop(t + dur + 0.02);
  }

  function playCorrect() {
    if (!audioReady()) return;
    tone(523.25, 0, 0.12);       // C5
    tone(659.25, 0.07, 0.28);    // E5
  }
  function playWrong() {
    if (audioReady()) tone(180, 0, 0.16, { type: "sine", vol: 0.14, slideTo: 110 });
  }

  // Restart a one-shot CSS animation class on an element.
  function replay(el, cls) {
    el.classList.remove(cls);
    void el.offsetWidth;
    el.classList.add(cls);
  }

  const CONFETTI = ["#22c55e", "#facc15", "#3b82f6", "#ec4899", "#f97316", "#a855f7"];
  function confetti(count, from = document.querySelector(".flag-wrap")) {
    if (reducedMotion.matches || !count) return;
    // Burst from `from`, or from the top third of the window when it isn't on screen.
    const fw = from.getBoundingClientRect();
    const r = fw.width ? fw : { left: 0, top: 0, width: innerWidth, height: innerHeight * 0.66 };
    for (let i = 0; i < count; i++) {
      const p = document.createElement("span");
      p.className = "confetti";
      const angle = Math.random() * Math.PI * 2;
      const dist = 90 + Math.random() * Math.min(r.width, r.height) * 0.6;
      p.style.left = `${r.left + r.width / 2}px`;
      p.style.top = `${r.top + r.height / 2}px`;
      p.style.background = CONFETTI[i % CONFETTI.length];
      p.style.setProperty("--dx", `${Math.cos(angle) * dist}px`);
      p.style.setProperty("--dy", `${Math.sin(angle) * dist}px`);
      p.style.setProperty("--rot", `${Math.random() * 720 - 360}deg`);
      p.addEventListener("animationend", () => p.remove());
      document.body.append(p);
    }
  }

  // tier: "retry" (right after a miss), "ok", "fast" (under the lightest heatmap bin), "big" (milestone or personal best)
  function celebrate(tier) {
    playCorrect();
    const click = session.answer === "click";
    // The map only gets the soft glow: scaling it would redraw the whole map every frame.
    replay(click ? $("map-wrap") : $("flag-wrap"), tier === "retry" || click ? "glow-soft" : "glow");
    replay($("reveal"), "pop");
    // On a map the burst comes from the place you clicked.
    confetti({ retry: 0, ok: 10, fast: 22, big: 40 }[tier], click && mapView.hitEl ? mapView.hitEl : undefined);
    updateStreak(true);
  }

  function updateStreak(bump) {
    const el = $("hud-streak");
    const n = session?.streak || 0;
    el.textContent = n >= 3 ? `🔥 ${n}` : "";
    if (bump && n >= 3) replay(el, "bump");
  }

  function renderSoundBtn() {
    const b = $("sound-btn");
    b.textContent = soundOn ? "🔊 Sound" : "🔇 Muted";
    b.setAttribute("aria-pressed", String(soundOn));
  }

  // ---- Session (a run of one or more rounds) & round state ----
  let session = null;
  let round = null;
  let timerId = null;

  function startSession(label, codes) {
    // Map data is loaded the first time it's needed, so the clock doesn't start before the map shows.
    if (K.map && !window.MAPS?.[K.map]) {
      loadMap(K.map).then(() => startSession(label, codes), () => alert("Couldn't load the map."));
      return;
    }
    syncOptions();
    session = {
      label,
      codes: codes.slice(),
      speedrun: opts.speedrun,
      grid: !K.map && opts.layout === "grid",
      answer: K.map ? "click" : opts.answer,
      borders: opts.borders,
      highlight: opts.highlight,
      rotate: K.shape ? opts.rotate : "none",
      spin: opts.spin,
      tag: variantTag(),
      infinite: opts.infinite && !opts.speedrun && (K.map || opts.layout !== "grid"),
      weighted: opts.weighted && !opts.speedrun && (K.map || opts.layout !== "grid"),
      rounds: [],          // summaries of finished rounds
      missed: new Set(),   // everything missed across the session
      seen: new Set(),     // flags answered or skipped at least once this session
      recent: {},          // code -> ms for its last RECENT_N showings this session
      streak: 0,           // consecutive first-try correct answers (carries across rounds)
      start: Date.now(),
    };
    clearInterval(timerId);
    if (session.grid) return startGrid();
    buildHeatmap();
    updateStreak(false);
    timerId = setInterval(updateTime, 500);
    $("speed-clock").hidden = !session.speedrun;
    $("hud-time").hidden = session.speedrun;
    if (session.speedrun) {
      $("speed-time").textContent = fmtRun(0);
      $("speed-best").textContent = bestText(session);
    }
    const mode = session.answer;
    $("guess-box").hidden = mode !== "dropdown" && mode !== "type";
    $("mc").hidden = mode !== "mc";
    $("flag-wrap").hidden = mode === "click";
    $("flag-wrap").after($("map-wrap")); // the connect screen borrows it
    $("map-wrap").hidden = $("map-prompt").hidden = mode !== "click";
    $("answer-note").textContent = {
      dropdown: `↑ ↓ to pick a ${K.noun} · Enter to submit · ↓ on an empty box lists all ${K.nouns}`,
      type: "Type the full name · Enter to submit",
      mc: "Click an answer or press 1–4 · Esc to skip",
      click: "Scroll or pinch to zoom · drag to move · Esc to skip",
    }[mode];
    show("game");
    if (mode === "click") setupMap(session.codes);
    startRound();
  }

  function startRound() {
    const codes = session.codes;
    round = {
      number: session.rounds.length + 1,
      queue: session.weighted ? [] : shuffle(codes),
      total: codes.length,
      correct: new Set(),            // unique flags right on the first attempt (shuffle mode)
      missed: new Set(),             // unique flags skipped or guessed wrong at least once
      done: new Set(),               // unique flags finished (shuffle mode)
      hits: 0,                       // showings answered with no miss (weighted mode)
      misses: 0,                     // showings with a skip or wrong guess (weighted mode)
      draws: 0,                      // showings completed
      times: [],                     // [code, ms] for every correct answer this round
      requeue: !session.weighted && !session.speedrun && opts.requeue,
      current: null,
      shownAt: 0,
      missedThisShowing: false,
      revealing: false,
      start: Date.now(),
    };
    $("end-btn").textContent = session.speedrun ? "Give up" : session.infinite ? "End session" : "End round";
    if (session.answer === "click") clearMapMarks(true);
    if (session.speedrun) startRunClock("speed-time");
    renderLiveChart();
    next();
  }

  function next() {
    round.revealing = false;
    round.missedThisShowing = false;
    const guess = $("guess");
    guess.value = "";
    guess.disabled = false;
    hideSuggestions();
    $("reveal").textContent = "";
    $("reveal").className = "reveal";

    const finished = session.weighted ? round.draws >= round.total : round.queue.length === 0;
    if (finished) return endRound(false);

    round.current = session.weighted
      ? sampleWeighted(session.codes, round.current)
      : round.queue.shift();
    if (session.answer === "click") {
      clearMapMarks(false);
      round.wrongClicks = 0;
      $("map-prompt").textContent = COUNTRIES[round.current].name;
    } else {
      $("flag").src = flagUrl(round.current);
      applyRotation($("flag"));
    }
    if (session.answer === "mc") renderChoices();
    round.shownAt = performance.now();
    const isRetry = round.missed.has(round.current);
    $("retry-note").hidden = !isRetry;
    $("retry-note").textContent = isRetry ? "You missed this one earlier — try again." : "";
    updateHud();
    if (session.answer === "mc" || session.answer === "click") guess.blur();
    else guess.focus();
  }

  function updateHud() {
    const roundTag = session.infinite ? ` · round ${round.number}` : "";
    const modeTag = session.weighted ? " · weighted" : "";
    $("hud-region").textContent = session.label + roundTag + modeTag;
    if (session.weighted) {
      $("hud-progress").textContent = `${round.draws} / ${round.total}`;
      $("hud-score").textContent = `✓ ${round.hits}  ✗ ${round.misses}`;
      // The flag on screen isn't marked seen until it's answered, so it counts as still to play.
      const unseen = unseenIn(session.codes).length;
      if (unseen) {
        $("hud-chance").textContent = `first pass · ${unseen} new left`;
      } else {
        $("hud-chance").textContent = `chance ${fmtPct(probabilities(session.codes).get(round.current))}`;
      }
    } else {
      $("hud-progress").textContent = `${round.done.size} / ${round.total}`;
      $("hud-score").textContent = `✓ ${round.correct.size}  ✗ ${round.missed.size}`;
      $("hud-chance").textContent = "";
    }
  }

  function updateTime() {
    if (round) $("hud-time").textContent = fmtClock(Date.now() - round.start);
  }

  // Record a miss once per time a flag is shown.
  function recordMiss(code) {
    session.streak = 0;
    updateStreak(false);
    round.missed.add(code);
    session.missed.add(code);
    bank.add(code);
    saveBank();
    if (!round.missedThisShowing) {
      round.missedThisShowing = true;
      statFor(code).m++;
      saveStats();
    }
  }

  function submitGuess(text) {
    if (!round || round.revealing || !text.trim()) return;
    const c = COUNTRIES[round.current];
    if (c.answers.has(normalize(text))) markCorrect(c);
    else wrongGuess(text);
  }

  // `at` = when the answer was given (the map paints its click before getting here).
  function markCorrect(c, at = performance.now()) {
    round.revealing = true;
    hideSuggestions();
    const ms = at - round.shownAt;
    round.times.push([c.code, ms]);
    const s = statFor(c.code);
    const firstTry = !round.missedThisShowing;
    const personalBest = firstTry && s.best != null && ms < s.best;
    s.c++;
    s.t += ms;
    s.best = s.best == null ? ms : Math.min(s.best, ms);
    pushRecent(c.code, round.missedThisShowing ? Math.max(ms, MISS_PENALTY_S * 1000) : ms);
    markSeen(c.code);
    if (!round.missed.has(c.code)) {
      round.correct.add(c.code);
      bank.delete(c.code);
      saveBank();
    }
    if (round.missedThisShowing) round.misses++;
    else round.hits++;
    round.draws++;
    saveStats();
    round.done.add(c.code);
    $("guess").value = c.name;
    $("reveal").textContent = `✓ ${c.name} · ${fmtSecs(ms)}` + (personalBest ? " · new best!" : "");
    $("reveal").className = "reveal good";
    if (firstTry) session.streak++;
    const milestone = firstTry && session.streak % 5 === 0;
    if (milestone) flashBanner(`🔥 ${session.streak} in a row!`);
    const tier = !firstTry ? "retry"
      : milestone || personalBest ? "big"
      : ms < HEAT_BINS[0] * 1000 ? "fast" : "ok";
    celebrate(tier);
    updateHud();
    renderLiveChart();
    // Stop the clock on the last answer, not after the reveal pause; speed runs also advance faster.
    if (session.speedrun && round.queue.length === 0) session.runEnd = at;
    setTimeout(next, session.speedrun ? 150 : 600);
  }

  function skip() {
    if (!round || round.revealing) return;
    if (session.speedrun) return failRun(null);
    const c = COUNTRIES[round.current];
    round.revealing = true;
    hideSuggestions();
    recordMiss(c.code);
    pushRecent(c.code, MISS_PENALTY_S * 1000);
    saveStats();
    markSeen(c.code);
    round.misses++;
    round.draws++;
    if (round.requeue) {
      // Back of the queue, so every other flag is shown before it comes round again.
      round.queue.push(c.code);
    } else {
      round.done.add(c.code);
    }
    $("guess").disabled = true;
    $("mc").querySelector(`[data-code="${c.code}"]`)?.classList.add("answer");
    if (session.answer === "click") markPlace(c.code, "answer");
    $("reveal").textContent = `✗ It was ${c.name}`;
    $("reveal").className = "reveal bad";
    updateHud();
    renderLiveChart();
    setTimeout(next, REVEAL_MS);
  }

  function wrongGuess(text) {
    if (session.speedrun) return failRun(text.trim());
    recordMiss(round.current);
    playWrong();
    if (session.answer === "mc" || session.answer === "click") return updateHud();
    updateHud();
    const g = $("guess");
    g.value = "";
    hideSuggestions();
    g.classList.remove("shake");
    void g.offsetWidth; // restart animation
    g.classList.add("shake");
  }

  // ---- Shape rotation ----
  // Rotated images are drawn in a square (see .rot in the CSS) so a turned shape never overflows.
  function applyRotation(img) {
    const r = session.rotate;
    img.classList.toggle("rot", r !== "none");
    img.classList.toggle("spin", r === "spin");
    img.style.removeProperty("animation-delay");
    if (r === "none") return;
    // Any angle can need the square's diagonal, so those shrink to fit.
    img.style.setProperty("--rot-scale", r === "right" ? 1 : 0.7);
    if (r === "right") img.style.setProperty("--angle", `${90 * (1 + Math.floor(Math.random() * 3))}deg`);
    if (r === "any") img.style.setProperty("--angle", `${Math.floor(Math.random() * 360)}deg`);
    if (r === "spin") {
      const dur = 360 / session.spin;
      img.style.setProperty("--spin-dur", `${dur}s`);
      img.style.animationDelay = `${-Math.random() * dur}s`; // start at a random angle
    }
  }

  // ---- Map: click the place ----
  // maps/<name>.js (built by tools/build_map.py) sets MAPS[name] = { w, h, places, bg, boxes, dots }.
  // The view is the SVG viewBox, kept at the box's aspect ratio. Changing it redraws every border, so
  // while you drag or zoom the drawn map is just moved with a CSS transform (cheap), and the viewBox
  // catches up once the gesture pauses. `vb` is what's drawn; `target` is where the view is heading.
  const mapView = { name: null, svg: null, vb: null, target: null, home: null, hitEl: null, timer: 0 };
  const SETTLE_MS = 150;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const DOT_PX = 5; // dot radius on screen, whatever the zoom

  function loadMap(name) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = `maps/${name}.js`;
      s.onload = resolve;
      s.onerror = reject;
      document.head.append(s);
    });
  }

  // codes = places in play; the view starts framed on `frame` (default: all of them).
  function setupMap(codes, frame = codes) {
    const m = MAPS[K.map];
    if (mapView.name !== K.map) {
      mapView.svg?.remove();
      const svg = document.createElementNS(SVG_NS, "svg");
      svg.id = "map-svg";
      svg.innerHTML = (m.bg ? `<path class="bg" d="${m.bg}"/>` : "") +
        Object.entries(m.places).map(([code, d]) => `<path class="place" data-code="${code}" d="${d}"/>`).join("") +
        Object.entries(m.dots).map(([code, [x, y]]) => `<circle class="place dot" data-code="${code}" cx="${x}" cy="${y}"/>`).join("");
      $("map-wrap").prepend(svg);
      mapView.svg = svg;
      mapView.name = K.map;
    }
    const inPlay = new Set(codes);
    for (const el of mapView.svg.querySelectorAll("[data-code]")) el.classList.toggle("off", !inPlay.has(el.dataset.code));
    mapView.svg.classList.toggle("borderless", session.borders === "hidden");
    const boxes = frame.map((c) => m.boxes[c]).filter(Boolean);
    let [x0, y0, x1, y1] = [Math.min(...boxes.map((b) => b[0])), Math.min(...boxes.map((b) => b[1])),
      Math.max(...boxes.map((b) => b[2])), Math.max(...boxes.map((b) => b[3]))];
    const pad = Math.max(x1 - x0, y1 - y0) * 0.06 + m.w * 0.01;
    mapView.home = [x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad];
    mapView.vb = null;
    setView(...mapView.home);
  }

  // Draw the view now if `now` (or nothing is drawn yet); otherwise preview it and draw it when things settle.
  function setView(x, y, w, h, now = false) {
    const svg = mapView.svg, m = MAPS[mapView.name];
    const cw = svg.clientWidth || 1, ch = svg.clientHeight || 1, aspect = cw / ch;
    // Match the box's aspect ratio, growing whichever side is short.
    if (w / h < aspect) { const nw = h * aspect; x -= (nw - w) / 2; w = nw; }
    else { const nh = w / aspect; y -= (nh - h) / 2; h = nh; }
    // Zoom limits: the whole map at most, 1/60 of its width at least.
    const maxW = Math.max(m.w, m.h * aspect) * 1.05, minW = m.w / 60;
    const k = Math.min(Math.max(w, minW), maxW) / w;
    if (k !== 1) { x += (w - w * k) / 2; y += (h - h * k) / 2; w *= k; h *= k; }
    // Keep the centre over the map.
    x = Math.min(Math.max(x + w / 2, 0), m.w) - w / 2;
    y = Math.min(Math.max(y + h / 2, 0), m.h) - h / 2;
    mapView.target = [x, y, w, h];
    clearTimeout(mapView.timer);
    if (now || !mapView.vb) return drawView();
    const [dx, dy, dw] = mapView.vb;
    const px = cw / w; // screen pixels per map unit in the new view
    svg.style.transform = `translate(${(dx - x) * px}px, ${(dy - y) * px}px) scale(${dw / w})`;
    mapView.timer = setTimeout(drawView, SETTLE_MS);
  }

  function drawView() {
    const svg = mapView.svg, [x, y, w, h] = mapView.target;
    mapView.vb = mapView.target;
    svg.setAttribute("viewBox", `${x} ${y} ${w} ${h}`);
    svg.style.transform = "";
    // Map units per screen pixel: borders and dots stay the same on-screen size at any zoom.
    const k = w / (svg.clientWidth || 1);
    svg.style.setProperty("--k", k);
    for (const dot of svg.querySelectorAll(".dot")) dot.setAttribute("r", DOT_PX * k);
  }

  // Zoom by `f` (<1 = in) keeping the map point under (clientX, clientY) still.
  function zoomAt(clientX, clientY, f) {
    const [x, y, w, h] = mapView.target;
    // Measure the box, not the SVG, which may be mid-transform.
    const wrap = $("map-wrap"), rect = wrap.getBoundingClientRect();
    const px = x + ((clientX - rect.left - wrap.clientLeft) / wrap.clientWidth) * w;
    const py = y + ((clientY - rect.top - wrap.clientTop) / wrap.clientHeight) * h;
    setView(px - (px - x) * f, py - (py - y) * f, w * f, h * f);
  }

  function wireMap() {
    const wrap = $("map-wrap");
    const pointers = new Map();
    let moved = 0, pinch = 0;
    const center = () => { const r = wrap.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; };
    const spread = () => { const [a, b] = [...pointers.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };

    wrap.addEventListener("wheel", (e) => {
      if (!mapView.vb) return;
      e.preventDefault();
      zoomAt(e.clientX, e.clientY, Math.exp(e.deltaY * 0.0015));
    }, { passive: false });
    wrap.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".map-zoom") || !mapView.vb) return;
      try { wrap.setPointerCapture(e.pointerId); } catch {} // keep getting moves when the pointer leaves the map
      audioReady(); // start the sound engine now, not on the first correct click (that takes a while)
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 1) moved = 0;
      if (pointers.size === 2) pinch = spread();
    });
    wrap.addEventListener("pointermove", (e) => {
      const p = pointers.get(e.pointerId);
      if (!p) return setHover(e.target.closest?.("#map-svg [data-code]"));
      setHover(null);
      const dx = e.clientX - p.x, dy = e.clientY - p.y;
      p.x = e.clientX;
      p.y = e.clientY;
      moved += Math.abs(dx) + Math.abs(dy);
      if (pointers.size === 1) {
        const [x, y, w, h] = mapView.target;
        const k = w / mapView.svg.clientWidth;
        setView(x - dx * k, y - dy * k, w, h);
      } else if (pointers.size === 2) {
        const d = spread();
        const [a, b] = [...pointers.values()];
        if (pinch) zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, pinch / d);
        pinch = d;
        moved = Infinity; // a pinch is never a click
      }
    });
    wrap.addEventListener("pointerleave", () => setHover(null));
    const release = (e) => {
      if (!pointers.delete(e.pointerId)) return;
      try { wrap.releasePointerCapture(e.pointerId); } catch {}
      if (e.type === "pointerup" && pointers.size === 0 && moved < 6) {
        // Pointer capture retargets events, so find what's under the pointer directly.
        const el = document.elementFromPoint(e.clientX, e.clientY)?.closest("#map-svg [data-code]");
        if (el) mapClick(el);
      }
    };
    wrap.addEventListener("pointerup", release);
    wrap.addEventListener("pointercancel", release);
    $("zoom-in").onclick = () => zoomAt(...center(), 1 / 1.6);
    $("zoom-out").onclick = () => zoomAt(...center(), 1.6);
    $("zoom-reset").onclick = () => setView(...mapView.home, true);
    window.addEventListener("resize", () => { if (mapView.vb && !$("map-wrap").hidden) setView(...mapView.target, true); });
  }

  // Colour the place straight away; the bookkeeping (stats, saving, sound, confetti, charts) waits
  // until that colour is on screen, so the click feels instant. The answer time is taken at the click.
  const afterPaint = (fn) => requestAnimationFrame(() => setTimeout(fn, 0));
  // Hover is a class set here rather than CSS :hover, which browsers only re-check on the next mouse
  // move: after a click the place would keep its hover shade until you nudged the mouse.
  function setHover(el) {
    if (el && (el.classList.contains("off") || mapView.svg.classList.contains("borderless"))) el = null;
    if (mapView.hover === el) return;
    mapView.hover?.classList.remove("hover");
    el?.classList.add("hover");
    mapView.hover = el;
  }

  function mapClick(el) {
    setHover(null);
    if (!round || round.revealing || el.classList.contains("off")) return;
    const at = performance.now();
    const r = round, c = COUNTRIES[r.current];
    const code = el.dataset.code;
    mapView.hitEl = el;
    if (code === c.code) {
      r.revealing = true; // no second click while the rest catches up
      markPlace(code, session.highlight ? "found" : "right");
      return afterPaint(() => { if (round === r) markCorrect(c, at); });
    }
    markPlace(code, "wrong");
    setTimeout(() => unmarkPlace(code, "wrong"), 700);
    r.wrongClicks++;
    // After three wrong clicks, show where it is (it still counts as a miss).
    if (r.wrongClicks === 3) markPlace(c.code, "hint");
    afterPaint(() => { if (round === r && r.current === c.code) wrongGuess(COUNTRIES[code].name); });
  }

  const placeEls = (code) => mapView.svg.querySelectorAll(`[data-code="${code}"]`);
  const markPlace = (code, cls) => placeEls(code).forEach((el) => el.classList.add(cls));
  const unmarkPlace = (code, cls) => placeEls(code).forEach((el) => el.classList.remove(cls));
  // Between questions clear the hints; at the start of a round also clear what's been found.
  function clearMapMarks(all) {
    const cls = ["right", "wrong", "hint", "answer", ...(all ? ["found", "from", "to", "route", "cx-on", "cx-near", "cx-far"] : [])];
    for (const el of mapView.svg.querySelectorAll("[data-code]")) el.classList.remove(...cls);
  }

  // ---- Connect: join two places with a chain of land neighbours ----
  // Any unbroken chain wins. Guesses are capped at the shortest route's length plus CX_SPARE, and
  // each is coloured by how far it is off a shortest route.
  const CX_SPARE = 3;
  const CX_MIN = 2, CX_MAX = 7; // puzzle route lengths, in borders crossed
  let cx = null;

  function bfs(from) {
    const adj = NEIGHBORS[K.map], dist = { [from]: 0 }, queue = [from];
    for (let i = 0; i < queue.length; i++) {
      for (const n of adj[queue[i]] || []) {
        if (!(n in dist)) { dist[n] = dist[queue[i]] + 1; queue.push(n); }
      }
    }
    return dist;
  }

  // Every pair of places in `codes` that a puzzle could use (the route may leave the region).
  const pairCache = new Map();
  function connectPairs(codes) {
    const cacheKey = `${K.map}:${codes.join()}`;
    if (!pairCache.has(cacheKey)) {
      const pairs = [];
      for (const a of codes) {
        const d = bfs(a);
        for (const b of codes) if (a < b && d[b] >= CX_MIN && d[b] <= CX_MAX) pairs.push([a, b]);
      }
      pairCache.set(cacheKey, pairs);
    }
    return pairCache.get(cacheKey);
  }

  function startConnect(label, codes) {
    if (!window.MAPS?.[K.map]) {
      loadMap(K.map).then(() => startConnect(label, codes), () => alert("Couldn't load the map."));
      return;
    }
    syncOptions();
    round = null;
    // A session only so the shared map and dropdown code know the settings.
    session = { label, codes, answer: "dropdown", borders: opts.borders, connect: true };
    cx = { label, pairs: connectPairs(codes), last: null };
    $("cx-region").textContent = label;
    $("cx-guess").placeholder = `Type a ${K.noun} in between…`;
    show("connect");
    $("cx-map-slot").append($("map-wrap"));
    $("map-wrap").hidden = false;
    newPuzzle();
  }

  function newPuzzle() {
    let pair;
    do pair = cx.pairs[Math.floor(Math.random() * cx.pairs.length)];
    while (cx.pairs.length > 1 && pair.join() === cx.last);
    cx.last = pair.join();
    const [from, to] = Math.random() < 0.5 ? pair : [pair[1], pair[0]];
    const dFrom = bfs(from), dTo = bfs(to);
    const shortest = dFrom[to];
    Object.assign(cx, { from, to, dFrom, dTo, shortest, guessed: [], limit: shortest - 1 + CX_SPARE, over: false });
    // Frame the map on everything along any shortest route.
    const route = Object.keys(dFrom).filter((c) => dFrom[c] + (dTo[c] ?? Infinity) === shortest);
    setupMap(Object.keys(COUNTRIES), route);
    clearMapMarks(true);
    markPlace(from, "from");
    markPlace(to, "to");
    $("cx-from").textContent = COUNTRIES[from].name;
    $("cx-to").textContent = COUNTRIES[to].name;
    $("cx-result").textContent = "";
    $("cx-result").className = "reveal";
    $("cx-list").innerHTML = "";
    $("cx-next").hidden = true;
    $("cx-giveup").hidden = false;
    $("cx-guess").disabled = false;
    $("cx-guess").value = "";
    renderConnectHud();
    $("cx-guess").focus();
  }

  function renderConnectHud() {
    const left = cx.limit - cx.guessed.length;
    $("cx-guesses").textContent = `${left} guess${left === 1 ? "" : "es"} left · best possible ${cx.shortest - 1}`;
    const st = load(key("connect"), {});
    $("cx-score").textContent = `solved ${st.solved || 0} / ${st.played || 0} · streak ${st.streak || 0}`;
  }

  function cxSubmit(text) {
    if (!cx) return;
    if (cx.over) return newPuzzle();
    const input = $("cx-guess");
    const key_ = normalize(text);
    const c = key_ && Object.values(COUNTRIES).find((x) => x.answers.has(key_));
    hideSuggestions();
    input.value = "";
    if (!c) return text.trim() && replay(input, "shake");
    if (c.code === cx.from || c.code === cx.to || cx.guessed.includes(c.code)) {
      $("cx-result").textContent = `${c.name} is already on the map`;
      $("cx-result").className = "reveal";
      return;
    }
    cx.guessed.push(c.code);
    const off = cx.dFrom[c.code] + cx.dTo[c.code] - cx.shortest; // NaN when it's cut off entirely
    const cls = off === 0 ? "cx-on" : off <= 2 ? "cx-near" : "cx-far";
    markPlace(c.code, cls);
    const li = document.createElement("li");
    li.className = cls;
    li.textContent = c.name;
    $("cx-list").append(li);
    $("cx-result").textContent = "";
    if (chain()) return endPuzzle(true);
    if (cx.guessed.length >= cx.limit) return endPuzzle(false);
    renderConnectHud();
  }

  // The guessed places linking `from` to `to`, or null while they aren't connected.
  function chain() {
    const adj = NEIGHBORS[K.map], ok = new Set([...cx.guessed, cx.to]);
    const prev = { [cx.from]: null }, queue = [cx.from];
    for (let i = 0; i < queue.length; i++) {
      for (const n of adj[queue[i]] || []) {
        if (ok.has(n) && !(n in prev)) { prev[n] = queue[i]; queue.push(n); }
      }
    }
    if (!(cx.to in prev)) return null;
    const path = [];
    for (let n = prev[cx.to]; n !== cx.from; n = prev[n]) path.unshift(n);
    return path;
  }

  function endPuzzle(won) {
    cx.over = true;
    const st = load(key("connect"), { played: 0, solved: 0, perfect: 0, streak: 0, best: 0 });
    st.played++;
    const used = cx.guessed.length, best = cx.shortest - 1;
    if (won) {
      st.solved++;
      st.streak++;
      st.best = Math.max(st.best, st.streak);
      if (used === best) st.perfect++;
      $("cx-result").textContent = used === best
        ? `Perfect! Connected in ${used} — the shortest possible`
        : `Connected in ${used} · shortest possible was ${best}`;
      $("cx-result").className = "reveal good";
      playCorrect();
      replay($("cx-result"), "pop");
      confetti(used === best ? 60 : 25, $("map-wrap"));
    } else {
      st.streak = 0;
      // Show a shortest route, preferring one through places already guessed.
      const route = [];
      for (let n = cx.from; ;) {
        const next = (NEIGHBORS[K.map][n] || []).filter((x) => cx.dTo[x] === cx.dTo[n] - 1)
          .sort((a, b) => cx.guessed.includes(b) - cx.guessed.includes(a))[0];
        if (next === cx.to) break;
        route.push(next);
        n = next;
      }
      for (const code of route) if (!cx.guessed.includes(code)) markPlace(code, "route");
      $("cx-result").textContent = `One route: ${route.map((c) => COUNTRIES[c].name).join(" → ")}`;
      $("cx-result").className = "reveal bad";
      playWrong();
    }
    save(key("connect"), st);
    $("cx-guess").disabled = false;
    $("cx-next").hidden = false;
    $("cx-giveup").hidden = true;
    renderConnectHud();
    $("cx-next").focus();
  }

  // ---- Multiple choice ----
  // The right answer plus three others, from the same continent where possible so it isn't too easy.
  function choicesFor(code) {
    const c = COUNTRIES[code];
    const others = Object.values(COUNTRIES).filter((x) => x.code !== code);
    const near = others.filter((x) => x.region === c.region);
    return shuffle([c, ...shuffle(near.length >= 3 ? near : others).slice(0, 3)]);
  }

  function renderChoices() {
    const box = $("mc");
    box.innerHTML = "";
    choicesFor(round.current).forEach((c, i) => {
      const b = document.createElement("button");
      b.className = "choice";
      b.dataset.code = c.code;
      b.innerHTML = `<kbd>${i + 1}</kbd>`;
      b.append(c.name);
      b.onclick = () => pickChoice(b);
      box.append(b);
    });
  }

  function pickChoice(b) {
    if (!round || round.revealing || !b || b.disabled) return;
    const c = COUNTRIES[round.current];
    if (b.dataset.code === c.code) {
      b.classList.add("right");
      markCorrect(c);
    } else {
      b.disabled = true;
      b.classList.add("wrong");
      wrongGuess(COUNTRIES[b.dataset.code].name);
    }
  }

  // ---- Grid: every question on screen at once, answered in any order ----
  // Answer times aren't meaningful here, so the grid only feeds the missed list and miss counts.
  function startGrid() {
    const s = session;
    round = { grid: true, total: s.codes.length, done: new Set(), missed: new Set(), times: [], current: null };
    const list = $("grid-list");
    parkSuggestions();
    list.innerHTML = "";
    for (const code of shuffle(s.codes)) list.append(gridCell(code));
    $("grid-region").textContent = s.label + (s.tag ? ` · ${s.tag}` : "");
    $("grid-best").textContent = bestText(s);
    $("grid-end-btn").textContent = s.speedrun ? "Give up" : "Finish";
    updateGridHud();
    show("grid");
    startRunClock("grid-time");
    list.querySelector("input, button")?.focus();
  }

  function gridCell(code) {
    const li = document.createElement("li");
    li.className = "cell";
    li.dataset.code = code;
    li.innerHTML = `<div class="cell-img rot-box"><img alt=""></div>`;
    const img = li.querySelector("img");
    img.src = flagUrl(code);
    applyRotation(img);
    if (session.answer === "mc") {
      const box = document.createElement("div");
      box.className = "cell-mc";
      for (const c of choicesFor(code)) {
        const b = document.createElement("button");
        b.textContent = c.name;
        b.onclick = () => (c.code === code ? gridCorrect(li) : gridWrong(li, c.name, b));
        box.append(b);
      }
      li.append(box);
    } else {
      const box = document.createElement("div");
      box.className = "guess-box";
      const input = document.createElement("input");
      input.type = "text";
      input.autocomplete = "off";
      input.spellcheck = false;
      input.setAttribute("aria-label", `${cap(K.one)} answer`);
      const matches = (text) => COUNTRIES[code].answers.has(normalize(text));
      input.addEventListener("input", () => {
        if (matches(input.value)) gridCorrect(li);
        else updateSuggestions();
      });
      attachSuggestions(input, (text) => {
        if (!text.trim()) focusNextCell(li);
        else if (matches(text)) gridCorrect(li);
        else gridWrong(li, text.trim(), null);
      });
      box.append(input);
      li.append(box);
    }
    return li;
  }

  function focusNextCell(li) {
    const open = [...$("grid-list").querySelectorAll(".cell:not(.done)")];
    if (!open.length) return;
    const after = open.find((x) => li.compareDocumentPosition(x) & Node.DOCUMENT_POSITION_FOLLOWING);
    (after || open[0]).querySelector("input, button:not(:disabled)")?.focus();
  }

  function gridCorrect(li) {
    const code = li.dataset.code;
    if (!round?.grid || round.done.has(code)) return;
    round.done.add(code);
    const first = !round.missed.has(code);
    if (first) {
      bank.delete(code);
      saveBank();
    }
    li.classList.add("done", first ? "right" : "late");
    if (li.contains($("suggestions"))) parkSuggestions();
    li.querySelector(".cell-mc, .guess-box").replaceWith(Object.assign(document.createElement("div"), {
      className: "cell-name", textContent: COUNTRIES[code].name,
    }));
    playCorrect();
    replay(li, "glow");
    confetti(first ? 8 : 0, li);
    updateGridHud();
    if (round.done.size === round.total) return endGrid(false);
    focusNextCell(li);
  }

  function gridWrong(li, typed, button) {
    const code = li.dataset.code;
    if (session.speedrun) {
      round.current = code;
      return failRun(typed);
    }
    if (!round.missed.has(code)) {
      round.missed.add(code);
      session.missed.add(code);
      bank.add(code);
      saveBank();
      statFor(code).m++;
      saveStats();
    }
    playWrong();
    if (button) {
      button.disabled = true;
      button.classList.add("wrong");
    } else {
      const input = li.querySelector("input");
      hideSuggestions();
      input.value = "";
      replay(input, "shake");
    }
    updateGridHud();
  }

  function updateGridHud() {
    $("grid-progress").textContent = `${round.done.size} / ${round.total}`;
    $("grid-score").textContent = `✓ ${round.done.size - [...round.done].filter((c) => round.missed.has(c)).length}  ✗ ${round.missed.size}`;
  }

  // gaveUp = the player pressed Finish / Give up before answering everything.
  function endGrid(gaveUp) {
    const s = session, r = round;
    s.runEnd ??= performance.now();
    const left = s.codes.filter((c) => !r.done.has(c));
    if (s.speedrun) return showRunResults(gaveUp ? { code: left[0], typed: null, gaveUp: true } : null);

    round = null;
    for (const c of left) bank.add(c);
    saveBank();
    const firstTry = r.done.size - [...r.done].filter((c) => r.missed.has(c)).length;
    $("res-title").textContent = gaveUp ? "Grid ended" : "Grid complete!";
    $("res-summary").textContent =
      `${firstTry} of ${r.total} right first try (${fmtPct(firstTry / r.total)}) · ${fmtRun(s.runEnd - s.runStart)}` +
      (left.length ? ` · ${left.length} not answered` : "");
    if (!gaveUp && firstTry === r.total) confetti(60);

    const replayCodes = [...new Set([...r.missed, ...left])];
    const rb = $("replay-btn");
    rb.hidden = replayCodes.length === 0;
    rb.textContent = `Replay missed ${K.many} (${replayCodes.length})`;
    const label = s.label, codes = s.codes;
    rb.onclick = () => startSession(`${label.replace(/ · missed$/, "")} · missed`, replayCodes);
    $("again-btn").textContent = "Play grid again";
    $("again-btn").onclick = () => startSession(label, codes);
    $("session-block").hidden = true;
    $("missed-heading").textContent = replayCodes.length ? `${cap(K.many)} you missed` : "Perfect — no misses!";
    renderFlagCards($("missed-list"), replayCodes.map((c) => [c, r.done.has(c) ? "" : "not answered"]));
    $("slow-heading").hidden = true;
    $("slow-list").innerHTML = "";
    show("results");
    rb.hidden ? $("again-btn").focus() : rb.focus();
  }

  // ---- Speed run ----
  // One pass through the region against the clock. Any wrong answer or skip ends the run.
  function startRunClock(id) {
    const s = session;
    s.runStart = performance.now();
    s.runEnd = null;
    (function tick() {
      if (session !== s || s.runEnd != null) return;
      $(id).textContent = fmtRun(performance.now() - s.runStart);
      requestAnimationFrame(tick);
    })();
  }

  function bestText(s) {
    const rec = records[recKey(s.label, s.tag)];
    if (!s.speedrun) return "";
    return rec ? `best ${fmtRun(rec.ms)}` : isRanked(s.label) ? "no record yet" : "practice · not ranked";
  }

  function failRun(typed) {
    const code = round.current;
    round.revealing = true;
    recordMiss(code);
    pushRecent(code, MISS_PENALTY_S * 1000);
    saveStats();
    playWrong();
    showRunResults({ code, typed });
  }

  // failed = { code, typed, gaveUp } for a run that ended early, or null for a finished one.
  function showRunResults(failed) {
    const s = session;
    s.runEnd ??= performance.now();
    const ms = s.runEnd - s.runStart;
    const r = round;
    clearInterval(timerId);
    round = null;
    const rk = recKey(s.label, s.tag);
    const prev = records[rk];
    const ranked = isRanked(s.label);
    if (!failed) {
      runs.push({
        label: s.label, ms, at: Date.now(),
        ...(s.tag && { variant: s.tag }),
        ...(ranked && { prevMs: prev?.ms ?? null }),
      });
      saveRuns();
    }

    if (failed) {
      $("res-title").textContent = failed.gaveUp ? "Run abandoned" : "Run over";
      $("res-summary").textContent =
        `${s.label} · ${r.done.size} / ${r.total} ${K.many} · ${fmtRun(ms)}` + (prev ? ` · best ${fmtRun(prev.ms)}` : "");
    } else if (ranked && (!prev || ms < prev.ms)) {
      records[rk] = { ms, at: Date.now() };
      saveRecords();
      $("res-title").textContent = `New record! ${fmtRun(ms)}`;
      $("res-summary").textContent = prev
        ? `${s.label} · previous best ${fmtRun(prev.ms)} (−${((prev.ms - ms) / 1000).toFixed(2)}s)`
        : `${s.label} · first completed run`;
      playCorrect();
      confetti(80);
    } else {
      $("res-title").textContent = `Finished in ${fmtRun(ms)}`;
      $("res-summary").textContent = prev
        ? `${s.label} · best ${fmtRun(prev.ms)} (+${((ms - prev.ms) / 1000).toFixed(2)}s)`
        : `${s.label} · practice runs aren't ranked`;
    }

    $("replay-btn").hidden = true;
    $("session-block").hidden = true;
    const label = s.label, codes = s.codes;
    $("again-btn").textContent = "Restart run";
    $("again-btn").onclick = () => startSession(label, codes);

    $("missed-heading").textContent = failed ? (failed.gaveUp ? "Gave up on" : "The one that ended it") : "Perfect run — no misses!";
    const how = failed?.gaveUp ? "gave up" : failed?.typed ? `you ${{ mc: "picked", click: "clicked" }[session.answer] || "typed"} “${failed.typed}”` : "skipped";
    renderFlagCards($("missed-list"), failed ? [[failed.code, how]] : []);

    const slow = r.grid ? [] : [...r.times].sort((a, b) => b[1] - a[1]).slice(0, 10);
    $("slow-heading").hidden = slow.length === 0;
    $("slow-heading").textContent = "Slowest answers this run";
    renderFlagCards($("slow-list"), slow.map(([code, t]) => [code, fmtSecs(t)]));

    show("results");
    $("again-btn").focus();
  }

  function renderRecords() {
    const tag = variantTag();
    $("records-variant").hidden = !tag;
    $("records-variant").textContent = tag;
    const rows = [K.all, ...Object.keys(K.regions)].map((label) => {
      const rec = records[recKey(label, tag)];
      return `<tr><th scope="row">${label}</th>` +
        (rec
          ? `<td class="num">${fmtRun(rec.ms)}</td><td title="${new Date(rec.at).toLocaleString()}">${fmtWhen(rec.at)}</td>`
          : `<td class="num muted">—</td><td></td>`) + "</tr>";
    });
    $("records-body").innerHTML = rows.join("");
  }

  // ---- Round summaries ----
  function summarize(r, partial) {
    const times = r.times.map(([, ms]) => ms);
    const hits = session.weighted ? r.hits : r.correct.size;
    const answered = session.weighted ? r.draws : r.done.size;
    return {
      number: r.number,
      partial,
      total: r.total,
      answered,
      hits,
      misses: session.weighted ? r.misses : r.missed.size,
      // First-try accuracy over what was actually played (so an ended-early round isn't penalised).
      acc: partial ? (answered ? hits / answered : null) : hits / r.total,
      avgMs: times.length ? times.reduce((a, b) => a + b, 0) / times.length : null,
      durationMs: Date.now() - r.start,
    };
  }

  // byUser = the player pressed End; otherwise the round ran out of flags.
  function endRound(byUser) {
    const r = round;
    if (session.speedrun) return byUser ? showRunResults({ code: r.current, typed: null, gaveUp: true }) : showRunResults(null);
    // Ended right after a wrong guess: that showing still goes into the recent history as a miss.
    if (byUser && r.missedThisShowing && !r.revealing) {
      pushRecent(r.current, MISS_PENALTY_S * 1000);
      saveStats();
    }
    const summary = summarize(r, byUser);
    if (!byUser || summary.answered > 0) session.rounds.push(summary);

    if (session.infinite && !byUser) {
      flashBanner(`Round ${summary.number} done · ${fmtPct(summary.acc)} first try · avg ${fmtSecs(summary.avgMs)}`);
      startRound();
      return;
    }
    showResults(r);
  }

  function flashBanner(text) {
    const b = $("banner");
    b.textContent = text;
    b.hidden = false;
    b.classList.remove("fade");
    void b.offsetWidth;
    b.classList.add("fade");
    clearTimeout(flashBanner.t);
    flashBanner.t = setTimeout(() => { b.hidden = true; }, 3000);
  }

  function showResults(r) {
    clearInterval(timerId);
    round = null;
    const multi = session.infinite;
    const last = session.rounds[session.rounds.length - 1];
    const totalMs = Date.now() - session.start;

    if (multi) {
      const played = session.rounds.reduce((a, x) => a + x.answered, 0);
      const hits = session.rounds.reduce((a, x) => a + x.hits, 0);
      const full = session.rounds.filter((x) => !x.partial).length;
      $("res-title").textContent = "Session ended";
      $("res-summary").textContent =
        `${full} full round${full === 1 ? "" : "s"} · ${played} ${K.many} · ` +
        `${played ? fmtPct(hits / played) : "—"} first try · ${fmtClock(totalMs)}`;
    } else {
      $("res-title").textContent = last && !last.partial ? "Round complete!" : "Round ended";
      $("res-summary").textContent = last
        ? `${last.hits} of ${last.total} correct on the first try (${fmtPct(last.hits / last.total)}) · ` +
          `${fmtClock(last.durationMs)}` + (last.avgMs != null ? ` · avg ${fmtSecs(last.avgMs)} per ${K.one}` : "")
        : `No ${K.many} answered.`;
    }

    // Replay = everything missed this session, plus anything not reached in the last round.
    const missed = [...session.missed];
    const replay = new Set(missed);
    if (!session.weighted) for (const c of r.queue) replay.add(c);
    if (r.current && !r.done.has(r.current) && !session.weighted) replay.add(r.current);

    const rb = $("replay-btn");
    rb.hidden = replay.size === 0;
    rb.textContent = `Replay missed ${K.many} (${replay.size})`;
    const label = session.label, codes = session.codes;
    rb.onclick = () => startSession(`${label.replace(/ · missed$/, "")} · missed`, [...replay]);
    $("again-btn").textContent = multi ? "New session" : "Play full round again";
    $("again-btn").onclick = () => startSession(label, codes);

    $("session-block").hidden = !multi || session.rounds.length === 0;
    if (multi) renderRoundsChart($("results-chart"), session.rounds, null);

    $("missed-heading").textContent = missed.length ? `${cap(K.many)} you missed` : (replay.size ? "" : "Perfect — no misses!");
    renderFlagCards($("missed-list"), missed.map((code) => [code, ""]));

    // Slowest correct answers (the slowest showing of each flag).
    const slowest = new Map();
    for (const [code, ms] of r.times) slowest.set(code, Math.max(ms, slowest.get(code) ?? 0));
    const slow = [...slowest].sort((a, b) => b[1] - a[1]).slice(0, 10);
    $("slow-heading").hidden = slow.length === 0;
    $("slow-heading").textContent = multi ? "Slowest correct answers (last round)" : "Slowest correct answers this round";
    renderFlagCards($("slow-list"), slow.map(([code, ms]) =>
      [code, `${fmtSecs(ms)} · all-time last ${RECENT_N} avg ${fmtSecs(recentMs(stats[code]))}`]));

    show("results");
    rb.hidden ? $("again-btn").focus() : rb.focus();
  }

  function renderFlagCards(ul, items) {
    ul.innerHTML = "";
    for (const [code, detail] of items) {
      const li = document.createElement("li");
      li.innerHTML = `<img src="${flagUrl(code)}" alt=""><span class="name"></span><span class="detail"></span>`;
      li.querySelector(".name").textContent = COUNTRIES[code].name;
      li.querySelector(".detail").textContent = detail;
      ul.append(li);
    }
  }

  // ---- Flag heatmap (top right) ----
  // A fixed grid of every flag in the session, alphabetical. A square only gets colour once that
  // flag has been answered or skipped, so it never gives away the flag currently on screen.
  function buildHeatmap() {
    const grid = $("heatmap");
    grid.innerHTML = "";
    const codes = session.codes.slice().sort((a, b) => COUNTRIES[a].name.localeCompare(COUNTRIES[b].name));
    grid.style.setProperty("--cols", Math.min(codes.length, 14));
    for (const code of codes) {
      const sq = document.createElement("div");
      sq.className = "sq unseen";
      sq.dataset.code = code;
      sq.style.setProperty("--flag", `url("${flagUrl(code)}")`);
      grid.append(sq);
    }
    updateHeatmapCount();
  }

  function heatLevel(code) {
    const secs = sessionScoreSecs(code);
    if (secs == null) return 1;
    const i = HEAT_BINS.findIndex((b) => secs <= b);
    return (i === -1 ? HEAT_BINS.length : i) + 1;
  }

  function markSeen(code) {
    session.seen.add(code);
    const sq = $("heatmap").querySelector(`[data-code="${code}"]`);
    if (sq) sq.className = `sq seen lv${heatLevel(code)}`;
    updateHeatmapCount();
  }

  function updateHeatmapCount() {
    $("heatmap-count").textContent = `${session.seen.size} / ${session.codes.length}`;
  }

  // ---- Rounds chart (infinite mode) ----
  // Two single-series bar strips sharing the round axis: first-try accuracy and average time.
  function renderLiveChart() {
    const panel = $("session-panel");
    panel.hidden = !session.infinite;
    if (!session.infinite) return;
    renderRoundsChart($("live-chart"), session.rounds, round && summarize(round, true));
  }

  function renderRoundsChart(el, rounds, live) {
    const all = live && live.answered > 0 ? [...rounds, { ...live, live: true }] : rounds.slice();
    el.innerHTML = "";
    if (!all.length) {
      el.innerHTML = `<p class="note">Round bars appear here as you play.</p>`;
      return;
    }
    const maxAvg = Math.max(1000, ...all.map((x) => x.avgMs ?? 0));
    const strips = [
      { title: "First-try accuracy", value: (x) => x.acc, max: 1, fmt: (v) => (v == null ? "—" : fmtPct(v)) },
      { title: `Avg time per ${K.one}`, value: (x) => x.avgMs, max: maxAvg, fmt: fmtSecs },
    ];
    for (const s of strips) {
      const row = document.createElement("div");
      row.className = "strip";
      const latest = all[all.length - 1];
      row.innerHTML = `<div class="strip-head"><span>${s.title}</span><span class="strip-latest"></span></div><div class="bars"></div>`;
      row.querySelector(".strip-latest").textContent =
        `${latest.live ? "this round" : `round ${latest.number}`}: ${s.fmt(s.value(latest))}`;
      const bars = row.querySelector(".bars");
      for (const x of all) {
        const v = s.value(x);
        const col = document.createElement("div");
        col.className = "bar-col" + (x.live ? " live" : "") + (x.partial && !x.live ? " partial" : "");
        const h = v == null ? 0 : Math.max(2, (v / s.max) * 100);
        col.innerHTML = `<div class="bar" style="height:${h}%"></div>`;
        col.dataset.tip =
          `Round ${x.number}${x.live ? " (in progress)" : x.partial ? " (ended early)" : ""}\n` +
          `${x.acc == null ? "—" : fmtPct(x.acc)} first try · avg ${fmtSecs(x.avgMs)}\n` +
          `${x.answered} / ${x.total} ${K.many} · ${fmtClock(x.durationMs)}`;
        bars.append(col);
      }
      el.append(row);
    }
    const axis = document.createElement("div");
    axis.className = "bars axis";
    for (const x of all) {
      const t = document.createElement("span");
      t.textContent = all.length <= 20 || x.number % 5 === 0 ? x.number : "";
      axis.append(t);
    }
    el.append(axis);
    // Keep the newest round in view once it overflows.
    el.querySelectorAll(".bars").forEach((b) => { b.scrollLeft = b.scrollWidth; });
  }

  // One tooltip shared by every chart.
  document.addEventListener("mouseover", (e) => {
    const col = e.target.closest?.(".bar-col, #heatmap .sq");
    const tip = $("tooltip");
    if (!col) { tip.hidden = true; return; }
    if (col.dataset.code) {
      const code = col.dataset.code;
      const seen = session?.seen.has(code);
      // Unseen flags show their name only, so the grid can't be used as a cheat sheet.
      tip.innerHTML = (seen ? `<img class="tip-flag" src="${flagUrl(code)}" alt="">` : "") +
        `<strong></strong><span class="tip-detail"></span>`;
      tip.querySelector("strong").textContent = COUNTRIES[code].name;
      tip.querySelector(".tip-detail").textContent = seen
        ? `last ${RECENT_N} this session: avg ${fmtSecs(sessionScoreSecs(code) * 1000)}`
        : "not seen yet this session";
    } else {
      tip.textContent = col.dataset.tip;
    }
    tip.hidden = false;
    const r = col.getBoundingClientRect();
    const tw = tip.offsetWidth;
    tip.style.left = `${Math.min(window.innerWidth - tw - 8, Math.max(8, r.left + r.width / 2 - tw / 2))}px`;
    // Above the target, or below it if there isn't room above.
    const above = r.top - tip.offsetHeight - 8;
    tip.style.top = `${(above >= 8 ? above : r.bottom + 8) + window.scrollY}px`;
  });

  // ---- Suggestions dropdown ----
  // One list, shared by the single answer box and every grid box: it moves to whichever box has focus.
  let suggestions = [];
  let active = -1;
  let sugInput = $("guess");
  let sugSubmit = (text) => submitGuess(text);

  function updateSuggestions(showAllWhenEmpty = false) {
    const q = searchKey(sugInput.value);
    if (session?.answer !== "dropdown" || (!q && !showAllWhenEmpty)) return hideSuggestions();
    suggestions = ALPHABETICAL
      .filter((c) => !q || c.keys.some((k) => k.includes(q)));
    active = suggestions.length ? 0 : -1;
    renderSuggestions();
  }

  function renderSuggestions() {
    const ul = $("suggestions");
    ul.innerHTML = "";
    if (!suggestions.length) return hideSuggestions();
    suggestions.forEach((c, i) => {
      const li = document.createElement("li");
      li.id = `sugg-${i}`;
      li.setAttribute("role", "option");
      li.textContent = c.name;
      if (i === active) li.className = "active";
      li.setAttribute("aria-selected", i === active);
      // mousedown (not click) so the input doesn't lose focus first
      li.addEventListener("mousedown", (e) => { e.preventDefault(); choose(i); });
      li.addEventListener("mousemove", () => { if (active !== i) setActive(i); });
      ul.append(li);
    });
    ul.hidden = false;
    sugInput.setAttribute("aria-expanded", "true");
    sugInput.setAttribute("aria-activedescendant", active >= 0 ? `sugg-${active}` : "");
  }

  function setActive(i) {
    const ul = $("suggestions");
    ul.children[active]?.classList.remove("active");
    ul.children[active]?.setAttribute("aria-selected", "false");
    active = i;
    const li = ul.children[active];
    if (!li) return;
    li.classList.add("active");
    li.setAttribute("aria-selected", "true");
    li.scrollIntoView({ block: "nearest" });
    sugInput.setAttribute("aria-activedescendant", li.id);
  }

  function hideSuggestions() {
    suggestions = [];
    active = -1;
    $("suggestions").hidden = true;
    $("suggestions").innerHTML = "";
    sugInput.setAttribute("aria-expanded", "false");
    sugInput.removeAttribute("aria-activedescendant");
  }

  function choose(i) {
    const c = suggestions[i];
    if (c) sugSubmit(c.name);
  }

  // Dropdown keys for an answer box: ↑ ↓ move, Enter picks or submits, Esc closes the list (or calls onEscape).
  function attachSuggestions(input, submit, onEscape) {
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", "suggestions");
    input.setAttribute("aria-expanded", "false");
    input.addEventListener("focus", () => {
      if (sugInput === input) return;
      hideSuggestions();
      sugInput = input;
      sugSubmit = submit;
      input.parentNode.append($("suggestions"));
    });
    input.addEventListener("keydown", (e) => {
      const open = !$("suggestions").hidden;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (!open) updateSuggestions(true);
        else setActive(Math.min(active + 1, suggestions.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (open) setActive(Math.max(active - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (open && active >= 0) choose(active);
        else submit(input.value);
      } else if (e.key === "Escape") {
        e.preventDefault();
        if (open) hideSuggestions();
        else onEscape?.();
      }
    });
    input.addEventListener("blur", hideSuggestions);
  }
  // Put the list back in the single-question box before a grid box holding it is removed.
  function parkSuggestions() {
    hideSuggestions();
    $("guess-box").append($("suggestions"));
  }

  // ---- Stats screen ----
  let statsSort = { key: "recent", dir: -1 };

  function renderStats() {
    syncOptions();
    const regionSel = $("stats-region");
    if (regionSel.dataset.kind !== K.prefix) {
      regionSel.dataset.kind = K.prefix;
      regionSel.length = 0;
      for (const r of ["All regions", ...Object.keys(K.regions)]) regionSel.add(new Option(r, r));
    }
    const region = regionSel.value;
    const pool = ALPHABETICAL.filter((c) => region === "All regions" || c.region === region);
    const rows = pool
      .map((c) => {
        const s = stats[c.code] || {};
        return {
          c, correct: s.c || 0, missed: s.m || 0, avg: avgMs(s), best: s.best ?? null,
          recent: scoreSecs(c.code) == null ? null : scoreSecs(c.code) * 1000,
        };
      })
      .filter((r) => r.correct || r.missed || $("stats-unplayed").checked);

    const { key, dir } = statsSort;
    rows.sort((a, b) => {
      const va = key === "name" ? a.c.name : key === "region" ? a.c.region : a[key];
      const vb = key === "name" ? b.c.name : key === "region" ? b.c.region : b[key];
      if (va == null && vb == null) return a.c.name.localeCompare(b.c.name);
      if (va == null) return 1;   // unplayed always at the bottom
      if (vb == null) return -1;
      const cmp = typeof va === "string" ? va.localeCompare(vb) : va - vb;
      return cmp * dir || a.c.name.localeCompare(b.c.name);
    });

    const tbody = $("stats-body");
    tbody.innerHTML = "";
    for (const r of rows) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><img src="${flagUrl(r.c.code)}" alt=""></td><td></td><td></td>
        <td class="num">${r.correct}</td><td class="num">${r.missed}</td>
        <td class="num">${fmtSecs(r.recent)}</td>
        <td class="num">${fmtSecs(r.avg)}</td><td class="num">${fmtSecs(r.best)}</td>`;
      tr.children[1].textContent = r.c.name;
      tr.children[2].textContent = r.c.region;
      tbody.append(tr);
    }
    $("stats-empty").hidden = rows.length > 0;
    renderRuns();
    for (const th of document.querySelectorAll("#stats-table th[data-key]")) {
      th.dataset.sort = th.dataset.key === key ? (dir > 0 ? "asc" : "desc") : "";
    }
    show("stats");
  }

  // ---- Wiring ----
  const guess = $("guess");
  guess.addEventListener("input", () => {
    if (!round || round.revealing) return;
    const c = COUNTRIES[round.current];
    if (c.answers.has(normalize(guess.value))) return markCorrect(c);
    updateSuggestions();
  });
  attachSuggestions(guess, submitGuess, skip);
  // Connect: no auto-accept while typing ("Niger" is a prefix of "Nigeria"), so Enter submits.
  $("cx-guess").addEventListener("input", () => {
    $("cx-guess").classList.remove("shake");
    updateSuggestions();
  });
  attachSuggestions($("cx-guess"), cxSubmit);
  $("cx-next").onclick = () => newPuzzle();
  $("cx-giveup").onclick = () => { if (cx && !cx.over) endPuzzle(false); };
  $("cx-home").onclick = () => { cx = null; renderHome(); };

  for (const id of ["opt-requeue", "opt-infinite", "opt-weighted", "opt-speedrun", "opt-temp", "opt-spin"]) {
    $(id).addEventListener("input", syncOptions);
  }
  for (const radio of document.querySelectorAll(".seg input")) radio.addEventListener("change", syncOptions);

  // Multiple choice keys: 1–4 pick. With no answer box (multiple choice, map), Esc skips.
  document.addEventListener("keydown", (e) => {
    if (!round || round.grid || $("game").hidden) return;
    const mode = session.answer;
    if (mode === "mc" && e.key >= "1" && e.key <= "4") pickChoice($("mc").children[e.key - 1]);
    else if ((mode === "mc" || mode === "click") && e.key === "Escape") skip();
  });
  for (const id of ["opt-highlight"]) $(id).addEventListener("input", syncOptions);
  wireMap();
  $("grid-end-btn").onclick = () => { if (round?.grid) endGrid(true); };

  $("skip-btn").onclick = () => { skip(); guess.focus(); };
  $("sound-btn").onclick = () => {
    soundOn = !soundOn;
    save("quiz.sound", soundOn);
    renderSoundBtn();
    guess.focus();
  };
  renderSoundBtn();
  $("end-btn").onclick = () => { if (round) endRound(true); };
  $("home-btn").onclick = renderHome;
  $("stats-btn").onclick = renderStats;
  $("stats-home-btn").onclick = renderHome;
  $("stats-region").onchange = renderStats;
  $("stats-unplayed").onchange = renderStats;
  // Completed speed runs, newest first. "vs best" compares with the record as it stood before that run.
  function renderRuns() {
    $("runs-empty").hidden = runs.length > 0;
    $("runs-wrap").hidden = runs.length === 0;
    $("runs-body").innerHTML = runs.map((run, i) => {
      const vs = !("prevMs" in run) ? "not ranked"
        : run.prevMs == null || run.ms < run.prevMs ? "🏆 record"
        : `+${((run.ms - run.prevMs) / 1000).toFixed(2)}s`;
      return `<tr><td class="num">${i + 1}</td><td></td><td class="num">${fmtRun(run.ms)}</td>` +
        `<td>${vs}</td><td title="${new Date(run.at).toLocaleString()}">${fmtWhen(run.at)}</td></tr>`;
    }).reverse().join("");
    // Labels go in as text.
    [...$("runs-body").rows].forEach((tr, i) => {
      const run = runs[runs.length - 1 - i];
      tr.cells[1].textContent = run.variant ? `${run.label} · ${run.variant}` : run.label;
    });
  }

  $("stats-reset").onclick = () => {
    if (!confirm(`Reset all ${K.one} quiz stats and your missed-${K.many} list?`)) return;
    stats = {};
    bank = new Set();
    saveStats();
    saveBank();
    renderStats();
  };
  for (const th of document.querySelectorAll("#stats-table th[data-key]")) {
    th.onclick = () => {
      const key = th.dataset.key;
      statsSort = statsSort.key === key
        ? { key, dir: -statsSort.dir }
        : { key, dir: key === "name" || key === "region" ? 1 : -1 };
      renderStats();
    };
  }
  $("practice-btn").onclick = () => startSession("Practice · missed", [...bank].filter((c) => COUNTRIES[c]));
  $("slowest-btn").onclick = () => {
    const slowest = Object.keys(stats)
      .filter((code) => COUNTRIES[code] && scoreSecs(code) != null)
      .sort((a, b) => scoreSecs(b) - scoreSecs(a))
      .slice(0, 20)
      ;
    if (slowest.length) startSession("Practice · slowest", slowest);
  };
  $("flag").addEventListener("load", () => {
    // Preload the next flag so it appears instantly (shuffle mode knows what's next).
    if (round && round.queue[0]) new Image().src = flagUrl(round.queue[0]);
  });


  loadKind();
  renderHome();
})();
