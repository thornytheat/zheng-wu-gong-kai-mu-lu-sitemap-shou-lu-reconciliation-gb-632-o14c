/* 缺陷单交互：打印，以及导出链接跟随站点/分类筛选 */
(function () {
  const printButton = document.getElementById("print-btn");
  if (printButton) {
    printButton.addEventListener("click", () => window.print());
  }

  const filters = document.querySelector(".filters select#category");
  const siteSelect = document.querySelector(".filters select#site");
  const exportLink = document.querySelector('a[href^="/api/defects.csv"]');
  if (!exportLink) return;

  const refresh = () => {
    const params = new URLSearchParams();
    if (siteSelect && siteSelect.value) params.set("site", siteSelect.value);
    if (filters && filters.value) params.set("category", filters.value);
    const query = params.toString();
    exportLink.setAttribute("href", "/api/defects.csv" + (query ? "?" + query : ""));
  };

  if (siteSelect) siteSelect.addEventListener("change", refresh);
  if (filters) filters.addEventListener("change", refresh);
  refresh();
})();
