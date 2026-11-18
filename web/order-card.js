function escapeOrderHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderOrderConfirmation(data) {
  const el = document.createElement("article");
  el.className = "order-card";
  const price = data.price_inr == null ? "" : `₹${data.price_inr}`;
  const rows = [
    ["📏", "Size", data.size],
    ["👤", "Name", data.name],
    ["📍", "City", data.address],
    ["💳", "Payment", data.payment],
  ].filter((row) => row[2]);
  const image = data.image_url
    ? `<img src="${escapeOrderHtml(data.image_url)}" alt="${escapeOrderHtml(data.product_name || "")}">`
    : `<span class="order-card-emoji">${escapeOrderHtml(data.emoji || "🛍️")}</span>`;
  el.innerHTML = `
    <div class="order-card-banner">
      <span class="order-card-stamp" aria-hidden="true">✅</span>
      <div>
        <p class="order-card-kicker">Order confirmed</p>
        <h3>You're all set</h3>
      </div>
    </div>
    <p class="order-card-ref"><span aria-hidden="true">🔖</span> ${escapeOrderHtml(data.reference || "")}</p>
    <div class="order-card-product">
      <div class="order-card-visual">${image}</div>
      <div>
        <strong>${escapeOrderHtml(data.product_name || "")}</strong>
        <p>${escapeOrderHtml([price, data.colour, data.stock_status].filter(Boolean).join(" · "))}</p>
        <p class="order-card-id">${escapeOrderHtml(data.product_id || "")}</p>
      </div>
    </div>
    <ul class="order-card-rows">
      ${rows
        .map(
          ([icon, label, value]) =>
            `<li><span class="order-card-icon" aria-hidden="true">${icon}</span><span>${label}</span><strong>${escapeOrderHtml(value)}</strong></li>`
        )
        .join("")}
    </ul>
  `;
  const img = el.querySelector("img");
  if (img) img.addEventListener("error", () => img.remove());
  return el;
}
