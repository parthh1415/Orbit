/**
 * ORBIT command-bar integration for the eDEX-UI shell.
 *
 * Hooks into the keyboard's command input field (the text area between
 * CTRL and ALT GR in the bottom bar) and wires it to the ORBIT backend
 * command parser at /api/command/parse.
 *
 * The response text is displayed in the status area (#fs_space_bar h3)
 * and the input is cleared after each submission.
 */

(function orbitCommandBar() {
  "use strict";

  // -----------------------------------------------------------------------
  // Configuration
  // -----------------------------------------------------------------------

  var API_URL = "/api/command/parse";

  // -----------------------------------------------------------------------
  // Locate the keyboard command input element.
  // The eDEX-UI keyboard renders an <input> inside #keyboard.  Try several
  // selectors to be resilient across theme variations.
  // -----------------------------------------------------------------------

  function findCommandInput() {
    // Prefer the dedicated ORBIT command input (React BottomBar)
    var el =
      document.querySelector("#keyboard input") ||
      document.querySelector(".keyboard_input") ||
      document.querySelector("#keyboard_spacebar input") ||
      document.querySelector('[placeholder="COMMAND..."]');
    return el;
  }

  // -----------------------------------------------------------------------
  // Locate the status display element (#fs_space_bar h3).
  // -----------------------------------------------------------------------

  function findStatusDisplay() {
    return document.querySelector("#fs_space_bar h3");
  }

  // -----------------------------------------------------------------------
  // Send the command text to the backend and update the status display.
  // -----------------------------------------------------------------------

  function submitCommand(inputEl, statusEl) {
    var text = (inputEl.value || "").trim();
    if (!text) return;

    var body = JSON.stringify({ command: text });

    fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body,
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        if (statusEl) {
          statusEl.textContent = "> " + (data.output || "OK");
        }
      })
      .catch(function () {
        if (statusEl) {
          statusEl.textContent = "> ERROR: COMMAND FAILED";
        }
      });

    // Clear input immediately so the user can type the next command.
    inputEl.value = "";
  }

  // -----------------------------------------------------------------------
  // Attach the keydown listener.
  // -----------------------------------------------------------------------

  function attach() {
    var inputEl = findCommandInput();
    if (!inputEl) {
      // Retry once after a short delay — the keyboard DOM may not be ready.
      setTimeout(function () {
        var el = findCommandInput();
        if (el) bind(el);
      }, 1000);
      return;
    }
    bind(inputEl);
  }

  function bind(inputEl) {
    var statusEl = findStatusDisplay();

    inputEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        submitCommand(inputEl, statusEl);
      }
    });
  }

  // -----------------------------------------------------------------------
  // Boot — wait for DOMContentLoaded if the document is still loading.
  // -----------------------------------------------------------------------

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attach);
  } else {
    attach();
  }
})();
