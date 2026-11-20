const thread = document.getElementById("thread");
const form = document.getElementById("chat-form");
const input = document.getElementById("message");
const send = document.getElementById("send");
const prefs = document.getElementById("prefs");
const prompts = document.getElementById("prompts");
const statusEl = document.getElementById("status");
const newChat = document.getElementById("new-chat");
const widget = document.getElementById("widget");
const launcher = document.getElementById("launcher");
const minimize = document.getElementById("minimize");
const widgetName = document.getElementById("widget-name");
const pageNudge = document.getElementById("page-nudge");
const pageNudgeOpen = document.getElementById("page-nudge-open");
const pageNudgeDismiss = document.getElementById("page-nudge-dismiss");
const compareBar = document.getElementById("compare-bar");
const compareHint = document.getElementById("compare-hint");
const comparePicksEl = document.getElementById("compare-picks");
const compareAddEl = document.getElementById("compare-add");
const compareAddLabel = document.getElementById("compare-add-label");
const compareType = document.getElementById("compare-type");
const compareAddGo = document.getElementById("compare-add-go");
const compareGo = document.getElementById("compare-go");
const compareClear = document.getElementById("compare-clear");
const shelf = document.getElementById("shelf");
const shelfNav = document.getElementById("shelf-nav");

const CATEGORIES = [
  {
    title: "Occasions",
    emoji: "✨",
    children: [
      { title: "Office wear", emoji: "💼", text: "I need comfortable outfits for office and daily wear." },
      { title: "Festive", emoji: "🪔", text: "I need an outfit for a festive occasion." },
      { title: "Sports", emoji: "🏃", text: "I need an outfit for sports or gym." },
      { title: "Casuals", emoji: "☀️", text: "I need casual everyday outfits." },
    ],
  },
  {
    title: "Accessories",
    emoji: "💎",
    children: [
      { title: "Necklace", emoji: "📿", text: "Show me necklaces from the catalogue." },
      { title: "Earrings", emoji: "💍", text: "Show me earrings from the catalogue." },
      { title: "Bracelets", emoji: "⭕", text: "Show me bracelets from the catalogue." },
      { title: "Watches", emoji: "⌚", text: "Show me watches from the catalogue." },
    ],
  },
  {
    title: "Footwear",
    emoji: "👟",
    children: [
      { title: "Sports shoes", emoji: "🏃", text: "Suggest sports shoes for running or gym." },
      { title: "Flats", emoji: "🥿", text: "Show me flats from the catalogue." },
      { title: "Sandals", emoji: "👡", text: "Show me sandals from the catalogue." },
      { title: "Casual shoes", emoji: "👟", text: "Show me casual shoes or sneakers from the catalogue." },
    ],
  },
];

const state = {
  userTurns: 0,
  lastProducts: [],
  comparePicks: [],
  busy: false,
  proactiveCount: 0,
  typingStarted: false,
  catalogue: null,
  shelfFilter: "all",
};

let idleTimer = null;
let lingerTimer = null;
let pageTimer = null;
let typingTimer = null;
let memorySessionId = null;

function sessionId() {
  const key = "lookbook.session";
  let id = null;
  try {
    id = localStorage.getItem(key);
  } catch (err) {
    id = null; // storage blocked (private mode): fall back to an in-memory id
  }
  if (!id) {
    id =
      window.crypto && crypto.randomUUID
        ? crypto.randomUUID()
        : "s-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
    try {
      localStorage.setItem(key, id);
    } catch (err) {
      memorySessionId = id;
    }
  }
  return memorySessionId || id;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function chipLabel(item) {
  const emoji = item.emoji ? `${item.emoji} ` : "";
  return `${emoji}${item.title}`;
}

function scrollThread() {
  const body = document.querySelector(".widget-body");
  if (body) body.scrollTop = body.scrollHeight;
}

function widgetOpen() {
  return !widget.classList.contains("closed");
}

function markActivity() {
  clearTimeout(idleTimer);
  clearTimeout(pageTimer);
  clearTimeout(typingTimer);
  launcher.classList.remove("pulse");
  if (pageNudge) pageNudge.hidden = true;
  if (!state.busy) scheduleProactive();
}

function scheduleProactive() {
  clearTimeout(idleTimer);
  clearTimeout(pageTimer);
  if (state.proactiveCount >= 2 || state.busy) return;
  if (!widgetOpen()) {
    pageTimer = setTimeout(onPageLinger, 12000);
    return;
  }
  if (!state.userTurns) return;
  idleTimer = setTimeout(onWidgetIdle, 14000);
}

function onWidgetIdle() {
  if (!widgetOpen() || state.busy || !state.userTurns) return;
  if (document.activeElement === input && input.value.trim()) return;
  if (state.lastProducts.length) {
    showNudge(
      "Still deciding? I can filter cheaper catalogue options or another colour.",
      [
        { title: "Back", emoji: "←", text: "Go back" },
        { title: "💸 Cheaper", text: "Show me cheaper options" },
        { title: "🎨 Another colour", text: "I want to change the colour" },
      ]
    );
  }
}

function onPageLinger() {
  if (widgetOpen() || state.proactiveCount >= 2) return;
  launcher.classList.add("pulse");
  if (pageNudge) pageNudge.hidden = false;
  state.proactiveCount += 1;
}

function showNudge(text, replies) {
  if (!state.userTurns || state.proactiveCount >= 2) return;
  state.proactiveCount += 1;
  document.querySelectorAll(".row.nudge").forEach((el) => el.remove());
  const row = document.createElement("div");
  row.className = "row assistant nudge";
  const bubble = document.createElement("div");
  bubble.className = "bubble nudge-bubble";
  bubble.textContent = `💡 ${text}`;
  row.appendChild(bubble);
  thread.appendChild(row);
  if (replies?.length) renderFollowUps(replies);
  scrollThread();
}

function withBackChip(items) {
  const list = Array.isArray(items) ? items.slice() : [];
  if (
    list.some(
      (item) =>
        String(item.title || "").trim() === "Back" ||
        /^go back$/i.test(String(item.text || "").trim())
    )
  ) {
    return list;
  }
  return [{ title: "Back", emoji: "←", text: "Go back" }, ...list];
}

function renderFollowUps(items) {
  if (!items || !items.length) return false;
  prompts.innerHTML = "";
  withBackChip(items).forEach((item) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "prompt";
    chip.textContent = chipLabel(item);
    chip.addEventListener("click", () => sendMessage(item.text, chip));
    prompts.appendChild(chip);
  });
  return true;
}

function renderPrompts(categoryTitle) {
  prompts.innerHTML = "";
  if (!categoryTitle) {
    CATEGORIES.forEach((category) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "prompt";
      chip.textContent = chipLabel(category);
      chip.addEventListener("click", () => {
        markActivity();
        renderPrompts(category.title);
      });
      prompts.appendChild(chip);
    });
    return;
  }

  const category = CATEGORIES.find((item) => item.title === categoryTitle);
  const back = document.createElement("button");
  back.type = "button";
  back.className = "prompt";
  back.textContent = "← Categories";
  back.addEventListener("click", () => renderPrompts());
  prompts.appendChild(back);

  (category?.children || []).forEach((item) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "prompt";
    chip.textContent = chipLabel(item);
    chip.addEventListener("click", () => sendMessage(item.text, chip));
    prompts.appendChild(chip);
  });
}

function renderWelcome() {
  thread.innerHTML = "";
  const row = document.createElement("div");
  row.className = "row assistant";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent =
    "Hi — I recommend only products from this catalogue. Pick a type below, or tell me the occasion, budget, and size.";
  row.appendChild(bubble);
  thread.appendChild(row);
  renderPrompts();
  scrollThread();
}

function renderPrefs(context) {
  const chips = [];
  if (context.occasion) chips.push(`✨ ${context.occasion}`);
  if (context.activity) chips.push(`🏃 ${context.activity}`);
  if (context.budget_max) chips.push(`🪙 ₹${context.budget_max}`);
  if (context.size) chips.push(`📏 ${context.size}`);
  if (context.colour) chips.push(`🎨 ${context.colour}`);
    if (context.category) chips.push(context.category);
    const type = String(context.product_type || "").trim();
    const occasion = String(context.occasion || "").trim().toLowerCase();
    if (type && type.toLowerCase() !== occasion) chips.push(type);
  if (context.style) chips.push(`◻️ ${context.style}`);
  if (!chips.length) {
    prefs.hidden = true;
    prefs.innerHTML = "";
    return;
  }
  prefs.hidden = false;
  prefs.innerHTML = chips.map((c) => `<span class="chip">${escapeHtml(c)}</span>`).join("");
}

function scrollCarousel(scroller, direction) {
  const amount = scroller.clientWidth || 280;
  scroller.scrollBy({ left: direction * amount, behavior: "smooth" });
}

function isCompareSelected(productId) {
  return state.comparePicks.some((item) => item.id === productId);
}

function comparePool() {
  const byId = new Map();
  (state.lastProducts || []).forEach((product) => {
    if (!product?.product_id) return;
    byId.set(product.product_id, { id: product.product_id, name: product.product_name || product.product_id });
  });
  document.querySelectorAll(".card[data-product-id]").forEach((card) => {
    const id = card.dataset.productId;
    if (!id || byId.has(id)) return;
    const heading = card.querySelector("h3");
    const name = (heading?.textContent || "").replace(/^[^\w]+/, "").trim() || id;
    byId.set(id, { id, name });
  });
  return [...byId.values()];
}

function syncCompareCards() {
  document.querySelectorAll(".card[data-product-id]").forEach((card) => {
    const selected = isCompareSelected(card.dataset.productId);
    card.classList.toggle("selected", selected);
    const btn = card.querySelector(".quick.compare-toggle");
    if (btn) btn.textContent = selected ? "Selected" : "Compare";
  });
}

function syncCompareBar() {
  const count = state.comparePicks.length;
  if (!compareBar) return;
  compareBar.hidden = count === 0;
  const available = comparePool().filter((item) => !isCompareSelected(item.id));
  if (compareHint) {
    if (count >= 2) {
      compareHint.textContent = "Ready — compare only the products you selected.";
    } else if (available.length) {
      compareHint.textContent = "Tap another product below, or type its name / ID.";
    } else {
      compareHint.textContent = "Type another catalogue name or ID to add it.";
    }
  }
  if (comparePicksEl) {
    comparePicksEl.innerHTML = state.comparePicks
      .map(
        (item) =>
          `<button type="button" class="compare-pick" data-id="${escapeHtml(item.id)}" data-name="${escapeHtml(item.name)}" aria-label="Remove ${escapeHtml(item.name)}">${escapeHtml(item.name)} ×</button>`
      )
      .join("");
    comparePicksEl.querySelectorAll(".compare-pick").forEach((btn) => {
      btn.addEventListener("click", () =>
        toggleComparePick({ product_id: btn.dataset.id, product_name: btn.dataset.name })
      );
    });
  }
  if (compareAddEl) {
    compareAddEl.innerHTML = available
      .map(
        (item) =>
          `<button type="button" class="compare-pick add" data-id="${escapeHtml(item.id)}" data-name="${escapeHtml(item.name)}">+ ${escapeHtml(item.name)}</button>`
      )
      .join("");
    compareAddEl.querySelectorAll(".compare-pick.add").forEach((btn) => {
      btn.addEventListener("click", () =>
        toggleComparePick({ product_id: btn.dataset.id, product_name: btn.dataset.name })
      );
    });
  }
  if (compareAddLabel) compareAddLabel.hidden = available.length === 0;
  if (compareGo) compareGo.disabled = count < 2;
  syncCompareCards();
}

function addTypedCompare() {
  const raw = (compareType?.value || "").trim();
  if (!raw) return;
  const lower = raw.toLowerCase();
  const match = comparePool().find(
    (item) => item.id.toLowerCase() === lower || item.name.toLowerCase() === lower || item.name.toLowerCase().includes(lower)
  );
  toggleComparePick(match ? { product_id: match.id, product_name: match.name } : { product_id: raw, product_name: raw });
  if (compareType) compareType.value = "";
}

function clearComparePicks() {
  state.comparePicks = [];
  syncCompareBar();
}

function toggleComparePick(product) {
  const id = product.product_id;
  if (!id) return;
  const index = state.comparePicks.findIndex((item) => item.id === id);
  if (index >= 0) {
    state.comparePicks.splice(index, 1);
  } else if (state.comparePicks.length < 4) {
    state.comparePicks.push({ id, name: product.product_name || id });
  }
  syncCompareBar();
}

function renderComparison(comparison) {
  if (!comparison || !comparison.headers || !comparison.rows) return null;
  const wrap = document.createElement("div");
  wrap.className = "compare-table-wrap";
  const table = document.createElement("table");
  table.className = "compare-table";
  const thead = document.createElement("thead");
  thead.innerHTML = `<tr><th scope="col">Detail</th>${comparison.headers
    .map((header) => `<th scope="col">${escapeHtml(header)}</th>`)
    .join("")}</tr>`;
  const tbody = document.createElement("tbody");
  tbody.innerHTML = comparison.rows
    .map(
      (row) =>
        `<tr><th scope="row">${escapeHtml(row.label)}</th>${(row.values || [])
          .map((value) => `<td>${escapeHtml(value)}</td>`)
          .join("")}</tr>`
    )
    .join("");
  table.append(thead, tbody);
  wrap.appendChild(table);
  return wrap;
}

function formatCardWhy(why) {
  const text = String(why || "")
    .replace(/^Recommended because\s+/i, "")
    .replace(/\.$/, "")
    .trim();
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function renderAssistantBubble(text, handoff) {
  const bubble = document.createElement("div");
  bubble.className = handoff ? "bubble handoff" : "bubble";
  const lines = String(text || "").split("\n");
  let items = [];
  const flushList = () => {
    if (!items.length) return;
    const ul = document.createElement("ul");
    ul.className = "rec-list";
    items.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      ul.appendChild(li);
    });
    bubble.appendChild(ul);
    items = [];
  };
  lines.forEach((line) => {
    const trimmed = line.trim();
    if (/^[-*•–]\s+/.test(trimmed)) {
      items.push(trimmed.replace(/^[-*•–]\s+/, ""));
      return;
    }
    flushList();
    if (!trimmed) return;
    const p = document.createElement("p");
    p.textContent = line;
    bubble.appendChild(p);
  });
  flushList();
  if (!bubble.childNodes.length) bubble.textContent = text || "";
  return bubble;
}

function renderCarousel(products) {
  const wrap = document.createElement("div");
  wrap.className = "carousel-wrap";
  const scroller = document.createElement("div");
  scroller.className = "carousel";
  scroller.setAttribute("role", "list");

  products.forEach((p) => {
    const card = document.createElement("article");
    card.className = "card";
    card.dataset.productId = p.product_id;
    card.setAttribute("role", "listitem");
    const stockClass = String(p.stock_status || "").toLowerCase().includes("low") ? " low" : "";
    const selected = isCompareSelected(p.product_id);
    if (selected) card.classList.add("selected");
    const why = formatCardWhy(p.why);
    card.innerHTML = `
      <div class="card-visual">
        <img src="${escapeHtml(p.image_url || "")}" alt="${escapeHtml(p.product_name || "")}" loading="lazy">
      </div>
      <div class="card-body">
        <h3>${escapeHtml(p.product_name)}</h3>
        <p class="card-id">${escapeHtml(p.product_id)}</p>
        <div class="meta">
          <span class="price">₹${escapeHtml(p.price_inr)}</span>
          ${p.colour ? `<span>${escapeHtml(p.colour)}</span>` : ""}
          ${p.sizes ? `<span>Sizes ${escapeHtml(p.sizes)}</span>` : ""}
          <span class="stock${stockClass}">${escapeHtml(p.stock_status)}</span>
        </div>
        ${p.key_features ? `<p class="features">${escapeHtml(p.key_features)}</p>` : ""}
        ${why ? `<p class="why"><span>Why it matches</span>${escapeHtml(why)}</p>` : ""}
        <div class="card-actions">
          <button type="button" class="quick primary" data-msg="Checkout ${escapeHtml(p.product_name)}">Checkout</button>
          <button type="button" class="quick compare-toggle">${selected ? "Selected" : "Compare"}</button>
        </div>
      </div>
    `;
    const img = card.querySelector("img");
    if (img) img.addEventListener("error", () => img.remove());
    const buyBtn = card.querySelector(".quick[data-msg]");
    if (buyBtn) buyBtn.addEventListener("click", () => sendMessage(buyBtn.dataset.msg, buyBtn));
    const compareBtn = card.querySelector(".compare-toggle");
    if (compareBtn) compareBtn.addEventListener("click", () => toggleComparePick(p));
    card.addEventListener("pointerenter", () => {
      clearTimeout(lingerTimer);
      lingerTimer = setTimeout(() => {
        showNudge(
          `Still looking at ${p.product_name}? Pick another catalogue product with Compare, or ask for a cheaper option.`,
          [
            { title: "Checkout", text: `Checkout ${p.product_name}` },
            { title: "⚖️ Compare", text: "I want to compare products" },
            { title: "💸 Cheaper", text: "Show me cheaper options" },
          ]
        );
      }, 5000);
    });
    card.addEventListener("pointerleave", () => clearTimeout(lingerTimer));
    scroller.appendChild(card);
  });

  if (products.length > 1) {
    const prev = document.createElement("button");
    prev.type = "button";
    prev.className = "carousel-nav prev";
    prev.setAttribute("aria-label", "Previous product");
    prev.textContent = "‹";
    prev.addEventListener("click", () => scrollCarousel(scroller, -1));
    const next = document.createElement("button");
    next.type = "button";
    next.className = "carousel-nav next";
    next.setAttribute("aria-label", "Next product");
    next.textContent = "›";
    next.addEventListener("click", () => scrollCarousel(scroller, 1));
    wrap.append(prev, scroller, next);
  } else {
    wrap.append(scroller);
  }
  return wrap;
}

function productsNamedInReply(text, products) {
  const lower = String(text || "").toLowerCase();
  const hits = [];
  (products || []).forEach((p) => {
    const name = String(p.product_name || "").trim().toLowerCase();
    const id = String(p.product_id || "").trim().toLowerCase();
    let idx = name ? lower.indexOf(name) : -1;
    if (id) {
      const idIdx = lower.indexOf(id);
      if (idIdx !== -1 && (idx === -1 || idIdx < idx)) idx = idIdx;
    }
    if (idx !== -1) hits.push({ idx, p });
  });
  hits.sort((a, b) => a.idx - b.idx);
  const seen = new Set();
  return hits
    .map((h) => h.p)
    .filter((p) => {
      const id = p.product_id;
      if (!id || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
}

function appendMessage(role, text, products, handoff, comparison, confirmation) {
  const row = document.createElement("div");
  row.className = `row ${role}`;
  const bubble =
    role === "assistant" ? renderAssistantBubble(text, handoff) : document.createElement("div");
  if (role !== "assistant") {
    bubble.className = "bubble";
    bubble.textContent = text;
  }
  row.appendChild(bubble);

  if (confirmation) {
    row.appendChild(renderOrderConfirmation(confirmation));
    thread.appendChild(row);
    scrollThread();
    return;
  }

  const table = comparison ? renderComparison(comparison) : null;
  if (table) row.appendChild(table);
  const shown = table ? [] : productsNamedInReply(text, products);
  if (shown.length) {
    row.appendChild(renderCarousel(shown));
  }

  thread.appendChild(row);
  scrollThread();
}

function maybeAttachCompare(message) {
  if (!state.comparePicks.length) return message;
  if (/\bcompare\b/i.test(message)) return message;
  if (
    /^(show me|i need|i want to change|i want to buy|my maximum|size |colour |it'?s for|yes,? please|no,? skip)/i.test(
      message
    )
  ) {
    return message;
  }
  const ids = state.comparePicks.map((item) => item.id).join(" and ");
  return `compare ${ids} and ${message}`;
}

function optionButtons() {
  return document.querySelectorAll(
    "#prompts .prompt, .card-actions .quick, .carousel-nav, #compare-go, #compare-clear, #compare-add-go, .look-ask, .look-checkout, .type-ask, .cat-ask"
  );
}

function setBusy(busy, selectedButton) {
  state.busy = busy;
  send.disabled = busy;
  input.disabled = busy;
  if (compareType) compareType.disabled = busy;
  optionButtons().forEach((btn) => {
    const chosen = Boolean(busy && selectedButton && btn === selectedButton);
    btn.disabled = busy;
    btn.classList.toggle("is-selected", chosen);
    btn.setAttribute("aria-disabled", busy ? "true" : "false");
  });
  if (prompts) prompts.classList.toggle("is-busy", busy);
  if (!busy) {
    document.querySelectorAll(".is-selected").forEach((el) => el.classList.remove("is-selected"));
  }
}

async function sendMessage(text, selectedButton) {
  const message = maybeAttachCompare(text.trim());
  if (!message || state.busy) return;
  document.querySelectorAll(".row.nudge").forEach((el) => el.remove());
  state.userTurns += 1;
  markActivity();
  appendMessage("user", message);
  input.value = "";
  autoSize();
  setBusy(true, selectedButton);
  const typing = document.createElement("div");
  typing.className = "typing";
  typing.id = "typing";
  typing.textContent = "Looking through the catalogue…";
  thread.appendChild(typing);
  scrollThread();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId() }),
    });
    if (!res.ok) {
      const err = new Error("Chat failed");
      err.status = res.status;
      throw err;
    }
    const data = await res.json();
    typing.remove();
    state.lastProducts = data.products || [];
    if (data.comparison) clearComparePicks();
    appendMessage("assistant", data.reply, data.products, data.handoff, data.comparison, data.confirmation);
    renderPrefs(data.context || {});
    if (!renderFollowUps(data.follow_ups)) {
      renderPrompts();
    }
  } catch (err) {
    typing.remove();
    appendMessage(
      "assistant",
      err && err.status === 422
        ? "That message couldn’t be processed — please keep it under 1000 characters."
        : "I couldn’t reach the assistant. Please try again."
    );
  } finally {
    setBusy(false);
    input.focus();
    scheduleProactive();
  }
}

function autoSize() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 96)}px`;
}

function setOpen(open) {
  widget.classList.toggle("closed", !open);
  document.body.classList.toggle("chat-open", open);
  launcher.hidden = open;
  launcher.classList.remove("pulse");
  if (pageNudge) pageNudge.hidden = true;
  if (open) input.focus();
  scheduleProactive();
}

async function resetSession({ welcome = false } = {}) {
  try {
    await fetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId() }),
    });
  } catch (err) {
    /* offline: still clear the screen; the server session is reset on the next successful call */
  }
  state.userTurns = 0;
  state.lastProducts = [];
  state.proactiveCount = 0;
  clearComparePicks();
  renderPrefs({});
  if (welcome) renderWelcome();
}

async function askInChat(text, selectedButton) {
  if (!text || state.busy) return;
  setOpen(true);
  await resetSession();
  if (thread) thread.innerHTML = "";
  sendMessage(text, selectedButton);
}

function productAskText(product) {
  const name = product.product_name || product.product_id;
  const id = product.product_id ? ` (${product.product_id})` : "";
  return `Tell me about ${name}${id} from the catalogue.`;
}

function typeAskText(category, productType) {
  const type = String(productType || "").toLowerCase();
  if (type.includes("necklace")) return "Show me necklaces from the catalogue.";
  if (/(earring|jhumka|stud|hoop)/.test(type)) return "Show me earrings from the catalogue.";
  if (/(bracelet|bangle)/.test(type)) return "Show me bracelets from the catalogue.";
  if (type.includes("watch")) return "Show me watches from the catalogue.";
  if (type.includes("flat")) return "Show me flats from the catalogue.";
  if (type.includes("sandal")) return "Show me sandals from the catalogue.";
  if (/(sneaker|casual shoe)/.test(type)) return "Show me casual shoes or sneakers from the catalogue.";
  if (/(running|sport|training|trail|walking)/.test(type)) return "Suggest sports shoes for running or gym.";
  if (category === "Ethnic wear") return `Show me ${productType} from the catalogue.`;
  if (category === "Western wear") return `Show me ${productType} from the catalogue.`;
  return `Show me ${productType || category} from the catalogue.`;
}

function renderShelfNav(categories, total) {
  if (!shelfNav) return;
  const filters = [{ key: "all", label: `All ${total}` }].concat(
    (categories || []).map((group) => ({
      key: group.category,
      label: `${group.emoji || ""} ${group.category} ${group.count}`.trim(),
    }))
  );
  shelfNav.innerHTML = "";
  filters.forEach((item) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "shelf-filter" + (state.shelfFilter === item.key ? " is-active" : "");
    btn.textContent = item.label;
    btn.addEventListener("click", () => {
      state.shelfFilter = item.key;
      renderShelf();
    });
    shelfNav.appendChild(btn);
  });
}

function renderShelf() {
  if (!shelf || !state.catalogue) return;
  const categories = state.catalogue.categories || [];
  renderShelfNav(categories, state.catalogue.count || 0);
  const shown = categories.filter((group) => state.shelfFilter === "all" || group.category === state.shelfFilter);
  shelf.innerHTML = "";
  if (!shown.length) {
    shelf.innerHTML = `<p class="shelf-status">No catalogue products in this category.</p>`;
    return;
  }
  shown.forEach((group) => {
    const section = document.createElement("section");
    section.className = "shelf-section";
    section.id = `cat-${group.category.replace(/\s+/g, "-").toLowerCase()}`;
    const heading = document.createElement("div");
    heading.className = "shelf-heading";
    heading.innerHTML = `
      <div>
        <h2>${escapeHtml(group.emoji || "🛍️")} ${escapeHtml(group.category)}</h2>
        <p>${group.count} product${group.count === 1 ? "" : "s"} from the spreadsheet</p>
      </div>
    `;
    const catAsk = document.createElement("button");
    catAsk.type = "button";
    catAsk.className = "cat-ask";
    catAsk.textContent = "Chat about these";
    catAsk.addEventListener("click", () =>
      askInChat(`Show me ${String(group.category).toLowerCase()} from the catalogue.`, catAsk)
    );
    heading.appendChild(catAsk);
    section.appendChild(heading);

    (group.types || []).forEach((block) => {
      const typeWrap = document.createElement("div");
      typeWrap.className = "shelf-type";
      const typeHead = document.createElement("h3");
      typeHead.innerHTML = `<span>${escapeHtml(block.product_type)} <span>${block.count || (block.products || []).length}</span></span>`;
      const typeAsk = document.createElement("button");
      typeAsk.type = "button";
      typeAsk.className = "type-ask";
      typeAsk.textContent = "Chat about this type";
      typeAsk.addEventListener("click", () => askInChat(typeAskText(group.category, block.product_type), typeAsk));
      typeHead.appendChild(typeAsk);
      typeWrap.appendChild(typeHead);

      const grid = document.createElement("div");
      grid.className = "look-grid";
      (block.products || []).forEach((product) => {
        const card = document.createElement("article");
        card.className = "look";
        card.innerHTML = `
          <div class="look-visual">
            <img src="${escapeHtml(product.image_url || "")}" alt="${escapeHtml(product.product_name || "")}" loading="lazy">
          </div>
          <div class="look-body">
            <h4>${escapeHtml(product.product_name)}</h4>
            <div class="look-meta">
              <span class="price">₹${escapeHtml(product.price_inr)}</span>
              <span>${escapeHtml(product.colour)}</span>
              <span>${escapeHtml(product.stock_status)}</span>
            </div>
            <p class="look-meta">${escapeHtml(product.product_id)} · ${escapeHtml(product.product_type)}</p>
            <div class="look-actions">
              <button type="button" class="look-ask">💬 Chat</button>
              <a class="look-checkout" href="/checkout?product=${encodeURIComponent(product.product_id)}">Checkout</a>
            </div>
          </div>
        `;
        const img = card.querySelector("img");
        if (img) img.addEventListener("error", () => img.remove());
        const ask = card.querySelector(".look-ask");
        ask.addEventListener("click", () => askInChat(productAskText(product), ask));
        grid.appendChild(card);
      });
      typeWrap.appendChild(grid);
      section.appendChild(typeWrap);
    });
    shelf.appendChild(section);
  });
}

async function loadCatalogue() {
  if (!shelf) return;
  try {
    const res = await fetch("/api/catalogue");
    if (!res.ok) throw new Error("catalogue");
    state.catalogue = await res.json();
    renderShelf();
  } catch {
    shelf.innerHTML = `<p class="shelf-status">Could not load the catalogue. Refresh the page to try again.</p>`;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage(input.value);
  }
});

input.addEventListener("input", () => {
  autoSize();
  markActivity();
});

newChat.addEventListener("click", async () => {
  if (state.busy) return;
  await resetSession({ welcome: true });
  input.focus();
  scheduleProactive();
});

compareGo?.addEventListener("click", () => {
  if (state.comparePicks.length < 2) return;
  const ids = state.comparePicks.map((item) => item.id).join(" and ");
  sendMessage(`compare ${ids}`);
});
compareClear?.addEventListener("click", () => clearComparePicks());
compareAddGo?.addEventListener("click", () => addTypedCompare());
compareType?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  addTypedCompare();
});

minimize.addEventListener("click", () => setOpen(false));
launcher.addEventListener("click", () => setOpen(true));
pageNudgeOpen?.addEventListener("click", () => setOpen(true));
pageNudgeDismiss?.addEventListener("click", () => {
  if (pageNudge) pageNudge.hidden = true;
  launcher.classList.remove("pulse");
});

async function boot() {
  renderWelcome();
  loadCatalogue();
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const heading = document.getElementById("bot-heading");
    if (heading && data.heading) {
      heading.textContent = data.heading;
      document.title = data.heading;
    }
    if (data.user_name && widgetName) widgetName.textContent = data.user_name;
    const mode = data.grok
      ? `${data.llm_provider === "groq" ? "Groq" : "AI"} · ${data.llm_model || "LLM"}`
      : "Catalogue replies";
    statusEl.textContent = `${data.products} products · ${mode}`;
  } catch {
    statusEl.textContent = "Offline";
  }
  scheduleProactive();
}

boot();
