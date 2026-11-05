
import logging
import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)
DOMAIN = "ingstocks"

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    isin = config.get("isin")
    if not isin:
        _LOGGER.error("Keine ISIN angegeben!")
        return
    async_add_entities([INGStocksSensor(isin, async_get_clientsession(hass))], True)

class INGStocksSensor(Entity):
    def __init__(self, isin, session):
        self._isin = isin
        self._state = None
        self._attributes = {}
        self._available = True
        self._session = session

    @property
    def available(self):
        return self._available

    @property
    def device_class(self):
        return "monetary"

    @property
    def unit_of_measurement(self):
        return "€"

    @property
    def icon(self):
        return "mdi:currency-eur"

    @property
    def name(self):
        return f"ING Stocks {self._isin}"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_update(self):
        header_url = f"https://component-api.wertpapiere.ing.de/api/v1/components/instrumentheader/{self._isin}"
        keyfigures_url = f"https://component-api.wertpapiere.ing.de/api/v1/share-ng/keyfigures/{self._isin}"
        timeout = aiohttp.ClientTimeout(total=15)

        try:
            async with self._session.get(header_url, timeout=timeout) as response:
                response.raise_for_status()
                data = await response.json()
            if not isinstance(data, dict):
                raise ValueError("Unerwartete Kursdaten-Antwort")
            price = data.get("price")
            if price is None:
                raise ValueError("Kein Kurswert in der API-Antwort")

            attributes = {
                "name": data.get("name"),
                "isin": data.get("isin"),
                "currency": data.get("currencySign"),
                "change_percent": round(float(data.get("changePercent") or 0), 2),
                "change_absolute": data.get("changeAbsolute"),
                "exchange": data.get("exchangeName"),
                "last_update": data.get("priceChangeDate"),
            }

            async with self._session.get(keyfigures_url, timeout=timeout) as response:
                response.raise_for_status()
                keyfigures = await response.json()
            if not isinstance(keyfigures, dict):
                raise ValueError("Unerwartete Kennzahlen-Antwort")
            attributes.update({
                "dividend_yield": round(float(keyfigures.get("dividendYield") or 0), 4),
                "dividend_per_share": keyfigures.get("dividendPerShare"),
                "price_earnings_ratio": keyfigures.get("priceEarningsRatio"),
                "market_capitalization": keyfigures.get("marketCapitalization"),
                "market_cap_currency": keyfigures.get("marketCapitalizationCurrencyIsoCode"),
                "52w_low": keyfigures.get("fiftyTwoWeekLow"),
                "52w_high": keyfigures.get("fiftyTwoWeekHigh"),
            })
            self._state = round(float(price), 2)
            self._attributes = attributes
            self._available = True
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError) as err:
            _LOGGER.warning("ING-Kursabfrage für %s fehlgeschlagen: %s", self._isin, err)
            self._available = False
