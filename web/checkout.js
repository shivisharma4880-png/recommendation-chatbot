const CITIES = ["Mumbai", "Delhi", "Bengaluru", "Hyderabad"];
const PAYMENTS = [
  { title: "UPI", value: "UPI", emoji: "📱" },
  { title: "Card", value: "Card", emoji: "💳" },
  { title: "Cash on delivery", value: "Cash on delivery", emoji: "💵" },
];

const statusEl = document.getElementById("checkout-status");
const panel = document.getElementById("checkout-panel");
const form = document.getElementById("checkout-form");
const done = document.getElementById("checkout-done");
const receipt = document.getElementById("checkout-receipt");
const errorEl = document.getElementById("checkout-error");
const sizeField = document.getElementById("size-field");
const sizeHint = document.getElementById("size-hint");
const sizeChips = document.getElementById("size-chips");
const cityChips = document.getElementById("city-chips");
const paymentChips = document.getElementById("payment-chips");
const nameInput = document.getElementById("order-name");
const cityInput = document.getElementById("order-city");
const citySuggestList = document.getElementById("city-suggest-list");

const state = {
  product: null,
  size: "",
  payment: "",
  cityIndex: -1,
  cityMatches: [],
};

function showError(message) {
  errorEl.hidden = !message;
  errorEl.textContent = message || "";
}

function selectChip(container, value) {
  container.querySelectorAll("button").forEach((btn) => {
    btn.classList.toggle("is-on", btn.dataset.value === value);
  });
}

function addChips(container, items, onPick) {
  container.innerHTML = "";
  items.forEach((item) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "choice-chip";
    btn.dataset.value = item.value;
    btn.textContent = item.emoji ? `${item.emoji} ${item.title}` : item.title;
    btn.addEventListener("click", () => {
      onPick(item.value);
      selectChip(container, item.value);
    });
    container.appendChild(btn);
  });
}

function validName(value) {
  const text = String(value || "").trim();
  return /^[A-Za-z .'-]{2,40}$/.test(text) && /[A-Za-z]/.test(text);
}

function validCity(value) {
  const text = String(value || "").trim();
  return text.length >= 3 && text.length <= 80;
}

async function loadProduct() {
  const productId = new URLSearchParams(location.search).get("product") || "";
  if (!productId) {
    statusEl.textContent = "Choose a product from the catalogue to check out.";
    return;
  }
  try {
    const res = await fetch(`/api/product/${encodeURIComponent(productId)}`);
    if (res.status === 404) {
      statusEl.textContent = "That product is not in the catalogue. Go back and pick another item.";
      return;
    }
    if (!res.ok) throw new Error("product");
    const product = await res.json();
    state.product = product;
    renderProduct(product);
  } catch {
    statusEl.textContent = "Could not load this product. Refresh the page to try again.";
  }
}

function renderProduct(product) {
  statusEl.hidden = true;
  panel.hidden = false;
  document.getElementById("checkout-name").textContent = product.product_name || "";
  document.getElementById("checkout-meta").innerHTML = `
    <span class="price">₹${product.price_inr}</span>
    <span>${product.colour || ""}</span>
    <span>${product.stock_status || ""}</span>
  `;
  document.getElementById("checkout-id").textContent = `${product.product_id} · ${product.product_type || ""}`;
  const img = document.getElementById("checkout-image");
  img.alt = product.product_name || "";
  img.src = product.image_url || "";
  img.addEventListener("error", () => img.remove());

  const options = product.size_options || [];
  if (product.one_size || !options.length) {
    state.size = product.sizes || "One size";
    sizeHint.textContent = `Listed size: ${state.size}`;
    sizeChips.hidden = true;
  } else {
    sizeHint.textContent = "Pick a listed size.";
    addChips(
      sizeChips,
      options.map((size) => ({ title: size, value: size })),
      (value) => {
        state.size = value;
      }
    );
  }

  addChips(cityChips, CITIES.map((city) => ({ title: city, value: city })), (value) => {
    pickCity(value, { fromChip: true });
  });
  addChips(paymentChips, PAYMENTS, (value) => {
    state.payment = value;
  });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const product = state.product;
  if (!product) return;
  const options = product.size_options || [];
  if (options.length && !state.size) {
    showError("Pick a listed size.");
    return;
  }
  if (!validName(nameInput.value)) {
    showError("Enter the name to put on this order.");
    return;
  }
  if (!validCity(cityInput.value)) {
    showError("Enter the city to deliver to.");
    return;
  }
  if (!state.payment) {
    showError("Pick UPI, card, or cash on delivery.");
    return;
  }
  showError("");
  const confirmation = {
    reference: `ORD-${product.product_id}`,
    status: "confirmed",
    product_id: product.product_id,
    product_name: product.product_name,
    price_inr: product.price_inr,
    colour: product.colour,
    size: state.size || product.sizes,
    name: nameInput.value.trim(),
    address: cityInput.value.trim(),
    payment: state.payment,
    stock_status: product.stock_status,
    image_url: product.image_url,
    emoji: product.emoji,
  };
  panel.hidden = true;
  done.hidden = false;
  receipt.innerHTML = "";
  receipt.appendChild(renderOrderConfirmation(confirmation));
  window.scrollTo({ top: 0, behavior: "smooth" });
});

function escapeCityHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function markCityMatch(city, query) {
  const q = String(query || "").trim();
  const lower = city.toLowerCase();
  const needle = q.toLowerCase();
  let start = lower.startsWith(needle) ? 0 : -1;
  if (start < 0) {
    const parts = city.split(/([\s-]+)/);
    let offset = 0;
    for (const part of parts) {
      if (part.toLowerCase().startsWith(needle)) {
        start = offset;
        break;
      }
      offset += part.length;
    }
  }
  if (start < 0) return escapeCityHtml(city);
  const end = start + q.length;
  return `${escapeCityHtml(city.slice(0, start))}<strong>${escapeCityHtml(city.slice(start, end))}</strong>${escapeCityHtml(city.slice(end))}`;
}

function hideCitySuggest() {
  state.cityIndex = -1;
  state.cityMatches = [];
  citySuggestList.hidden = true;
  citySuggestList.innerHTML = "";
  cityInput.setAttribute("aria-expanded", "false");
  cityInput.removeAttribute("aria-activedescendant");
}

function highlightCityOption(index) {
  const items = [...citySuggestList.querySelectorAll(".city-suggest-item")];
  items.forEach((item, i) => {
    const on = i === index;
    item.classList.toggle("is-active", on);
    if (on) cityInput.setAttribute("aria-activedescendant", item.id);
  });
}

function renderCitySuggest(query) {
  const matches = typeof suggestIndianCities === "function" ? suggestIndianCities(query, 12) : [];
  state.cityMatches = matches;
  state.cityIndex = matches.length ? 0 : -1;
  if (!matches.length) {
    hideCitySuggest();
    return;
  }
  citySuggestList.hidden = false;
  cityInput.setAttribute("aria-expanded", "true");
  citySuggestList.innerHTML = matches
    .map(
      (city, i) =>
        `<li><button type="button" class="city-suggest-item${i === 0 ? " is-active" : ""}" id="city-option-${i}" role="option" aria-label="${escapeCityHtml(city)}" data-city="${escapeCityHtml(city)}">${markCityMatch(city, query)}</button></li>`
    )
    .join("");
  if (state.cityIndex >= 0) cityInput.setAttribute("aria-activedescendant", `city-option-${state.cityIndex}`);
}

function pickCity(city, { fromChip } = {}) {
  cityInput.value = city;
  const match = CITIES.find((item) => item.toLowerCase() === String(city).trim().toLowerCase());
  selectChip(cityChips, match || "");
  hideCitySuggest();
  if (!fromChip) cityInput.focus();
}

function syncCityChips() {
  const match = CITIES.find((city) => city.toLowerCase() === cityInput.value.trim().toLowerCase());
  selectChip(cityChips, match || "");
}

cityInput.addEventListener("input", () => {
  syncCityChips();
  renderCitySuggest(cityInput.value);
});

cityInput.addEventListener("keydown", (event) => {
  if (citySuggestList.hidden || !state.cityMatches.length) return;
  if (event.key === "ArrowDown") {
    event.preventDefault();
    state.cityIndex = (state.cityIndex + 1) % state.cityMatches.length;
    highlightCityOption(state.cityIndex);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    state.cityIndex = (state.cityIndex - 1 + state.cityMatches.length) % state.cityMatches.length;
    highlightCityOption(state.cityIndex);
  } else if (event.key === "Enter" && state.cityIndex >= 0) {
    event.preventDefault();
    pickCity(state.cityMatches[state.cityIndex]);
  } else if (event.key === "Escape") {
    hideCitySuggest();
  }
});

citySuggestList.addEventListener("mousedown", (event) => {
  const btn = event.target.closest(".city-suggest-item");
  if (!btn) return;
  event.preventDefault();
  pickCity(btn.dataset.city);
});

cityInput.addEventListener("blur", () => {
  window.setTimeout(hideCitySuggest, 120);
});

loadProduct();
