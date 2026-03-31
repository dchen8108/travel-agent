(() => {
  const root = document.querySelector(".rules-page");
  if (!root) return;

  const catalogs = window.travelAgentRulesCatalogs ?? { airports: [], airlines: [], weekdays: [] };
  const initialRouteDetails = Array.isArray(window.travelAgentRouteDetails) ? window.travelAgentRouteDetails : [];

  const form = root.querySelector("#rules-form");
  const programIdInput = form?.querySelector('input[name="program_id"]');
  const routeDetailsInput = form?.querySelector('input[name="route_detail_rankings"]');
  const newRuleButton = root.querySelector("[data-new-rule]");
  const ruleCards = Array.from(root.querySelectorAll("[data-rule-card]"));
  const detailList = root.querySelector("[data-detail-list]");
  const addDetailButton = root.querySelector("[data-add-detail]");
  const editorTitle = root.querySelector("[data-editor-title]");
  const editorNote = root.querySelector("[data-editor-note]");
  const duplicateButton = root.querySelector("[data-duplicate-button]");
  const deleteButton = root.querySelector("[data-delete-button]");

  const weekdays = Array.isArray(catalogs.weekdays) ? catalogs.weekdays : [];
  const airportOptions = Array.isArray(catalogs.airports) ? catalogs.airports : [];
  const airlineOptions = Array.isArray(catalogs.airlines) ? catalogs.airlines : [];
  const pickerRegistry = [];

  const draftDefaults = {
    program_id: "draft",
    program_name: "",
    active: true,
    route_detail_rankings: [
      {
        origin_airport: "BUR",
        destination_airport: "SFO",
        weekday: "Monday",
        start_time: "06:00",
        end_time: "10:00",
        airline: "Alaska",
        nonstop_only: true
      }
    ]
  };

  function normalizeDetail(detail = {}) {
    return {
      origin_airport: String(detail.origin_airport || "").trim().toUpperCase(),
      destination_airport: String(detail.destination_airport || "").trim().toUpperCase(),
      weekday: weekdays.includes(detail.weekday) ? detail.weekday : "Monday",
      start_time: String(detail.start_time || "06:00"),
      end_time: String(detail.end_time || "10:00"),
      airline: String(detail.airline || "").trim(),
      nonstop_only: detail.nonstop_only !== false && String(detail.nonstop_only) !== "false"
    };
  }

  function parseRouteDetails(raw) {
    if (!raw) return [];
    try {
      const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
      return Array.isArray(parsed) ? parsed.map(normalizeDetail) : [];
    } catch {
      return [];
    }
  }

  function serializeRouteDetails() {
    if (!routeDetailsInput) return;
    routeDetailsInput.value = JSON.stringify(routeDetails.map((detail) => ({ ...detail })));
  }

  function rankLabel(index) {
    if (index === 0) return "Primary";
    if (index === 1) return "Backup";
    return `Fallback ${index}`;
  }

  function detailSummary(detail) {
    const airline = detail.airline || "Any airline";
    return `${detail.origin_airport || "Origin"} → ${detail.destination_airport || "Destination"} · ${detail.weekday} ${detail.start_time}-${detail.end_time} · ${airline}`;
  }

  function buildSearchText(option) {
    return [option.value, option.label, option.keywords || ""].join(" ").toLowerCase();
  }

  function formatLabel(option) {
    return option.label ? `${option.value} · ${option.label}` : option.value;
  }

  function createSearchPicker({ container, options, value, placeholder, allowEmpty, onChange }) {
    const optionIndex = new Map(options.map((option) => [String(option.value).toLowerCase(), option]));
    let selectedValue = String(value || "");

    container.innerHTML = `
      <div class="multi-select search-select">
        <div class="chip-list" data-chip-list></div>
        <div class="multi-select-input-row">
          <input type="text" data-search placeholder="${placeholder}" autocomplete="off" spellcheck="false">
          <button type="button" class="button ghost" data-clear>Clear</button>
        </div>
        <div class="multi-select-menu" data-menu hidden></div>
        <p class="field-error is-hidden">Choose a supported option from the list.</p>
      </div>
    `;

    const node = container.querySelector(".search-select");
    const chipList = node.querySelector("[data-chip-list]");
    const search = node.querySelector("[data-search]");
    const menu = node.querySelector("[data-menu]");
    const clearButton = node.querySelector("[data-clear]");
    const error = node.querySelector(".field-error");

    function selectedOption() {
      return optionIndex.get(selectedValue.toLowerCase()) || null;
    }

    function clearError() {
      node.classList.remove("invalid");
      error.classList.add("is-hidden");
    }

    function showError() {
      node.classList.add("invalid");
      error.classList.remove("is-hidden");
    }

    function closeMenu() {
      menu.hidden = true;
      node.classList.remove("open");
    }

    function renderChip() {
      chipList.innerHTML = "";
      const option = selectedOption();
      if (!option) {
        const empty = document.createElement("span");
        empty.className = "chip-empty";
        empty.textContent = allowEmpty ? "Any option" : "No selection yet";
        chipList.appendChild(empty);
        return;
      }
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip";
      chip.innerHTML = `<span>${formatLabel(option)}</span>`;
      const remove = document.createElement("span");
      remove.className = "chip-remove";
      remove.setAttribute("aria-hidden", "true");
      remove.textContent = "×";
      chip.appendChild(remove);
      chip.addEventListener("click", () => {
        if (!allowEmpty) return;
        selectedValue = "";
        onChange(selectedValue);
        renderChip();
        clearError();
      });
      chipList.appendChild(chip);
    }

    function matchesForQuery(query) {
      const normalized = String(query || "").trim().toLowerCase();
      if (!normalized) return options.slice(0, 10);
      return options.filter((option) => buildSearchText(option).includes(normalized)).slice(0, 10);
    }

    function renderMenu(query = "") {
      const matches = matchesForQuery(query);
      menu.innerHTML = "";
      if (!matches.length) {
        const empty = document.createElement("div");
        empty.className = "multi-select-empty";
        empty.textContent = "No supported matches.";
        menu.appendChild(empty);
        menu.hidden = false;
        node.classList.add("open");
        return;
      }
      matches.forEach((option) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "multi-select-option";
        button.textContent = formatLabel(option);
        button.addEventListener("mousedown", (event) => {
          event.preventDefault();
          selectedValue = option.value;
          onChange(selectedValue);
          search.value = "";
          renderChip();
          clearError();
          closeMenu();
        });
        menu.appendChild(button);
      });
      menu.hidden = false;
      node.classList.add("open");
    }

    function hasPendingSearch() {
      return String(search.value || "").trim().length > 0;
    }

    renderChip();

    search.addEventListener("focus", () => {
      pickerRegistry.forEach((picker) => {
        if (picker.close !== closeMenu) picker.close();
      });
      renderMenu(search.value);
      clearError();
    });

    search.addEventListener("input", () => {
      renderMenu(search.value);
      clearError();
    });

    search.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        const [first] = matchesForQuery(search.value);
        if (first) {
          selectedValue = first.value;
          onChange(selectedValue);
          search.value = "";
          renderChip();
          clearError();
          renderMenu("");
          return;
        }
        if (hasPendingSearch()) showError();
      } else if (event.key === "Escape") {
        closeMenu();
      }
    });

    search.addEventListener("blur", () => {
      window.setTimeout(() => {
        if (hasPendingSearch()) {
          showError();
        } else {
          clearError();
        }
      }, 120);
    });

    clearButton.addEventListener("click", () => {
      search.value = "";
      if (allowEmpty) {
        selectedValue = "";
        onChange(selectedValue);
      }
      renderChip();
      clearError();
      closeMenu();
      search.focus();
    });

    pickerRegistry.push({
      close: closeMenu,
      hasPendingSearch,
      valid() {
        return allowEmpty || Boolean(selectedValue);
      },
      showError
    });
  }

  let routeDetails = initialRouteDetails.length ? initialRouteDetails.map(normalizeDetail) : draftDefaults.route_detail_rankings.map(normalizeDetail);

  function renderRouteDetails() {
    if (!detailList) return;
    detailList.innerHTML = "";
    pickerRegistry.length = 0;

    routeDetails.forEach((detail, index) => {
      const article = document.createElement("article");
      article.className = "detail-row";
      article.innerHTML = `
        <div class="detail-row-head">
          <div>
            <div class="tracker-slot-title">
              <span class="badge">${rankLabel(index)}</span>
              <strong>${detailSummary(detail)}</strong>
            </div>
            <p class="rules-note">Tracker ${index + 1} of ${routeDetails.length}</p>
          </div>
          <label class="toggle-chip">
            <input type="checkbox" data-detail-field="nonstop_only" ${detail.nonstop_only ? "checked" : ""}>
            <span>Nonstop only</span>
          </label>
        </div>
        <div class="detail-row-grid">
          <label>
            <span>Origin airport</span>
            <div data-picker-role="origin"></div>
          </label>
          <label>
            <span>Destination airport</span>
            <div data-picker-role="destination"></div>
          </label>
          <label>
            <span>Day</span>
            <select data-detail-field="weekday">
              ${weekdays.map((weekday) => `<option value="${weekday}" ${detail.weekday === weekday ? "selected" : ""}>${weekday}</option>`).join("")}
            </select>
          </label>
          <label>
            <span>Airline</span>
            <select data-detail-field="airline">
              <option value="">Any airline</option>
              ${airlineOptions.map((option) => `<option value="${option.value}" ${detail.airline === option.value ? "selected" : ""}>${option.value} · ${option.label}</option>`).join("")}
            </select>
          </label>
          <label>
            <span>Start time</span>
            <input type="time" data-detail-field="start_time" value="${detail.start_time}">
          </label>
          <label>
            <span>End time</span>
            <input type="time" data-detail-field="end_time" value="${detail.end_time}">
          </label>
        </div>
        <div class="detail-row-actions">
          <button type="button" class="button ghost" data-detail-up ${index === 0 ? "disabled" : ""}>Move up</button>
          <button type="button" class="button ghost" data-detail-down ${index === routeDetails.length - 1 ? "disabled" : ""}>Move down</button>
          <button type="button" class="button ghost" data-detail-duplicate>Duplicate</button>
          <button type="button" class="button ghost" data-detail-remove ${routeDetails.length === 1 ? "disabled" : ""}>Remove</button>
        </div>
      `;

      const originContainer = article.querySelector('[data-picker-role="origin"]');
      const destinationContainer = article.querySelector('[data-picker-role="destination"]');
      createSearchPicker({
        container: originContainer,
        options: airportOptions.map((option) => ({ value: option.value, label: option.label, keywords: option.keywords })),
        value: detail.origin_airport,
        placeholder: "Type LAX, BUR, or Burbank...",
        allowEmpty: false,
        onChange(nextValue) {
          routeDetails[index].origin_airport = nextValue;
          serializeRouteDetails();
        }
      });
      createSearchPicker({
        container: destinationContainer,
        options: airportOptions.map((option) => ({ value: option.value, label: option.label, keywords: option.keywords })),
        value: detail.destination_airport,
        placeholder: "Type SFO, OAK, or San Francisco...",
        allowEmpty: false,
        onChange(nextValue) {
          routeDetails[index].destination_airport = nextValue;
          serializeRouteDetails();
        }
      });

      article.querySelectorAll("[data-detail-field]").forEach((control) => {
        control.addEventListener("change", () => {
          const field = control.dataset.detailField;
          if (field === "nonstop_only") {
            routeDetails[index][field] = control.checked;
          } else {
            routeDetails[index][field] = control.value;
          }
          serializeRouteDetails();
          renderRouteDetails();
        });
      });

      article.querySelector("[data-detail-up]")?.addEventListener("click", () => {
        if (index === 0) return;
        [routeDetails[index - 1], routeDetails[index]] = [routeDetails[index], routeDetails[index - 1]];
        serializeRouteDetails();
        renderRouteDetails();
      });

      article.querySelector("[data-detail-down]")?.addEventListener("click", () => {
        if (index >= routeDetails.length - 1) return;
        [routeDetails[index + 1], routeDetails[index]] = [routeDetails[index], routeDetails[index + 1]];
        serializeRouteDetails();
        renderRouteDetails();
      });

      article.querySelector("[data-detail-duplicate]")?.addEventListener("click", () => {
        const clone = JSON.parse(JSON.stringify(routeDetails[index]));
        routeDetails.splice(index + 1, 0, normalizeDetail(clone));
        serializeRouteDetails();
        renderRouteDetails();
      });

      article.querySelector("[data-detail-remove]")?.addEventListener("click", () => {
        if (routeDetails.length === 1) return;
        routeDetails = routeDetails.filter((_, detailIndex) => detailIndex !== index);
        serializeRouteDetails();
        renderRouteDetails();
      });

      detailList.appendChild(article);
    });

    serializeRouteDetails();
  }

  function applyRuleData(rule) {
    if (!form || !rule) return;
    const programNameInput = form.elements.program_name;
    if (programNameInput) programNameInput.value = rule.program_name || "";
    if (programIdInput) programIdInput.value = rule.program_id || "draft";
    const activeCheckbox = form.elements.active;
    if (activeCheckbox) activeCheckbox.checked = rule.active === true || String(rule.active) === "true";

    const isDraft = !rule.program_id || rule.program_id === "draft";
    if (editorTitle) {
      editorTitle.textContent = isDraft ? "New commute rule" : rule.program_name || "Untitled rule";
    }
    if (editorNote) {
      editorNote.textContent = isDraft
        ? "Start with one route option, then add alternates for different airports, times, or airlines."
        : "Rank route options from most preferred to least preferred. The first row is what the app treats as your default target.";
    }
    if (duplicateButton) {
      duplicateButton.disabled = isDraft;
      duplicateButton.textContent = isDraft ? "Save before duplicating" : "Duplicate selected";
    }
    if (deleteButton) {
      deleteButton.disabled = isDraft;
      deleteButton.formAction = isDraft ? "/rules/draft/delete" : `/rules/${rule.program_id}/delete`;
      deleteButton.textContent = isDraft ? "Delete selected" : `Delete ${rule.program_name || "selected rule"}`;
    }

    routeDetails = parseRouteDetails(rule.route_detail_rankings).length
      ? parseRouteDetails(rule.route_detail_rankings)
      : draftDefaults.route_detail_rankings.map(normalizeDetail);
    renderRouteDetails();

    ruleCards.forEach((card) => {
      card.classList.toggle("active", card.dataset.programId === (rule.program_id || "draft"));
    });
  }

  function buildRuleFromCard(card) {
    return {
      program_id: card.dataset.programId || "draft",
      program_name: card.dataset.programName || "",
      active: card.dataset.active === "true",
      route_detail_rankings: card.dataset.routeDetailRankings || JSON.stringify(draftDefaults.route_detail_rankings)
    };
  }

  ruleCards.forEach((card) => {
    card.addEventListener("click", () => {
      applyRuleData(buildRuleFromCard(card));
      form?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  newRuleButton?.addEventListener("click", () => {
    applyRuleData({
      ...draftDefaults,
      route_detail_rankings: JSON.stringify(draftDefaults.route_detail_rankings)
    });
    form?.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  addDetailButton?.addEventListener("click", () => {
    const seed = routeDetails[routeDetails.length - 1] || draftDefaults.route_detail_rankings[0];
    routeDetails.push(normalizeDetail(seed));
    serializeRouteDetails();
    renderRouteDetails();
  });

  deleteButton?.addEventListener("click", (event) => {
    if (deleteButton.disabled) {
      event.preventDefault();
      return;
    }
    if (!window.confirm("Delete this rule and its generated trips?")) {
      event.preventDefault();
    }
  });

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Node)) return;
    if (event.target.closest(".search-select")) return;
    pickerRegistry.forEach((picker) => picker.close());
  });

  form?.addEventListener("submit", (event) => {
    let blocked = false;
    if (!routeDetails.length) {
      blocked = true;
      window.alert("Add at least one ranked route option before saving.");
    }
    pickerRegistry.forEach((picker) => {
      if (picker.hasPendingSearch() || !picker.valid()) {
        picker.showError();
        blocked = true;
      }
    });
    serializeRouteDetails();
    if (blocked) {
      event.preventDefault();
    }
  });

  renderRouteDetails();

  if (programIdInput && !programIdInput.value) {
    programIdInput.value = "draft";
  }
})();
