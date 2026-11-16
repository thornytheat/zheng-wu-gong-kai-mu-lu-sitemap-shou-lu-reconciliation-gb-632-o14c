/* 巡检触发与续跑：请求自有接口，按阶段结果刷新页面 */
(function () {
  const button = document.getElementById("run-btn");
  const resume = document.getElementById("resume-btn");
  const status = document.getElementById("run-status");
  const notice = document.getElementById("run-notice");

  async function trigger(url, payload) {
    if (SitemapAudit.state.busy) return;
    SitemapAudit.state.busy = true;
    if (button) button.disabled = true;
    SitemapAudit.setStatus(status, "运行中", "info");
    SitemapAudit.notice(notice, "正在读取样例站。", "info");
    try {
      const data = await SitemapAudit.json(url, { method: "POST", body: JSON.stringify(payload || {}) });
      const tail = data.reused ? "同输入复用结果" : "已完成";
      SitemapAudit.setStatus(status, tail, data.status === "done" ? "ok" : "warn");
      SitemapAudit.notice(notice, data.run_id + " · " + tail + " · 缺陷 " + (data.totals.findings_total || 0), "ok");
      window.setTimeout(() => window.location.reload(), 700);
    } catch (err) {
      SitemapAudit.setStatus(status, "失败", "bad");
      SitemapAudit.notice(notice, err.message + "（" + err.code + "）", "bad");
    } finally {
      SitemapAudit.state.busy = false;
      if (button) button.disabled = false;
    }
  }

  if (button) {
    button.addEventListener("click", () => trigger("/api/crawl", { mode: "full" }));
  }
  if (resume) {
    resume.addEventListener("click", () => {
      const runId = document.querySelector(".runmeta dd");
      const id = runId ? runId.textContent.trim() : "";
      if (!id || id === "—") return;
      trigger("/api/batches/" + encodeURIComponent(id) + "/resume", {});
    });
  }

  document.querySelectorAll("button.resume").forEach((item) => {
    item.addEventListener("click", () => {
      const id = item.dataset.run;
      const box = document.getElementById("batch-notice");
      SitemapAudit.json("/api/batches/" + encodeURIComponent(id) + "/resume", { method: "POST", body: "{}" })
        .then((data) => {
          SitemapAudit.notice(box, data.run_id + " · " + (data.note || "已续跑") + " · 缺陷 " + ((data.totals || {}).findings_total || 0), "ok");
          window.setTimeout(() => window.location.reload(), 700);
        })
        .catch((err) => SitemapAudit.notice(box, err.message + "（" + err.code + "）", "bad"));
    });
  });
})();
