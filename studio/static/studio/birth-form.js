const time = document.getElementById('id_birth_time');
const unknown = document.getElementById('id_unknown_birth_time');
if (time && unknown) {
  const toggle = () => {
    if (unknown.checked) time.value = '';
    time.disabled = unknown.checked;
  };
  unknown.addEventListener('change', toggle);
  toggle();
}
const city = document.getElementById('id_city');
const country = document.getElementById('id_countryCode');
if (city && country) {
  city.form.addEventListener('submit', (event) => {
    if (!city.value.trim() || !/^[A-Z]{2}$/.test(country.value)) {
      event.preventDefault();
      document.getElementById('birth-location-status').textContent = 'Please select your birth town from the location suggestions before submitting.';
      document.getElementById('birth-location-search').scrollIntoView({block: 'center'});
    }
  });
}
