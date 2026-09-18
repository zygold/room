/* auth-bootstrap.js — 同步阻塞, <head> 里执行.
   配合 <style>html{visibility:hidden}</style> 使用. */
(function(){
  var LOGIN = "/pages/login.html";
  var root = document.documentElement; // <html> — <head> 执行时就存在

  function show() { root.style.visibility = "visible"; }
  function hide() { root.style.visibility = "hidden"; }

  function goto_login() {
    hide(); // 确保跳走前不闪
    var enc = encodeURIComponent(location.pathname + location.search);
    location.replace(LOGIN + "?redirect=" + enc);
  }

  try {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/auth/me", false); // 同步阻塞
    xhr.withCredentials = true;
    try { xhr.send(null); } catch(e) { goto_login(); return; }
    if (xhr.status !== 200) { goto_login(); return; }
    var data = JSON.parse(xhr.responseText || "null");
    if (!data || !data.user) { goto_login(); return; }
    show();
  } catch(e) {
    goto_login();
  }
})();
