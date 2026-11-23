// 첫 페인트 전에 테마를 정합니다 (5차 묶음 P2-21).  style.css에는 어두운 색 값이 한 벌만 있고, 페이지는 늘 data-theme을 답니다.
// '시스템'이면 기기 설정을 읽습니다.  저장을 못 읽으면 시스템을 따릅니다.  app.js의 applyTheme이 이후의 전환을 맡습니다.
(function () {
  var t = "auto";
  try { t = localStorage.getItem("qse-theme") || "auto"; } catch (e) { /* storage unavailable */ }
  var dark = t === "dark" || (t !== "light" && !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches));
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
})();
