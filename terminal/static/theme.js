// 첫 페인트 전에 테마와 왼쪽 메뉴의 폭을 정합니다 (5차 묶음 P2-21, 작업 화면 개편 2026-11-24).  style.css에는 어두운 색 값이 한 벌만
// 있고, 페이지는 늘 data-theme을 답니다.  기본은 어둡게입니다(사용자 결정 2026-11-24).  예전에 저장된 '시스템'(auto)은 한 번만
// '어둡게'로 바꾸고 표식(qse-theme-v2)을 남깁니다: 그 뒤에 사용자가 고른 '시스템'은 그대로 둡니다.  저장을 못 읽으면 어둡게입니다.
// app.js의 applyTheme이 이후의 전환을 맡습니다.
(function () {
  var t = "dark";
  try {
    t = localStorage.getItem("qse-theme") || "dark";
    if (!localStorage.getItem("qse-theme-v2")) {
      if (t === "auto") { t = "dark"; localStorage.setItem("qse-theme", "dark"); }
      localStorage.setItem("qse-theme-v2", "1");
    }
  } catch (e) { /* storage unavailable */ }
  var dark = t === "dark" || (t !== "light" && !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches));
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  // 왼쪽 메뉴: 사용자가 ☰로 고른 폭(qse-nav: full 또는 rail)이 있으면 그것, 없으면 1440px 이상 펼침 · 그 아래 좁은 줄(rail).
  // 1280~1439px도 좁은 줄로 시작해 화면이 두 칸이 됩니다(사용자 결정 2026-11-24).
  // 1023px 이하에서는 서랍과 폰 막대가 대신하므로 이 값은 1024px 이상에서만 쓰입니다.  app.js의 navApply가 이후를 맡습니다.
  var n = null;
  try { n = localStorage.getItem("qse-nav"); } catch (e) { /* storage unavailable */ }
  if (n !== "full" && n !== "rail") n = window.matchMedia && window.matchMedia("(max-width: 1439px)").matches ? "rail" : "full";
  document.documentElement.setAttribute("data-nav", n);
})();
