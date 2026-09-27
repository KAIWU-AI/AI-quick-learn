(() => {
  "use strict";
  const links = Array.from(document.querySelectorAll(".event-link"));
  const panels = Array.from(document.querySelectorAll(".event-panel"));
  if (!links.length) return;
  const seek = document.getElementById("seek");
  const play = document.getElementById("play");
  const previous = document.getElementById("previous");
  const next = document.getElementById("next");
  const filter = document.getElementById("filter");
  const speed = document.getElementById("speed");
  const expand = document.getElementById("expand");
  let current = 0;
  let timer = null;
  let visible = links.map((_, index) => index);

  function stop() {
    if (timer !== null) window.clearInterval(timer);
    timer = null;
    play.textContent = "播放轨迹";
    play.setAttribute("aria-pressed", "false");
  }

  function select(index, scroll = false) {
    if (!Number.isInteger(index) || index < 0 || index >= panels.length) return;
    current = index;
    panels.forEach((panel, i) => { panel.hidden = i !== index; });
    links.forEach((link, i) => {
      if (i === index) link.setAttribute("aria-current", "step");
      else link.removeAttribute("aria-current");
    });
    document.querySelectorAll(".flow-node").forEach(node => {
      node.classList.toggle("active", node.dataset.node === panels[index].dataset.node);
    });
    seek.value = String(index);
    document.getElementById("position").textContent = `${index + 1} / ${panels.length}`;
    previous.disabled = visible.indexOf(index) <= 0;
    next.disabled = visible.indexOf(index) >= visible.length - 1;
    expand.textContent = "展开当前 JSON";
    if (scroll) {
      const nav = links[index].parentElement;
      const offset = links[index].offsetTop - nav.offsetTop;
      nav.scrollTop = offset - nav.clientHeight / 2 + links[index].clientHeight / 2;
    }
  }

  function applyFilter() {
    stop();
    visible = [];
    links.forEach((link, index) => {
      const matches = filter.value === "all" || link.dataset.group === filter.value ||
        (filter.value === "errors" && link.dataset.error === "true");
      link.hidden = !matches;
      if (matches) visible.push(index);
    });
    document.getElementById("no-matches").hidden = visible.length > 0;
    play.disabled = visible.length < 2;
    expand.disabled = visible.length === 0;
    if (visible.length) select(visible.includes(current) ? current : visible[0]);
    else {
      panels.forEach(panel => { panel.hidden = true; });
      links.forEach(link => link.removeAttribute("aria-current"));
      document.querySelectorAll(".flow-node").forEach(node => node.classList.remove("active"));
      document.getElementById("position").textContent = "0 个匹配";
      previous.disabled = next.disabled = true;
    }
  }

  function move(delta) {
    const position = visible.indexOf(current);
    const index = visible[position + delta];
    if (index !== undefined) select(index, true);
  }

  document.querySelectorAll(".playback,.filter-control").forEach(node => { node.hidden = false; });
  document.body.classList.add("js-ready");
  document.querySelectorAll('a[href^="#event-"]').forEach(link => {
    link.addEventListener("click", event => {
      const index = Number(link.getAttribute("href").slice("#event-".length));
      if (!Number.isInteger(index) || !panels[index]) return;
      event.preventDefault();
      stop();
      if (!visible.includes(index)) {
        filter.value = "all";
        applyFilter();
      }
      select(index, true);
      if (!link.classList.contains("event-link")) panels[index].scrollIntoView({block: "nearest"});
    });
  });
  previous.addEventListener("click", () => { stop(); move(-1); });
  next.addEventListener("click", () => { stop(); move(1); });
  filter.addEventListener("change", applyFilter);
  seek.addEventListener("input", () => {
    stop();
    const target = Number(seek.value);
    filter.value = "all";
    applyFilter();
    select(target, true);
  });
  play.addEventListener("click", () => {
    if (timer !== null) { stop(); return; }
    if (current === visible[visible.length - 1]) select(visible[0], true);
    play.textContent = "暂停回放";
    play.setAttribute("aria-pressed", "true");
    timer = window.setInterval(() => {
      move(1);
      if (current === visible[visible.length - 1]) stop();
    }, Number(speed.value));
  });
  speed.addEventListener("change", () => {
    if (timer !== null) { stop(); play.click(); }
  });
  expand.addEventListener("click", () => {
    const details = Array.from(panels[current].querySelectorAll(".tree details"));
    const open = details.some(node => !node.open);
    details.forEach(node => { node.open = open; });
    expand.textContent = open ? "收起当前 JSON" : "展开当前 JSON";
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); });
  const requested = /^#event-(\d+)$/.exec(window.location.hash);
  const initial = requested ? Number(requested[1]) : 0;
  select(initial < panels.length ? initial : 0);
  play.setAttribute("aria-pressed", "false");
})();
