(() => {
  const tripState = window.travelAgentTripForm;
  const bookingState = window.travelAgentBookingForm;
  const pickerRegistry = [];
  const scheduledSearchDebounceMs = 90;
  let scheduledFilterRequestToken = 0;
  let scheduledFilterAbortController = null;

  function pruneDetachedPickers() {
    for (let index = pickerRegistry.length - 1; index >= 0; index -= 1) {
      if (!pickerRegistry[index].root.isConnected) {
        pickerRegistry.splice(index, 1);
      }
    }
  }

  function registerPicker(root, close) {
    pruneDetachedPickers();
    for (let index = pickerRegistry.length - 1; index >= 0; index -= 1) {
      if (pickerRegistry[index].root === root) {
        pickerRegistry.splice(index, 1);
      }
    }
    pickerRegistry.push({ root, close });
  }

  function closeOtherPickers(currentRoot = null) {
    pruneDetachedPickers();
    pickerRegistry.forEach((picker) => {
      if (!currentRoot || picker.root !== currentRoot) {
        picker.close();
      }
    });
  }

  document.addEventListener("pointerdown", (event) => {
    pruneDetachedPickers();
    pickerRegistry.forEach((picker) => {
      if (!picker.root.contains(event.target)) {
        picker.close();
      }
    });
  });

  function buildSearchText(option) {
    return [option.value, option.label, option.keywords || ""].join(" ").toLowerCase();
  }

  function formatOption(option) {
    return option.label ? `${option.value} · ${option.label}` : option.value;
  }

  function createMultiPicker({
    root,
    options,
    values,
    placeholder,
    emptyText = "No selections",
    maxSelections = Number.POSITIVE_INFINITY,
    onChange
  }) {
    const state = { values: Array.from(values || []) };
    root.innerHTML = `
      <div class="multi-select">
        <div class="chip-list" data-chip-list></div>
        <div class="multi-select-input-row">
          <input type="text" data-search placeholder="${placeholder}" autocomplete="off" spellcheck="false">
        </div>
        <div class="multi-select-menu" data-menu hidden></div>
      </div>
    `;
    const chipList = root.querySelector("[data-chip-list]");
    const search = root.querySelector("[data-search]");
    const menu = root.querySelector("[data-menu]");

    function closeMenu() {
      menu.hidden = true;
    }

    function renderChips() {
      chipList.innerHTML = "";
      state.values.forEach((value, index) => {
        const option = options.find((item) => item.value === value);
        if (!option) return;
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "chip";
        chip.innerHTML = `<span>${formatOption(option)}</span><span class="chip-remove" aria-hidden="true">×</span>`;
        chip.addEventListener("click", () => {
          state.values = state.values.filter((_, itemIndex) => itemIndex !== index);
          renderChips();
          onChange(state.values);
        });
        chipList.appendChild(chip);
      });
      if (!state.values.length) {
        const empty = document.createElement("span");
        empty.className = "chip-empty";
        empty.textContent = emptyText;
        chipList.appendChild(empty);
      }
    }

    function renderMenu(query = "") {
      if (state.values.length >= maxSelections) {
        closeMenu();
        return;
      }
      const normalized = query.trim().toLowerCase();
      const matches = options
        .filter((option) => !state.values.includes(option.value))
        .filter((option) => !normalized || buildSearchText(option).includes(normalized))
        .slice(0, 10);
      menu.innerHTML = "";
      if (!matches.length) {
        closeMenu();
        return;
      }
      matches.forEach((option) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "multi-select-option";
        button.textContent = formatOption(option);
        button.addEventListener("mousedown", (event) => {
          event.preventDefault();
          state.values = [...state.values, option.value];
          renderChips();
          onChange(state.values);
          search.value = "";
          renderMenu("");
        });
        menu.appendChild(button);
      });
      menu.hidden = false;
    }

    renderChips();

    registerPicker(root, closeMenu);

    search.addEventListener("focus", () => {
      closeOtherPickers(root);
      renderMenu(search.value);
    });
    search.addEventListener("input", () => renderMenu(search.value));
    search.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeMenu();
        search.blur();
      }
    });
    search.addEventListener("blur", () => {
      window.setTimeout(() => {
        closeMenu();
      }, 150);
    });
  }

  function createSinglePicker({ field, options }) {
    const hidden = field.querySelector('input[type="hidden"]');
    const root = field.querySelector("[data-picker-root]");
    const state = { value: hidden.value || "" };
    root.innerHTML = `
      <div class="multi-select">
        <div class="chip-list" data-chip-list></div>
        <div class="multi-select-input-row">
          <input type="text" data-search placeholder="Search supported options" autocomplete="off" spellcheck="false">
        </div>
        <div class="multi-select-menu" data-menu hidden></div>
      </div>
    `;
    const chipList = root.querySelector("[data-chip-list]");
    const search = root.querySelector("[data-search]");
    const menu = root.querySelector("[data-menu]");

    function closeMenu() {
      menu.hidden = true;
    }

    function renderChip() {
      chipList.innerHTML = "";
      const option = options.find((item) => item.value === state.value);
      if (!option) {
        const empty = document.createElement("span");
        empty.className = "chip-empty";
        empty.textContent = "No selection";
        chipList.appendChild(empty);
        return;
      }
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip";
      chip.innerHTML = `<span>${formatOption(option)}</span><span class="chip-remove" aria-hidden="true">×</span>`;
      chip.addEventListener("click", () => {
        state.value = "";
        hidden.value = "";
        renderChip();
      });
      chipList.appendChild(chip);
    }

    function renderMenu(query = "") {
      const normalized = query.trim().toLowerCase();
      const matches = options
        .filter((option) => !normalized || buildSearchText(option).includes(normalized))
        .slice(0, 10);
      menu.innerHTML = "";
      if (!matches.length) {
        closeMenu();
        return;
      }
      matches.forEach((option) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "multi-select-option";
        button.textContent = formatOption(option);
        button.addEventListener("mousedown", (event) => {
          event.preventDefault();
          state.value = option.value;
          hidden.value = option.value;
          search.value = "";
          renderChip();
          renderMenu("");
        });
        menu.appendChild(button);
      });
      menu.hidden = false;
    }

    renderChip();
    registerPicker(root, closeMenu);

    search.addEventListener("focus", () => {
      closeOtherPickers(root);
      renderMenu(search.value);
    });
    search.addEventListener("input", () => renderMenu(search.value));
    search.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeMenu();
        search.blur();
      }
    });
    search.addEventListener("blur", () => {
      window.setTimeout(() => {
        closeMenu();
      }, 150);
    });
  }

  if (tripState) {
    const form = document.querySelector("#trip-form");
    const root = form?.querySelector("[data-route-options]");
    const hidden = form?.querySelector('input[name="route_options_json"]');
    const tripKindSelect = form?.querySelector("[data-trip-kind]");
    const anchorWeekdaySelect = form?.querySelector("[data-anchor-weekday]");
    const anchorDateField = form?.querySelector("[data-anchor-date-field]");
    const anchorWeekdayField = form?.querySelector("[data-anchor-weekday-field]");
    const catalogs = tripState.catalogs || {};
    const airports = catalogs.airports || [];
    const airlines = catalogs.airlines || [];

    const weekdays = catalogs.weekdays || ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
    let routeOptions = Array.isArray(tripState.routeOptions) && tripState.routeOptions.length
      ? tripState.routeOptions
      : [{
          route_option_id: "",
          origin_airports: [],
          destination_airports: [],
          airlines: [],
          day_offset: 0,
          start_time: "",
          end_time: ""
        }];

    function currentAnchorWeekday() {
      if (tripKindSelect.value === "weekly") {
        return anchorWeekdaySelect.value || "Monday";
      }
      const anchorDateValue = form.querySelector('input[name="anchor_date"]').value;
      if (!anchorDateValue) return "Monday";
      const date = new Date(`${anchorDateValue}T12:00:00`);
      return weekdays[(date.getDay() + 6) % 7];
    }

    function dayOptions(anchorWeekday) {
      const index = weekdays.indexOf(anchorWeekday);
      return [-1, 0, 1].map((offset) => ({
        value: offset,
        label: `${weekdays[(index + offset + weekdays.length) % weekdays.length]} (${offset === 0 ? "T" : `T${offset > 0 ? `+${offset}` : offset}`})`
      }));
    }

    function serialize() {
      hidden.value = JSON.stringify(routeOptions.map((option) => ({
        route_option_id: option.route_option_id || "",
        origin_airports: option.origin_airports,
        destination_airports: option.destination_airports,
        airlines: option.airlines,
        day_offset: Number(option.day_offset),
        start_time: option.start_time,
        end_time: option.end_time
      })));
    }

    function syncKindVisibility() {
      const oneTime = tripKindSelect.value === "one_time";
      anchorDateField.classList.toggle("is-hidden", !oneTime);
      anchorWeekdayField.classList.toggle("is-hidden", oneTime);
      render();
    }

    function render() {
      root.innerHTML = "";
      const anchorWeekday = currentAnchorWeekday();
      routeOptions.forEach((option, index) => {
        const card = document.createElement("article");
        card.className = "route-option-card";
        card.innerHTML = `
          <div class="card-header">
            <div>
              <strong>Option ${index + 1}</strong>
              <p class="muted">One tracker definition.</p>
            </div>
            <div class="inline-actions">
              <button type="button" class="button ghost" data-move-up ${index === 0 ? "disabled" : ""}>Up</button>
              <button type="button" class="button ghost" data-move-down ${index === routeOptions.length - 1 ? "disabled" : ""}>Down</button>
              <button type="button" class="button danger" data-remove>Remove</button>
            </div>
          </div>
          <div class="form-grid">
            <label><span>Origin airports</span><div data-field="origin_airports"></div></label>
            <label><span>Destination airports</span><div data-field="destination_airports"></div></label>
            <label><span>Airlines</span><div data-field="airlines"></div></label>
            <label><span>Relative day</span><select data-field="day_offset"></select></label>
            <label><span>Departure range start</span><input type="time" data-field="start_time" value="${option.start_time}"></label>
            <label><span>Departure range end</span><input type="time" data-field="end_time" value="${option.end_time}"></label>
          </div>
        `;
        const daySelect = card.querySelector('[data-field="day_offset"]');
        dayOptions(anchorWeekday).forEach((choice) => {
          const optionEl = document.createElement("option");
          optionEl.value = String(choice.value);
          optionEl.textContent = choice.label;
          if (Number(option.day_offset) === choice.value) optionEl.selected = true;
          daySelect.appendChild(optionEl);
        });
        daySelect.addEventListener("change", () => {
          option.day_offset = Number(daySelect.value);
          serialize();
        });
        card.querySelector('[data-field="start_time"]').addEventListener("input", (event) => {
          option.start_time = event.target.value;
          serialize();
        });
        card.querySelector('[data-field="end_time"]').addEventListener("input", (event) => {
          option.end_time = event.target.value;
          serialize();
        });
        createMultiPicker({
          root: card.querySelector('[data-field="origin_airports"]'),
          options: airports,
          values: option.origin_airports,
          placeholder: "Search origins",
          maxSelections: 3,
          onChange(values) {
            option.origin_airports = values;
            serialize();
          }
        });
        createMultiPicker({
          root: card.querySelector('[data-field="destination_airports"]'),
          options: airports,
          values: option.destination_airports,
          placeholder: "Search destinations",
          maxSelections: 3,
          onChange(values) {
            option.destination_airports = values;
            serialize();
          }
        });
        createMultiPicker({
          root: card.querySelector('[data-field="airlines"]'),
          options: airlines,
          values: option.airlines,
          placeholder: "Search airlines",
          onChange(values) {
            option.airlines = values;
            serialize();
          }
        });
        card.querySelector("[data-remove]").addEventListener("click", () => {
          routeOptions = routeOptions.filter((_, itemIndex) => itemIndex !== index);
          if (!routeOptions.length) {
            routeOptions = [{
              route_option_id: "",
              origin_airports: [],
              destination_airports: [],
              airlines: [],
              day_offset: 0,
              start_time: "",
              end_time: ""
            }];
          }
          render();
        });
        card.querySelector("[data-move-up]").addEventListener("click", () => {
          if (index === 0) return;
          [routeOptions[index - 1], routeOptions[index]] = [routeOptions[index], routeOptions[index - 1]];
          render();
        });
        card.querySelector("[data-move-down]").addEventListener("click", () => {
          if (index === routeOptions.length - 1) return;
          [routeOptions[index + 1], routeOptions[index]] = [routeOptions[index], routeOptions[index + 1]];
          render();
        });
        root.appendChild(card);
      });
      serialize();
    }

    document.querySelector("[data-add-route-option]").addEventListener("click", () => {
      routeOptions.push({
        route_option_id: "",
        origin_airports: [],
        destination_airports: [],
        airlines: [],
        day_offset: 0,
        start_time: "",
        end_time: ""
      });
      render();
    });

    tripKindSelect.addEventListener("change", syncKindVisibility);
    form.querySelector('input[name="anchor_date"]').addEventListener("change", render);
    anchorWeekdaySelect.addEventListener("change", render);
    syncKindVisibility();
  }

  if (bookingState) {
    const catalogs = bookingState.catalogs || {};
    document.querySelectorAll("[data-single-picker-field]").forEach((field) => {
      const type = field.dataset.pickerType;
      const options = type === "airline" ? (catalogs.airlines || []) : (catalogs.airports || []);
      createSinglePicker({ field, options });
    });
  }

  const scheduledFiltersState = window.travelAgentTripsFilters;

  function initScheduledFilters(scope = document) {
    const panel = scope.querySelector("[data-scheduled-panel]");
    const form = scope.querySelector("[data-scheduled-filter-form]");
    if (!panel || !form || !scheduledFiltersState || form.dataset.bound === "true") {
      return;
    }
    form.dataset.bound = "true";

    const searchInput = form.querySelector("[data-filter-search]");
    const recurringRoot = form.querySelector("[data-recurring-filter-root]");
    const hiddenInputsRoot = form.querySelector("[data-recurring-hidden-inputs]");
    let resultsShell = panel.querySelector("[data-scheduled-results-shell]");
    const skippedToggle = form.querySelector("[data-skipped-toggle]");
    const skippedInput = form.querySelector("[data-skipped-input]");
    const clearLink = form.querySelector("[data-clear-filters]");
    let debounceTimer = null;

    function selectedRecurringTripIds() {
      return Array.from(hiddenInputsRoot.querySelectorAll('input[name="recurring_trip_id"]'))
        .map((input) => input.value)
        .filter(Boolean);
    }

    function setSelectedRecurringTripIds(values) {
      hiddenInputsRoot.innerHTML = "";
      values.forEach((value) => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "recurring_trip_id";
        input.value = value;
        hiddenInputsRoot.appendChild(input);
      });
    }

    function setSkippedState(enabled) {
      skippedInput.value = enabled ? "true" : "";
      skippedToggle.classList.toggle("is-on", enabled);
      skippedToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
    }

    function buildQuery() {
      const params = new URLSearchParams();
      const query = (searchInput.value || "").trim();
      if (query) {
        params.set("q", query);
      }
      if (skippedInput.value) {
        params.set("show_skipped", "true");
      }
      selectedRecurringTripIds().forEach((value) => {
        params.append("recurring_trip_id", value);
      });
      return params;
    }

    async function refreshScheduledPanel(params) {
      if (!resultsShell) {
        window.location.assign(`/trips${params.toString() ? `?${params.toString()}` : ""}`);
        return;
      }
      const pageQuery = params.toString();
      const pageUrl = `/trips${pageQuery ? `?${pageQuery}` : ""}`;
      const partialParams = new URLSearchParams(params);
      partialParams.set("partial", "scheduled-results");
      const partialUrl = `/trips?${partialParams.toString()}`;
      const requestToken = scheduledFilterRequestToken + 1;
      scheduledFilterRequestToken = requestToken;
      scheduledFilterAbortController?.abort();
      scheduledFilterAbortController = new AbortController();

      try {
        const response = await fetch(partialUrl, {
          headers: { "X-Requested-With": "fetch" },
          signal: scheduledFilterAbortController.signal,
        });
        if (!response.ok) {
          throw new Error(`Unexpected response ${response.status}`);
        }
        if (requestToken !== scheduledFilterRequestToken) {
          return;
        }
        resultsShell.outerHTML = await response.text();
        resultsShell = panel.querySelector("[data-scheduled-results-shell]");
        window.history.replaceState({}, "", pageUrl);
      } catch (error) {
        if (error?.name === "AbortError") {
          return;
        }
        window.location.assign(pageUrl);
      }
    }

    function submitFilters({ debounce = false } = {}) {
      if (debounce) {
        window.clearTimeout(debounceTimer);
        debounceTimer = window.setTimeout(() => {
          refreshScheduledPanel(buildQuery());
        }, scheduledSearchDebounceMs);
        return;
      }
      window.clearTimeout(debounceTimer);
      refreshScheduledPanel(buildQuery());
    }

    createMultiPicker({
      root: recurringRoot,
      options: scheduledFiltersState.recurringOptions || [],
      values: selectedRecurringTripIds(),
      placeholder: "Type to find a recurring trip",
      emptyText: "All recurring trips",
      onChange(values) {
        setSelectedRecurringTripIds(values);
        submitFilters();
      }
    });
    recurringRoot.querySelector(".multi-select")?.classList.add("filter-picker");

    searchInput.addEventListener("input", () => submitFilters({ debounce: true }));
    searchInput.addEventListener("search", () => submitFilters());
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submitFilters();
      }
    });

    skippedToggle.addEventListener("click", () => {
      setSkippedState(!skippedInput.value);
      submitFilters();
    });

    clearLink?.addEventListener("click", (event) => {
      event.preventDefault();
      window.clearTimeout(debounceTimer);
      window.location.assign("/trips");
    });
  }

  initScheduledFilters();
})();
