/* Dashboard — le strict nécessaire.
   Aucun texte n'est écrit ici : les messages traduits sont lus dans le
   document, qui les a déjà échappés. */
(function () {
  "use strict";

  // Le nombre d'équipes pilote les lignes affichées. Les six lignes existent
  // toujours dans le formulaire : masquer coûte moins cher que reconstruire,
  // et un nom déjà tapé n'est pas perdu si on remonte le curseur.
  var teams = document.querySelector('select[name="num_teams"]');
  if (teams) {
    var sync = function () {
      var wanted = parseInt(teams.value, 10);
      // Une valeur illisible laisserait « index >= NaN » toujours faux, donc
      // les six lignes affichées : on ne touche alors à rien.
      if (!isFinite(wanted)) return;
      Array.prototype.forEach.call(document.querySelectorAll(".team-row"), function (row) {
        row.hidden = parseInt(row.dataset.index, 10) >= wanted;
      });
    };
    teams.addEventListener("change", sync);
    sync();
  }

  var message = document.getElementById("confirm-text");
  Array.prototype.forEach.call(document.querySelectorAll("form.confirm"), function (form) {
    form.addEventListener("submit", function (event) {
      if (message && !window.confirm(message.textContent)) {
        event.preventDefault();
      }
    });
  });
})();
