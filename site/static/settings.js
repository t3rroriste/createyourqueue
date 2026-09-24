/* Page de reglages d'un serveur.

   Le formulaire ne se soumet jamais tout seul : on compare ce qui est a
   l'ecran avec ce qui a ete charge, et on n'envoie que les differences.
   Envoyer tout le reste ferait refuser la page entiere pour un salon
   supprime entre-temps, alors qu'on n'y touchait pas. */

(function () {
  "use strict";

  var form = document.getElementById("settings");
  if (!form) return;

  var guildId = form.dataset.guild;
  var savebar = document.getElementById("savebar");
  var toast   = document.getElementById("toast");
  var saveBtn = document.getElementById("save");
  var resetBtn = document.getElementById("reset");

  var ERRORS = {
    not_logged_in:      "Ta session a expire. Reconnecte-toi.",
    forbidden:          "Tu n'as plus le droit de regler ce serveur.",
    unauthorized:       "Le site n'arrive plus a joindre le bot. Previens un administrateur.",
    guild_not_found:    "Le bot n'est plus sur ce serveur.",
    bot_unreachable:    "Le bot ne repond pas. Reessaie dans une minute.",
    unknown_language:   "Cette langue n'existe pas.",
    invalid_features:   "Une des fonctions n'a pas ete comprise.",
    invalid_resources:  "Un des salons n'a pas ete compris.",
    unknown_resource:   "Un des reglages n'existe plus.",
    invalid_resource_id:"Un identifiant de salon est invalide.",
    wrong_resource_type:"Le salon choisi n'est pas du bon type. Recharge la page.",
    invalid_json:       "La demande n'a pas ete comprise."
  };

  /* Etat de reference : ce que le serveur nous a donne au chargement. */
  function snapshot() {
    var state = { language: null, features: {}, resources: {} };

    var lang = form.querySelector('input[name="language"]:checked');
    state.language = lang ? lang.value : null;

    form.querySelectorAll('input[name^="feature:"]').forEach(function (input) {
      state.features[input.name.slice(8)] = input.checked;
    });

    form.querySelectorAll('select[name^="resource:"]').forEach(function (select) {
      state.resources[select.name.slice(9)] = select.value;
    });

    return state;
  }

  var saved = snapshot();

  function diff() {
    var now = snapshot();
    var payload = {};
    var changed = false;

    if (now.language !== saved.language) {
      payload.language = now.language;
      changed = true;
    }

    var features = {};
    Object.keys(now.features).forEach(function (key) {
      if (now.features[key] !== saved.features[key]) {
        features[key] = now.features[key];
        changed = true;
      }
    });
    if (Object.keys(features).length) payload.features = features;

    var resources = {};
    Object.keys(now.resources).forEach(function (key) {
      if (now.resources[key] !== saved.resources[key]) {
        // "" veut dire « aucun » : l'API attend null ou la chaine vide.
        resources[key] = now.resources[key] || null;
        changed = true;
      }
    });
    if (Object.keys(resources).length) payload.resources = resources;

    return changed ? payload : null;
  }

  function refresh() {
    savebar.hidden = diff() === null;
  }

  function say(message, kind) {
    toast.textContent = message;
    toast.className = "toast " + (kind === "ok" ? "is-ok" : "is-bad");
    toast.hidden = false;
    savebar.hidden = true;
    clearTimeout(say.timer);
    say.timer = setTimeout(function () {
      toast.hidden = true;
      refresh();
    }, 3600);
  }

  /* La classe suit l'etat coche : les navigateurs sans :has gardent le
     meme rendu que les autres. */
  function paintLanguages() {
    form.querySelectorAll(".lang").forEach(function (label) {
      label.classList.toggle("is-on", label.querySelector("input").checked);
    });
  }

  form.addEventListener("change", function () {
    paintLanguages();
    refresh();
  });

  resetBtn.addEventListener("click", function () {
    var lang = form.querySelector('input[name="language"][value="' + saved.language + '"]');
    if (lang) lang.checked = true;

    form.querySelectorAll('input[name^="feature:"]').forEach(function (input) {
      input.checked = saved.features[input.name.slice(8)];
    });
    form.querySelectorAll('select[name^="resource:"]').forEach(function (select) {
      select.value = saved.resources[select.name.slice(9)];
    });

    paintLanguages();
    refresh();
  });

  saveBtn.addEventListener("click", function () {
    var payload = diff();
    if (!payload) return;

    saveBtn.disabled = true;
    saveBtn.textContent = "Enregistrement...";

    fetch("/dashboard/" + guildId, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "same-origin"
    })
      .then(function (response) {
        return response.json()
          .catch(function () { return {}; })
          .then(function (body) { return { ok: response.ok, body: body }; });
      })
      .then(function (result) {
        if (!result.ok) {
          say(ERRORS[result.body.error] || "L'enregistrement a echoue.", "bad");
          return;
        }
        // Ce que le bot a vraiment retenu devient la nouvelle reference.
        saved = snapshot();
        say("Reglages enregistres.", "ok");
      })
      .catch(function () {
        say("Connexion perdue. Reessaie.", "bad");
      })
      .finally(function () {
        saveBtn.disabled = false;
        saveBtn.textContent = "Enregistrer";
      });
  });

  window.addEventListener("beforeunload", function (event) {
    if (diff() === null) return;
    event.preventDefault();
    event.returnValue = "";
  });

  paintLanguages();
})();
