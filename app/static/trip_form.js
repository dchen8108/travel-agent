(() => {
  const tripState = window.travelAgentApp?.readJsonScript("trip-form-data");
  const pickers = window.travelAgentPickers;
  if (!tripState || !pickers) {
    return;
  }

  const form = document.querySelector("#trip-form");
  const root = form?.querySelector("[data-route-options]");
  const hidden = form?.querySelector('input[name="route_options_json"]');
  const tripKindInputs = Array.from(form?.querySelectorAll('input[data-trip-kind]') || []);
  const preferenceModeInputs = Array.from(form?.querySelectorAll('input[name="preference_mode"]') || []);
  const anchorWeekdaySelect = form?.querySelector("[data-anchor-weekday]");
  const anchorDateField = form?.querySelector("[data-anchor-date-field]");
  const anchorWeekdayField = form?.querySelector("[data-anchor-weekday-field]");
  const addRouteOptionButton = document.querySelector("[data-add-route-option]");
  if (!form || !root || !hidden || !tripKindInputs.length || !anchorWeekdaySelect || !anchorDateField || !anchorWeekdayField || !addRouteOptionButton) {
    return;
  }

  const catalogs = tripState.catalogs || {};
  const airports = catalogs.airports || [];
  const airlines = catalogs.airlines || [];
  const weekdays = catalogs.weekdays || ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const blankRouteOption = () => ({
    route_option_id: "",
    savings_needed_vs_previous: 0,
    origin_airports: [],
    destination_airports: [],
    airlines: [],
    day_offset: 0,
    start_time: "",
    end_time: "",
    fare_class_policy: "include_basic",
  });

  let routeOptions = Array.isArray(tripState.routeOptions) && tripState.routeOptions.length
    ? tripState.routeOptions
    : [blankRouteOption()];

  function currentPreferenceMode() {
    return preferenceModeInputs.find((input) => input.checked)?.value || tripState.trip?.preference_mode || "equal";
  }

  function currentTripKind() {
    return tripKindInputs.find((input) => input.checked)?.value || tripState.trip?.trip_kind || "weekly";
  }

  function currentAnchorWeekday() {
    if (currentTripKind() === "weekly") {
      return anchorWeekdaySelect.value || "Monday";
    }
    const anchorDateValue = form.querySelector('input[name="anchor_date"]').value;
    if (!anchorDateValue) {
      return "Monday";
    }
    const parsedDate = new Date(`${anchorDateValue}T12:00:00`);
    return weekdays[(parsedDate.getDay() + 6) % 7];
  }

  function dayOptions(anchorWeekday) {
    const index = weekdays.indexOf(anchorWeekday);
    return [-1, 0, 1].map((offset) => ({
      value: offset,
      label: `${weekdays[(index + offset + weekdays.length) % weekdays.length]} (${offset === 0 ? "T" : `T${offset > 0 ? `+${offset}` : offset}`})`,
    }));
  }

  function serialize() {
    hidden.value = JSON.stringify(routeOptions.map((option) => ({
      route_option_id: option.route_option_id || "",
      savings_needed_vs_previous: Number(option.savings_needed_vs_previous || 0),
      origin_airports: option.origin_airports,
      destination_airports: option.destination_airports,
      airlines: option.airlines,
      day_offset: Number(option.day_offset),
      start_time: option.start_time,
      end_time: option.end_time,
      fare_class_policy: option.fare_class_policy || "include_basic",
    })));
  }

  function syncKindVisibility() {
    const oneTime = currentTripKind() === "one_time";
    anchorDateField.classList.toggle("is-hidden", !oneTime);
    anchorWeekdayField.classList.toggle("is-hidden", oneTime);
    render();
  }

  function render() {
    root.innerHTML = "";
    const anchorWeekday = currentAnchorWeekday();
    const preferenceMode = currentPreferenceMode();
    const biasEnabled = preferenceMode === "ranked_bias";
    routeOptions.forEach((option, index) => {
      const pairwiseBias = index === 0 ? 0 : Number(option.savings_needed_vs_previous || 0);
      const card = document.createElement("article");
      card.className = "route-option-card";
      card.innerHTML = `
        <div class="card-header">
          <div>
            <strong>Option ${index + 1}</strong>
          </div>
          <div class="inline-actions">
            <button type="button" class="button ghost" data-move-up ${index === 0 ? "disabled" : ""}>Up</button>
            <button type="button" class="button ghost" data-move-down ${index === routeOptions.length - 1 ? "disabled" : ""}>Down</button>
            <button type="button" class="button danger" data-remove>Remove</button>
          </div>
        </div>
        <div class="form-grid">
          <div class="field"><span>Origin airports</span><div data-field="origin_airports"></div></div>
          <div class="field"><span>Destination airports</span><div data-field="destination_airports"></div></div>
          <div class="field"><span>Airlines</span><div data-field="airlines"></div></div>
          <div class="field"><span>Relative day</span><div class="select-shell"><select data-field="day_offset"></select></div></div>
          <div class="field"><span>Departure range start</span><input type="time" data-field="start_time" value="${option.start_time}"></div>
          <div class="field"><span>Departure range end</span><input type="time" data-field="end_time" value="${option.end_time}"></div>
          <div class="field full-width fare-policy-field">
            <span>Fare policy</span>
            <div class="fare-policy-grid" data-field="fare_class_policy">
              <label class="choice-card compact">
                <input type="radio" name="fare_class_policy_${index}" value="include_basic" ${(!option.fare_class_policy || option.fare_class_policy === "include_basic") ? "checked" : ""}>
                <span>
                  <strong>Include Basic</strong>
                  <small>Track the cheapest economy result even if it is a more restrictive basic fare.</small>
                </span>
              </label>
              <label class="choice-card compact">
                <input type="radio" name="fare_class_policy_${index}" value="exclude_basic" ${option.fare_class_policy === "exclude_basic" ? "checked" : ""}>
                <span>
                  <strong>Exclude Basic</strong>
                  <small>Only compare standard-or-better economy fares.</small>
                </span>
              </label>
            </div>
          </div>
          ${biasEnabled ? `
            <div class="field preference-threshold-field ${index === 0 ? "is-readonly" : ""}">
              <span>${index === 0 ? "Preference buffer" : `Savings needed vs option ${index}`}</span>
              ${
                index === 0
                  ? '<p class="muted">Top preference. Lower-ranked options need savings to beat it.</p>'
                  : `<input type="number" min="0" step="1" data-field="savings_needed_vs_previous" value="${pairwiseBias}">
                     <small class="muted">Must be at least $${pairwiseBias} cheaper than option ${index}.</small>`
              }
            </div>
          ` : ""}
        </div>
      `;
      const daySelect = card.querySelector('[data-field="day_offset"]');
      dayOptions(anchorWeekday).forEach((choice) => {
        const optionEl = document.createElement("option");
        optionEl.value = String(choice.value);
        optionEl.textContent = choice.label;
        if (Number(option.day_offset) === choice.value) {
          optionEl.selected = true;
        }
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
      card.querySelectorAll(`input[name="fare_class_policy_${index}"]`).forEach((input) => {
        input.addEventListener("change", () => {
          if (!input.checked) {
            return;
          }
          option.fare_class_policy = input.value;
          serialize();
        });
      });
      const biasInput = card.querySelector('[data-field="savings_needed_vs_previous"]');
      if (biasInput) {
        biasInput.addEventListener("change", (event) => {
          const nextValue = Math.max(0, Number.parseInt(event.target.value || "0", 10) || 0);
          option.savings_needed_vs_previous = nextValue;
          event.target.value = String(nextValue);
          serialize();
          render();
        });
      } else {
        option.savings_needed_vs_previous = 0;
      }
      pickers.createMultiPicker({
        root: card.querySelector('[data-field="origin_airports"]'),
        options: airports,
        values: option.origin_airports,
        placeholder: "Search origins",
        maxSelections: 3,
        onChange(values) {
          option.origin_airports = values;
          serialize();
        },
      });
      pickers.createMultiPicker({
        root: card.querySelector('[data-field="destination_airports"]'),
        options: airports,
        values: option.destination_airports,
        placeholder: "Search destinations",
        maxSelections: 3,
        onChange(values) {
          option.destination_airports = values;
          serialize();
        },
      });
      pickers.createMultiPicker({
        root: card.querySelector('[data-field="airlines"]'),
        options: airlines,
        values: option.airlines,
        placeholder: "Search airlines",
        onChange(values) {
          option.airlines = values;
          serialize();
        },
      });
      card.querySelector("[data-remove]").addEventListener("click", () => {
        routeOptions = routeOptions.filter((_, itemIndex) => itemIndex !== index);
        if (!routeOptions.length) {
          routeOptions = [blankRouteOption()];
        }
        render();
      });
      card.querySelector("[data-move-up]").addEventListener("click", () => {
        if (index === 0) {
          return;
        }
        [routeOptions[index - 1], routeOptions[index]] = [routeOptions[index], routeOptions[index - 1]];
        render();
      });
      card.querySelector("[data-move-down]").addEventListener("click", () => {
        if (index === routeOptions.length - 1) {
          return;
        }
        [routeOptions[index + 1], routeOptions[index]] = [routeOptions[index], routeOptions[index + 1]];
        render();
      });
      root.appendChild(card);
    });
    serialize();
  }

  addRouteOptionButton.addEventListener("click", () => {
    routeOptions.push(blankRouteOption());
    render();
  });

  tripKindInputs.forEach((input) => {
    input.addEventListener("change", syncKindVisibility);
  });
  preferenceModeInputs.forEach((input) => {
    input.addEventListener("change", render);
  });
  form.querySelector('input[name="anchor_date"]').addEventListener("change", render);
  anchorWeekdaySelect.addEventListener("change", render);
  syncKindVisibility();
})();
