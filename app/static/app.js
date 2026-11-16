/* 共享请求与表格工具：只做展示层（排序、过滤、提示），判定规则全在后端 */
const SitemapAudit = (function () {
  const state = { busy: false };

  async function json(url, options) {
    const response = await fetch(url, Object.assign({ headers: { "content-type": "application/json" } }, options || {}));
    let body = null;
    try {
      body = await response.json();
    } catch (err) {
      body = null;
    }
    if (!response.ok) {
      const message = body && body.message ? body.message : "请求失败 " + response.status;
      const error = new Error(message);
      error.code = body && body.error ? body.error : "E_UNKNOWN";
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function notice(el, text, kind) {
    if (!el) return;
    el.textContent = text;
    el.className = "notice " + (kind || "");
    el.hidden = !text;
  }

  function sortTable(table, columnIndex) {
    const body = table.tBodies[0];
    if (!body) return;
    const rows = Array.from(body.rows);
    const ascending = table.dataset["sort" + columnIndex] !== "asc";
    table.dataset["sort" + columnIndex] = ascending ? "asc" : "desc";
    const value = (row) => {
      const cell = row.cells[columnIndex];
      if (!cell) return "";
      const raw = cell.textContent.trim();
      const number = Number(raw.replace(/,/g, ""));
      return Number.isFinite(number) && raw !== "" ? number : raw;
    };
    rows.sort((a, b) => {
      const left = value(a);
      const right = value(b);
      if (typeof left === "number" && typeof right === "number") {
        return ascending ? left - right : right - left;
      }
      return ascending ? String(left).localeCompare(String(right), "zh") : String(right).localeCompare(String(left), "zh");
    });
    rows.forEach((row) => body.appendChild(row));
  }

  function bindSortable(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    Array.from(table.tHead ? table.tHead.rows[0].cells : []).forEach((cell, index) => {
      cell.style.cursor = "pointer";
      cell.title = "点击排序";
      cell.addEventListener("click", () => sortTable(table, index));
    });
  }

  function setStatus(el, text, kind) {
    if (!el) return;
    el.textContent = text;
    el.className = "tag " + (kind || "");
  }

  return { state, json, notice, bindSortable, setStatus };
})();
