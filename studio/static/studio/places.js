// Use structured components; a formatted address is not a reliable city name.
export function extractBirthLocation(components = []) {
  const component = (type) => components.find((part) => part.types?.includes(type));
  const town = component('locality') || component('postal_town');
  const city = town?.longText?.trim() || '';
  const countryCode = component('country')?.shortText?.trim().toUpperCase() || '';
  if (!city || !/^[A-Z]{2}$/.test(countryCode)) return null;
  return {city, countryCode};
}

async function initialisePlaces(config) {
  const container = document.getElementById('birth-location-search');
  const status = document.getElementById('birth-location-status');
  const city = document.getElementById('id_city');
  const country = document.getElementById('id_countryCode');
  const form = city.form;
  let selectionNumber = 0;
  const fallback = () => {
    container.hidden = false;
    status.textContent = 'Location search is temporarily unavailable. Please try again later.';
  };
  try {
    await new Promise((resolve, reject) => {
      window.venastellaPlacesReady = resolve;
      const script = document.createElement('script');
      const url = new URL('https://maps.googleapis.com/maps/api/js');
      url.search = new URLSearchParams({key: config.apiKey, loading: 'async', callback: 'venastellaPlacesReady', v: 'quarterly', language: 'en'});
      script.src = url.href;
      script.async = true;
      script.onerror = reject;
      document.head.append(script);
    });
    const {PlaceAutocompleteElement} = await google.maps.importLibrary('places');
    const search = new PlaceAutocompleteElement({includedPrimaryTypes: ['locality']});
    search.id = 'birth-place-search';
    search.setAttribute('aria-label', 'Search your birth town or city');
    document.getElementById('birth-place-widget').append(search);
    container.hidden = false;
    search.addEventListener('gmp-error', fallback);
    search.addEventListener('input', () => {
      selectionNumber += 1;
      form.querySelector('button[type=submit]').disabled = false;
      city.value = '';
      country.value = '';
      status.textContent = 'Select your birth town from the suggestions.';
    });
    search.addEventListener('gmp-select', async ({placePrediction}) => {
      const thisSelection = ++selectionNumber;
      const submit = form.querySelector('button[type=submit]');
      submit.disabled = true;
      // Never retain an old location if the new selection cannot be resolved.
      city.value = '';
      country.value = '';
      status.textContent = 'Finding town and country…';
      try {
        const place = placePrediction.toPlace();
        await place.fetchFields({fields: ['addressComponents']});
        if (thisSelection !== selectionNumber) return;
        const location = extractBirthLocation(place.addressComponents);
        if (!location) {
          status.textContent = 'We could not identify a town and country for that place. Please choose another suggestion.';
          return;
        }
        city.value = location.city;
        country.value = location.countryCode;
        status.textContent = `Selected: ${location.city}.`;
      } catch {
        if (thisSelection === selectionNumber) fallback();
      } finally {
        if (thisSelection === selectionNumber) submit.disabled = false;
      }
    });
  } catch {
    fallback();
  }
}

if (typeof document !== 'undefined') {
  const config = document.getElementById('google-places-config');
  if (config) initialisePlaces(JSON.parse(config.textContent));
}
