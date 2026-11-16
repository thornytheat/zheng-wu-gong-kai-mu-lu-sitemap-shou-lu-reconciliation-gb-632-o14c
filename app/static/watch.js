/* 变更监测：表头排序、打印，导出链接跟随筛选 */
(function () {
  SitemapAudit.bindSortable("change-table");

  const printButton = document.getElementById("print-btn");
  if (printButton) {
    printButton.addEventListener("click", () => window.print());
  }

  const exportLink = document.querySelector('a[href^="/api/watch/regressions.csv"]');
  if (!exportLink) return;
  const base = document.getElementById("base");
  const site = document.getElementById("site");
  const bucket = document.getElementById("bucket");
  const refresh = () => {
    const params = new URLSearchParams();
    if (base) params.set("base", base.value);
    if (site && site.value) params.set("site", site.value);
    if (bucket && bucket.value) params.set("bucket", bucket.value);
    exportLink.setAttribute("href", "/api/watch/regressions.csv?" + params.toString());
  };
  [base, site, bucket].forEach((el) => {
    if (el) el.addEventListener("change", refresh);
  });
  refresh();
})();
