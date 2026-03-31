(() => {
  const root = document.querySelector(".rules-page");
  if (!root) return;

  const DEFAULT_CATALOGS = {
    airports: [
      { value: "BUR", label: "Hollywood Burbank", keywords: "Burbank Los Angeles" },
      { value: "LAX", label: "Los Angeles Intl", keywords: "Los Angeles El Segundo" },
      { value: "SNA", label: "John Wayne / Orange County", keywords: "Orange County Santa Ana Irvine" },
      { value: "ONT", label: "Ontario Intl", keywords: "Inland Empire" },
      { value: "SAN", label: "San Diego Intl", keywords: "San Diego Lindbergh" },
      { value: "SFO", label: "San Francisco Intl", keywords: "San Francisco Bay Area" },
      { value: "OAK", label: "Oakland Intl", keywords: "Oakland East Bay" },
      { value: "SJC", label: "San Jose Mineta Intl", keywords: "San Jose Silicon Valley" },
      { value: "SMF", label: "Sacramento Intl", keywords: "Sacramento" },
      { value: "PSP", label: "Palm Springs Intl", keywords: "Palm Springs Coachella Valley" },
      { value: "LAS", label: "Harry Reid Intl", keywords: "Las Vegas" },
      { value: "PHX", label: "Phoenix Sky Harbor", keywords: "Phoenix" },
      { value: "SEA", label: "Seattle-Tacoma Intl", keywords: "Seattle SeaTac" },
      { value: "PDX", label: "Portland Intl", keywords: "Portland" },
      { value: "DEN", label: "Denver Intl", keywords: "Denver" },
      { value: "AUS", label: "Austin-Bergstrom", keywords: "Austin" },
      { value: "DFW", label: "Dallas/Fort Worth Intl", keywords: "Dallas Fort Worth" },
      { value: "DAL", label: "Dallas Love Field", keywords: "Dallas" },
      { value: "IAH", label: "George Bush Intercontinental", keywords: "Houston" },
      { value: "HOU", label: "William P. Hobby", keywords: "Houston" },
      { value: "MSY", label: "Louis Armstrong New Orleans Intl", keywords: "New Orleans" },
      { value: "ATL", label: "Hartsfield-Jackson Atlanta Intl", keywords: "Atlanta" },
      { value: "CLT", label: "Charlotte Douglas Intl", keywords: "Charlotte" },
      { value: "ORD", label: "Chicago O'Hare Intl", keywords: "Chicago" },
      { value: "MDW", label: "Chicago Midway", keywords: "Chicago" },
      { value: "DCA", label: "Washington National", keywords: "Washington DC" },
      { value: "IAD", label: "Dulles Intl", keywords: "Washington DC" },
      { value: "JFK", label: "John F. Kennedy Intl", keywords: "New York Queens" },
      { value: "LGA", label: "LaGuardia", keywords: "New York Queens" },
      { value: "EWR", label: "Newark Liberty Intl", keywords: "New York Newark" },
      { value: "BOS", label: "Logan Intl", keywords: "Boston" },
      { value: "PHL", label: "Philadelphia Intl", keywords: "Philadelphia" },
      { value: "MCO", label: "Orlando Intl", keywords: "Orlando" },
      { value: "FLL", label: "Fort Lauderdale-Hollywood Intl", keywords: "Fort Lauderdale Miami" },
      { value: "MIA", label: "Miami Intl", keywords: "Miami" },
      { value: "TPA", label: "Tampa Intl", keywords: "Tampa" },
      { value: "RNO", label: "Reno-Tahoe Intl", keywords: "Reno Lake Tahoe" },
      { value: "HNL", label: "Daniel K. Inouye Intl", keywords: "Honolulu Hawaii" },
      { value: "SLC", label: "Salt Lake City Intl", keywords: "Salt Lake City" }
    ],
    airlines: [
      { value: "Alaska", label: "Alaska Airlines", keywords: "AS" },
      { value: "United", label: "United Airlines", keywords: "UA" },
      { value: "Delta", label: "Delta Air Lines", keywords: "DL" },
      { value: "American", label: "American Airlines", keywords: "AA" },
      { value: "Southwest", label: "Southwest Airlines", keywords: "WN" },
      { value: "JetBlue", label: "JetBlue", keywords: "B6" },
      { value: "Hawaiian", label: "Hawaiian Airlines", keywords: "HA" },
      { value: "Spirit", label: "Spirit Airlines", keywords: "NK" },
      { value: "Frontier", label: "Frontier Airlines", keywords: "F9" },
      { value: "Breeze", label: "Breeze Airways", keywords: "MX" },
      { value: "Avelo", label: "Avelo Airlines", keywords: "XP" },
      { value: "JSX", label: "JSX", keywords: "private regional" }
    ],
    weekdays: [
      "Monday",
      "Tuesday",
      "Wednesday",
      "Thursday",
      "Friday",
      "Saturday",
      "Sunday"
    ],
    farePreferences: [
      { value: "flexible", label: "Flexible / travel credit" },
      { value: "main", label: "Main cabin or better" },
      { value: "any", label: "Any fare" },
      { value: "best_value", label: "Best value" },
      { value: "lowest_price", label: "Lowest price" },
      { value: "nonstop", label: "Nonstop-focused" }
    ],
    tripModes: [
      { value: "one_way", label: "One-way" },
      { value: "round_trip", label: "Round-trip" }
    ]
  };

  const catalogs = window.travelAgentRulesCatalogs ?? DEFAULT_CATALOGS;
  const form = root.querySelector("#rules-form");
  const returnPanel = form?.querySelector("[data-return-panel]");
  const tripModeSelect = form?.querySelector("[data-trip-mode]");
  const programIdInput = form?.querySelector('input[name="program_id"]');
  const activeCheckbox = form?.querySelector('input[name="active"][type="checkbox"]');
  const nonstopCheckbox = form?.querySelector('input[name="nonstop_only"][type="checkbox"]');
  const newRuleButton = root.querySelector("[data-new-rule]");
  const ruleCards = Array.from(root.querySelectorAll("[data-rule-card]"));
  const componentNodes = Array.from(root.querySelectorAll("[data-multi-select]"));
  const returnFields = Array.from(form?.querySelectorAll("[data-return-field]") || []);

  const multiSelects = new Map();

  const draftDefaults = {
    program_id: "draft",
    program_name: "",
    active: true,
    trip_mode: "one_way",
    origin_airports: "",
    destination_airports: "",
    outbound_weekday: "Monday",
    outbound_time_start: "06:00",
    outbound_time_end: "10:00",
    return_weekday: "Wednesday",
    return_time_start: "16:00",
    return_time_end: "21:00",
    preferred_airlines: "",
    allowed_airlines: "",
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

  function buildSearchText(option) {
    return [option.value, option.label, option.keywords || ""].join(" ").toLowerCase();
  }

  function formatLabel(option) {
    return option.label ? `${option.value} · ${option.label}` : option.value;
  }

  function createOptionMatcher(catalog) {
    return (query) => {
      const normalized = normalize(query);
      if (!normalized) return catalog.slice();
      return catalog.filter((option) => buildSearchText(option).includes(normalized));
    };
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

  function setTripMode(mode) {
    if (!returnPanel || !tripModeSelect) return;
    const effective = mode === "one_way" ? "one_way" : "round_trip";
    returnPanel.classList.toggle("is-hidden", effective === "one_way");
    returnFields.forEach((field) => {
      field.disabled = effective === "one_way";
      if (effective === "one_way") {
        field.dataset.previousValue = field.value;
        if (field.tagName === "SELECT") {
          field.selectedIndex = 0;
        } else {
          field.value = "";
        }
      } else if (!field.value && field.dataset.previousValue) {
        field.value = field.dataset.previousValue;
      }
    });
  }

  function applyRuleData(rule) {
    if (!form || !rule) return;

    const fields = [
      "program_id",
      "program_name",
      "outbound_weekday",
      "outbound_time_start",
      "outbound_time_end",
      "return_weekday",
      "return_time_start",
      "return_time_end",
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

    if (activeCheckbox) activeCheckbox.checked = String(rule.active) === "true" || rule.active === true;

    if (nonstopCheckbox) nonstopCheckbox.checked = String(rule.nonstop_only) === "true" || rule.nonstop_only === true;

    if (tripModeSelect) {
      tripModeSelect.value = rule.trip_mode || "round_trip";
      setTripMode(tripModeSelect.value);
    }

    multiSelects.get("origin_airports")?.setValues(splitValues(rule.origin_airports));
    multiSelects.get("destination_airports")?.setValues(splitValues(rule.destination_airports));
    multiSelects.get("preferred_airlines")?.setValues(splitValues(rule.preferred_airlines));
    multiSelects.get("allowed_airlines")?.setValues(splitValues(rule.allowed_airlines));

    ruleCards.forEach((card) => {
      card.classList.toggle("active", card.dataset.programId === (rule.program_id || "draft"));
    });
  }

  function buildRuleFromCard(card) {
    return {
      program_id: card.dataset.programId || "draft",
      program_name: card.dataset.programName || "",
      active: card.dataset.active === "true",
      trip_mode: card.dataset.tripMode || "round_trip",
      origin_airports: card.dataset.originAirports || "",
      destination_airports: card.dataset.destinationAirports || "",
      outbound_weekday: card.dataset.outboundWeekday || "Monday",
      outbound_time_start: card.dataset.outboundTimeStart || "06:00",
      outbound_time_end: card.dataset.outboundTimeEnd || "10:00",
      return_weekday: card.dataset.returnWeekday || "Wednesday",
      return_time_start: card.dataset.returnTimeStart || "16:00",
      return_time_end: card.dataset.returnTimeEnd || "21:00",
      preferred_airlines: card.dataset.preferredAirlines || "",
      allowed_airlines: card.dataset.allowedAirlines || "",
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
    const matcher = createOptionMatcher(options);
    const optionIndex = new Map(options.map((option) => [option.value.toLowerCase(), option]));

    function setHidden(values) {
      hidden.value = uniqueValues(values).join("|");
    }

    function getSelectedValues() {
      return splitValues(hidden.value);
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
          removeValue(value);
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
          addValue(option.value);
          search.value = "";
          renderMenu(search.value);
          search.focus();
        });
        menu.appendChild(button);
      });

      menu.hidden = false;
    }

    function addValue(value) {
      const option = optionIndex.get(String(value).toLowerCase());
      if (!option) return;
      const selected = getSelectedValues();
      if (selected.map((item) => item.toLowerCase()).includes(option.value.toLowerCase())) return;
      selected.push(option.value);
      setHidden(selected);
      renderChips();
      clearError();
      hidden.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function removeValue(value) {
      const selected = getSelectedValues().filter((item) => item.toLowerCase() !== String(value).toLowerCase());
      setHidden(selected);
      renderChips();
      hidden.dispatchEvent(new Event("change", { bubbles: true }));
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

    function showError() {
      node.classList.add("invalid");
      error.classList.remove("is-hidden");
    }

    function clearError() {
      node.classList.remove("invalid");
      error.classList.add("is-hidden");
    }

    function hasPendingSearch() {
      return normalize(search.value).length > 0;
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
          addValue(matches[0].value);
          search.value = "";
          renderMenu(search.value);
        } else if (hasPendingSearch()) {
          showError();
        }
      } else if (event.key === "Backspace" && !search.value && getSelectedValues().length) {
        event.preventDefault();
        const selected = getSelectedValues();
        removeValue(selected[selected.length - 1]);
      } else if (event.key === "Escape") {
        menu.hidden = true;
        node.classList.remove("open");
      }
    });

    clearButton.addEventListener("click", () => {
      setValues([]);
      search.focus();
    });

    search.addEventListener("blur", () => {
      if (hasPendingSearch()) {
        showError();
      } else {
        clearError();
      }
    });

    multiSelects.set(field, { setValues, getValues: getSelectedValues, hasPendingSearch, clearError, showError });
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

  if (tripModeSelect) {
    tripModeSelect.addEventListener("change", () => setTripMode(tripModeSelect.value));
  }

  ruleCards.forEach((card) => {
    card.addEventListener("click", () => {
      applyRuleData(buildRuleFromCard(card));
      if (form) {
        form.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });

  newRuleButton?.addEventListener("click", () => {
    applyRuleData(draftDefaults);
    if (form) {
      form.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });

  if (tripModeSelect) {
    setTripMode(tripModeSelect.value);
  }

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
    if (blocked) {
      event.preventDefault();
    }
  });
})();
