(() => {
  const bookingState = window.travelAgentApp?.readJsonScript("booking-form-data");
  const pickers = window.travelAgentPickers;
  if (!bookingState || !pickers) {
    return;
  }

  const catalogs = bookingState.catalogs || {};
  document.querySelectorAll("[data-single-picker-field]").forEach((field) => {
    const type = field.dataset.pickerType;
    const options = type === "airline" ? (catalogs.airlines || []) : (catalogs.airports || []);
    pickers.createSinglePicker({ field, options });
  });
})();
