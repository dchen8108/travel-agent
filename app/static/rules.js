(() => {
  const root = document.querySelector(".rules-page");
  if (!root) return;

  const catalogs = window.travelAgentRulesCatalogs ?? { airports: [], airlines: [], weekdays: [] };
  const initialSlots = Array.isArray(window.travelAgentRuleSlots) ? window.travelAgentRuleSlots : [];

  const form = root.querySelector("#rules-form");
  const programIdInput = form?.querySelector('input[name="program_id"]');
  const newRuleButton = root.querySelector("[data-new-rule]");
  const ruleCards = Array.from(root.querySelectorAll("[data-rule-card]"));
  const componentNodes = Array.from(root.querySelectorAll("[data-multi-select]"));
  const slotList = root.querySelector("[data-slot-list]");
  const addSlotButton = root.querySelector("[data-add-slot]");
  const timeSlotInput = form?.querySelector('input[name="time_slot_rankings"]');
  const editorTitle = root.querySelector("[data-editor-title]");
  const editorNote = root.querySelector("[data-editor-note]");
  const duplicateButton = root.querySelector("[data-duplicate-button]");
  const deleteButton = root.querySelector("[data-delete-button]");

  const multiSelects = new Map();

  const draftDefaults = {
    program_id: "draft",
    program_name: "",
    active: true,
    origin_airports: "",
    destination_airports: "",
    time_slot_rankings: JSON.stringify([{ weekday: "Monday", start_time: "06:00", end_time: "10:00" }]),
    airlines: "",
    fare_preference: "flexible",
    nonstop_only: true,
    lookahead_weeks: "8",
    rebook_alert_threshold: "20"
  };

  function splitValues(value) {
    return String(value || "")
      .split("|")
      .map((part) => part.trim())
      .filter(Boolean);
  }

  function uniqueValues(values) {
    return Array.from(new Set(values.filter(Boolean)));
  }

  function normalize(value) {
    return String(value || "").trim().toLowerCase();
  }

  function getCatalog(name) {
    const catalog = catalogs?.[name] ?? [];
    return Array.isArray(catalog) ? catalog : [];
  }

  function weekdays() {
    return Array.isArray(catalogs?.weekdays) ? catalogs.weekdays : [];
  }

  function buildSearchText(option) {
    return [option.value, option.label, option.keywords || ""].join(" ").toLowerCase();
  }

  function formatLabel(option) {
    return option.label ? `${option.value} · ${option.label}` : option.value;
  }

  function closeAllMenus(except = null) {
    componentNodes.forEach((node) => {
      if (node !== except) {
        const menu = node.querySelector("[data-menu]");
        if (menu) menu.hidden = true;
        node.classList.remove("open");
      }
    });
  }

  function parseSlots(raw) {
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  let slots = initialSlots.length ? initialSlots : parseSlots(timeSlotInput?.value || draftDefaults.time_slot_rankings);

  function serializeSlots() {
    if (timeSlotInput) {
      timeSlotInput.value = JSON.stringify(
        slots.map((slot) => ({
          weekday: slot.weekday,
          start_time: slot.start_time,
          end_time: slot.end_time
        }))
      );
    }
  }

  function renderSlots() {
    if (!slotList) return;
    slotList.innerHTML = "";

    slots.forEach((slot, index) => {
      const article = document.createElement("article");
      article.className = "slot-row";
      article.innerHTML = `
        <div class="slot-row-head">
          <strong>${index === 0 ? "Primary" : index === 1 ? "Backup" : `Fallback ${index}`}</strong>
          <span class="badge">#${index + 1}</span>
        </div>
        <div class="slot-row-grid">
          <label>
            <span>Day</span>
            <select data-slot-field="weekday">
              ${weekdays()
                .map((weekday) => `<option value="${weekday}" ${slot.weekday === weekday ? "selected" : ""}>${weekday}</option>`)
                .join("")}
            </select>
          </label>
          <label>
            <span>Start</span>
            <input type="time" data-slot-field="start_time" value="${slot.start_time}">
          </label>
          <label>
            <span>End</span>
            <input type="time" data-slot-field="end_time" value="${slot.end_time}">
          </label>
        </div>
        <div class="slot-row-actions">
          <button type="button" class="button ghost" data-slot-up ${index === 0 ? "disabled" : ""}>Move up</button>
          <button type="button" class="button ghost" data-slot-down ${index === slots.length - 1 ? "disabled" : ""}>Move down</button>
          <button type="button" class="button ghost" data-slot-remove ${slots.length === 1 ? "disabled" : ""}>Remove</button>
        </div>
      `;

      article.querySelectorAll("[data-slot-field]").forEach((control) => {
        control.addEventListener("change", () => {
          const field = control.dataset.slotField;
          slots[index][field] = control.value;
          serializeSlots();
        });
      });

      article.querySelector("[data-slot-up]")?.addEventListener("click", () => {
        if (index === 0) return;
        [slots[index - 1], slots[index]] = [slots[index], slots[index - 1]];
        serializeSlots();
        renderSlots();
      });

      article.querySelector("[data-slot-down]")?.addEventListener("click", () => {
        if (index >= slots.length - 1) return;
        [slots[index + 1], slots[index]] = [slots[index], slots[index + 1]];
        serializeSlots();
        renderSlots();
      });

      article.querySelector("[data-slot-remove]")?.addEventListener("click", () => {
        if (slots.length === 1) return;
        slots = slots.filter((_, slotIndex) => slotIndex !== index);
        serializeSlots();
        renderSlots();
      });

      slotList.appendChild(article);
    });

    serializeSlots();
  }

  function applyRuleData(rule) {
    if (!form || !rule) return;
    const fields = [
      "program_id",
      "program_name",
      "fare_preference",
      "lookahead_weeks",
      "rebook_alert_threshold"
    ];

    fields.forEach((field) => {
      const control = form.elements[field];
      if (control) control.value = rule[field] ?? "";
    });

    if (programIdInput) {
      programIdInput.value = rule.program_id || "draft";
    }

    const isDraft = !rule.program_id || rule.program_id === "draft";
    if (editorTitle) {
      editorTitle.textContent = isDraft ? "New commute rule" : rule.program_name || "Untitled rule";
    }
    if (editorNote) {
      editorNote.textContent = isDraft
        ? "Start a new one-way rule. Save it once, then duplicate or delete it from here."
        : "Airports and airlines are catalog-constrained. Schedule slots are ranked with the first row treated as primary.";
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

    const activeCheckbox = form.elements.active;
    if (activeCheckbox) activeCheckbox.checked = String(rule.active) === "true" || rule.active === true;

    const nonstopCheckbox = form.elements.nonstop_only;
    if (nonstopCheckbox) nonstopCheckbox.checked = String(rule.nonstop_only) === "true" || rule.nonstop_only === true;

    slots = parseSlots(rule.time_slot_rankings || draftDefaults.time_slot_rankings);
    if (!slots.length) {
      slots = parseSlots(draftDefaults.time_slot_rankings);
    }
    renderSlots();

    multiSelects.get("origin_airports")?.setValues(splitValues(rule.origin_airports));
    multiSelects.get("destination_airports")?.setValues(splitValues(rule.destination_airports));
    multiSelects.get("airlines")?.setValues(splitValues(rule.airlines));

    ruleCards.forEach((card) => {
      card.classList.toggle("active", card.dataset.programId === (rule.program_id || "draft"));
    });
  }

  function buildRuleFromCard(card) {
    return {
      program_id: card.dataset.programId || "draft",
      program_name: card.dataset.programName || "",
      active: card.dataset.active === "true",
      origin_airports: card.dataset.originAirports || "",
      destination_airports: card.dataset.destinationAirports || "",
      time_slot_rankings: card.dataset.timeSlotRankings || draftDefaults.time_slot_rankings,
      airlines: card.dataset.airlines || "",
      fare_preference: card.dataset.farePreference || "flexible",
      nonstop_only: card.dataset.nonstopOnly === "true",
      lookahead_weeks: card.dataset.lookaheadWeeks || "8",
      rebook_alert_threshold: card.dataset.rebookAlertThreshold || "20"
    };
  }

  componentNodes.forEach((node) => {
    const field = node.dataset.field;
    const catalogName = node.dataset.catalog;
    const hidden = node.querySelector('input[type="hidden"]');
    const search = node.querySelector("[data-search]");
    const chipList = node.querySelector("[data-chip-list]");
    const menu = node.querySelector("[data-menu]");
    const clearButton = node.querySelector("[data-clear]");
    const error = document.createElement("p");
    error.className = "field-error is-hidden";
    error.textContent = "Select from the supported catalog.";
    node.appendChild(error);
    const options = getCatalog(catalogName);
    const optionIndex = new Map(options.map((option) => [option.value.toLowerCase(), option]));

    function matcher(query) {
      const normalized = normalize(query);
      if (!normalized) return options.slice();
      return options.filter((option) => buildSearchText(option).includes(normalized));
    }

    function setHidden(values) {
      hidden.value = uniqueValues(values).join("|");
    }

    function getSelectedValues() {
      return splitValues(hidden.value);
    }

    function clearError() {
      node.classList.remove("invalid");
      error.classList.add("is-hidden");
    }

    function showError() {
      node.classList.add("invalid");
      error.classList.remove("is-hidden");
    }

    function hasPendingSearch() {
      return normalize(search.value).length > 0;
    }

    function renderChips() {
      chipList.innerHTML = "";
      const selected = getSelectedValues();

      if (!selected.length) {
        const empty = document.createElement("span");
        empty.className = "chip-empty";
        empty.textContent = "No selections yet";
        chipList.appendChild(empty);
        return;
      }

      selected.forEach((value) => {
        const option = optionIndex.get(value.toLowerCase());
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "chip";
        chip.innerHTML = `<span>${option ? formatLabel(option) : value}</span>`;

        const remove = document.createElement("span");
        remove.className = "chip-remove";
        remove.setAttribute("aria-hidden", "true");
        remove.textContent = "×";
        chip.appendChild(remove);
        chip.addEventListener("click", () => {
          const selectedValues = getSelectedValues().filter((item) => item.toLowerCase() !== value.toLowerCase());
          setHidden(selectedValues);
          renderChips();
          search.focus();
        });
        chipList.appendChild(chip);
      });
    }

    function renderMenu(query = "") {
      const matches = matcher(query).slice(0, 10);
      menu.innerHTML = "";
      menu.setAttribute("role", "listbox");

      if (!matches.length) {
        const empty = document.createElement("div");
        empty.className = "multi-select-empty";
        empty.textContent = "No matches in the supported catalog.";
        menu.appendChild(empty);
        menu.hidden = false;
        return;
      }

      matches.forEach((option) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "multi-select-option";
        button.textContent = formatLabel(option);
        button.setAttribute("role", "option");
        button.addEventListener("mousedown", (event) => {
          event.preventDefault();
          const selected = getSelectedValues();
          if (!selected.map((item) => item.toLowerCase()).includes(option.value.toLowerCase())) {
            selected.push(option.value);
            setHidden(selected);
            renderChips();
            clearError();
          }
          search.value = "";
          renderMenu(search.value);
          search.focus();
        });
        menu.appendChild(button);
      });

      menu.hidden = false;
    }

    function setValues(values) {
      const next = uniqueValues(values).filter((value) => optionIndex.has(String(value).toLowerCase()));
      setHidden(next);
      renderChips();
      clearError();
      search.value = "";
      menu.hidden = true;
      node.classList.remove("open");
    }

    renderChips();

    search.addEventListener("focus", () => {
      closeAllMenus(node);
      node.classList.add("open");
      renderMenu(search.value);
      clearError();
    });

    search.addEventListener("input", () => {
      closeAllMenus(node);
      node.classList.add("open");
      renderMenu(search.value);
    });

    search.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        const matches = matcher(search.value);
        if (matches.length) {
          const selected = getSelectedValues();
          const first = matches[0].value;
          if (!selected.map((item) => item.toLowerCase()).includes(first.toLowerCase())) {
            selected.push(first);
            setHidden(selected);
            renderChips();
            clearError();
          }
          search.value = "";
          renderMenu(search.value);
        } else if (hasPendingSearch()) {
          showError();
        }
      } else if (event.key === "Backspace" && !search.value && getSelectedValues().length) {
        event.preventDefault();
        const selected = getSelectedValues();
        setHidden(selected.slice(0, -1));
        renderChips();
      } else if (event.key === "Escape") {
        menu.hidden = true;
        node.classList.remove("open");
      }
    });

    search.addEventListener("blur", () => {
      if (hasPendingSearch()) {
        showError();
      } else {
        clearError();
      }
    });

    clearButton.addEventListener("click", () => {
      setValues([]);
      search.focus();
    });

    multiSelects.set(field, { setValues, hasPendingSearch, clearError, showError });
  });

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Node)) return;
    const activeNode = componentNodes.find((node) => node.contains(target));
    if (activeNode) {
      closeAllMenus(activeNode);
      activeNode.classList.add("open");
      return;
    }
    closeAllMenus();
  });

  ruleCards.forEach((card) => {
    card.addEventListener("click", () => {
      applyRuleData(buildRuleFromCard(card));
      form?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  newRuleButton?.addEventListener("click", () => {
    applyRuleData(draftDefaults);
    form?.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  addSlotButton?.addEventListener("click", () => {
    slots.push({ weekday: "Monday", start_time: "06:00", end_time: "10:00" });
    renderSlots();
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

  renderSlots();

  if (programIdInput && !programIdInput.value) {
    programIdInput.value = "draft";
  }

  form?.addEventListener("submit", (event) => {
    let blocked = false;
    multiSelects.forEach((component) => {
      if (component.hasPendingSearch()) {
        component.showError();
        blocked = true;
      } else {
        component.clearError();
      }
    });

    if (!slots.length) {
      blocked = true;
      window.alert("Add at least one ranked time slot before saving.");
    }

    serializeSlots();
    if (blocked) {
      event.preventDefault();
    }
  });
})();
