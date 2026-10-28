/* Theme clair ou sombre.

   Par defaut le site suit le reglage du systeme. Des que tu touches au
   bouton, ton choix est retenu dans ce navigateur et prend le dessus. */

(function () {
  "use strict";

  var KEY = "cyq-theme";
  var root = document.documentElement;

  function stored() {
    // Navigation privee ou stockage bloque : on fait sans, sans casser la page.
    try {
      return localStorage.getItem(KEY);
    } catch (e) {
      return null;
    }
  }

  function remember(value) {
    try {
      localStorage.setItem(KEY, value);
    } catch (e) {
      /* tant pis, le choix ne durera que cette page */
    }
  }

  function systemTheme() {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  var choice = stored();
  if (choice === "light" || choice === "dark") {
    root.setAttribute("data-theme", choice);
  } else {
    // Pas de choix : on laisse la CSS suivre le systeme.
    root.removeAttribute("data-theme");
  }

  var button = document.getElementById("theme-toggle");
  if (!button) return;

  button.addEventListener("click", function () {
    var current = root.getAttribute("data-theme") || systemTheme();
    var next = current === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    remember(next);
  });
})();
