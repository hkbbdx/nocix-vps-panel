import json
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from loguru import logger
from selenium import webdriver
from selenium.common import exceptions
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.wait import WebDriverWait

from backend.app.proxy import ProxyConfig
from nocix_fucker import config
from nocix_fucker import logic
from nocix_fucker import types


def _safe_url(value: str | None) -> str:
    """Keep URL diagnostics useful without exposing credentials or query data."""
    if not value:
        return "[default URL]"
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        if not parsed.scheme or not hostname:
            return "[invalid URL]"
        return urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))
    except ValueError:
        return "[invalid URL]"


class ProxyInitializationError(RuntimeError):
    """Raised when a configured proxy cannot be installed safely."""


def proxy_capabilities(proxy: ProxyConfig | None) -> dict[str, Any]:
    if proxy is None:
        return {}

    host = f"[{proxy.host}]" if ":" in proxy.host else proxy.host
    host_port = f"{host}:{proxy.port}"
    if proxy.scheme == "http":
        return {
            "proxyType": "manual",
            "httpProxy": host_port,
            "sslProxy": host_port,
        }
    if proxy.scheme == "socks5":
        capabilities = {
            "proxyType": "manual",
            "socksProxy": host_port,
            "socksVersion": 5,
        }
        if proxy.username is not None:
            capabilities["socksUsername"] = proxy.username
            capabilities["socksPassword"] = proxy.password
        return capabilities
    raise ProxyInitializationError("unsupported proxy configuration")


def _legacy_proxy_capabilities(proxy: config.ProxyDsn) -> dict[str, Any]:
    """Keep the environment-configured ProxyDsn contract, including SOCKS4."""
    return proxy.dict


def _proxy_config(proxy: ProxyConfig | config.ProxyDsn) -> ProxyConfig | None:
    if isinstance(proxy, ProxyConfig):
        return proxy
    if str(proxy.scheme) not in {"http", "socks5"}:
        return None
    return ProxyConfig(
        scheme=str(proxy.scheme),
        host=str(proxy.host),
        port=int(proxy.port),
        username=proxy.user,
        password=proxy.password,
    )


def _create_http_auth_extension(username: str, password: str) -> Path:
    extension_dir = Path(tempfile.mkdtemp(prefix="nocix-proxy-auth-"))
    archive_path = extension_dir / "proxy-auth.xpi"
    manifest = {
        "manifest_version": 2,
        "name": "NOCIX proxy authentication",
        "version": "1.0",
        "permissions": ["webRequest", "webRequestBlocking", "<all_urls>"],
        "background": {"scripts": ["background.js"]},
    }
    credentials = json.dumps(
        {"username": username, "password": password}, ensure_ascii=True
    )
    background = (
        "browser.webRequest.onAuthRequired.addListener("
        "function(details) { return {authCredentials: "
        + credentials
        + "}; }, "
        '{"urls": ["<all_urls>"]}, ["blocking"]);'
    )
    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("background.js", background)
    except Exception:
        shutil.rmtree(extension_dir, ignore_errors=True)
        raise
    return extension_dir


class Client:
    def __init__(
        self,
        remote_browser_dsn: str,
        proxy_dsn: ProxyConfig | config.ProxyDsn | None,
    ) -> None:
        logger.trace("Connecting to remote browser")

        options = webdriver.FirefoxOptions()
        extension_dir: Path | None = None
        proxy = _proxy_config(proxy_dsn) if proxy_dsn else None
        has_proxy = proxy_dsn is not None

        if proxy_dsn:
            logger.trace("Proxy detected, configurating")

            try:
                capabilities = (
                    proxy_capabilities(proxy)
                    if proxy is not None
                    else _legacy_proxy_capabilities(proxy_dsn)
                )
                options.capabilities.update(capabilities)
                if proxy is not None and proxy.scheme == "http" and proxy.has_credentials:
                    extension_dir = _create_http_auth_extension(
                        proxy.username, proxy.password
                    )
                    options.add_extension(str(extension_dir / "proxy-auth.xpi"))
            except Exception as exc:
                if extension_dir is not None:
                    shutil.rmtree(extension_dir, ignore_errors=True)
                if isinstance(exc, ProxyInitializationError):
                    raise
                raise ProxyInitializationError(
                    "HTTP proxy authentication extension could not be installed"
                    if proxy is not None and proxy.scheme == "http" and proxy.has_credentials
                    else "proxy configuration could not be installed"
                ) from None

        try:
            driver = webdriver.Remote(command_executor=remote_browser_dsn, options=options)
        except Exception:
            if extension_dir is not None:
                shutil.rmtree(extension_dir, ignore_errors=True)
            if has_proxy:
                raise ProxyInitializationError("proxy browser initialization failed") from None
            raise
        try:
            driver.maximize_window()
            wait = WebDriverWait(driver, 10, 5)
        except Exception as exc:
            try:
                driver.quit()
            except Exception:
                logger.warning("Failed to clean up browser after setup failure")
            if extension_dir is not None:
                shutil.rmtree(extension_dir, ignore_errors=True)
            if has_proxy:
                raise ProxyInitializationError("proxy browser initialization failed") from None
            raise exc

        self._driver = driver
        self._wait = wait
        self._proxy_extension_dir = extension_dir
        self.last_price_text: str | None = None

    def _find_visible_element(self, selectors: tuple[tuple[str, str], ...]) -> WebElement | None:
        elements = self._find_visible_elements(selectors)
        return elements[0] if elements else None

    def _find_visible_elements(
        self, selectors: tuple[tuple[str, str], ...]
    ) -> list[WebElement]:
        def find(driver):
            visible_elements = []
            for find_by, find_value in selectors:
                try:
                    elements = driver.find_elements(find_by, find_value)
                except Exception:
                    continue
                for element in elements:
                    try:
                        if element.is_displayed():
                            visible_elements.append(element)
                    except Exception:
                        continue
            return visible_elements or False

        try:
            return self._wait.until(find)
        except exceptions.TimeoutException:
            return []

    def _visible_login_form_controls(
        self, container: WebElement
    ) -> tuple[WebElement, WebElement, WebElement] | None:
        def descendant(selectors: tuple[tuple[str, str], ...]) -> WebElement | None:
            for find_by, find_value in selectors:
                try:
                    elements = container.find_elements(find_by, find_value)
                except Exception:
                    continue
                for element in elements:
                    try:
                        if element.is_displayed():
                            return element
                    except Exception:
                        continue
            return None

        email = descendant(
            (
                (By.NAME, "existing_username"),
                (By.NAME, "email"),
                (By.CSS_SELECTOR, "input[type='email']"),
            )
        )
        password = descendant(
            (
                (By.NAME, "existing_password"),
                (By.NAME, "password"),
                (By.CSS_SELECTOR, "input[type='password']"),
            )
        )
        submit = descendant(
            (
                (By.CLASS_NAME, "hvr-sweep-to-right"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
            )
        )
        if email is None or password is None or submit is None:
            return None
        owners = []
        for control in (email, password, submit):
            try:
                owner = control.find_elements(By.XPATH, "ancestor::form[1]")
            except Exception:
                owner = []
            if owner:
                owners.append(owner[0])
        if owners and len(owners) != 3:
            return None
        if owners and any(owner != owners[0] for owner in owners[1:]):
            return None
        return email, password, submit

    def _visible_login_form(self) -> tuple[WebElement, WebElement, WebElement] | None:
        containers = self._find_visible_elements(
            (
                (By.CSS_SELECTOR, "form[name='existing_customer']"),
                (By.CSS_SELECTOR, "form#existing_customer"),
                (By.CSS_SELECTOR, "form.existing-customer"),
                (By.CSS_SELECTOR, "[data-testid='existing-customer-form']"),
                (By.TAG_NAME, "form"),
            )
        )
        for container in containers:
            controls = self._visible_login_form_controls(container)
            if controls is not None:
                return controls

        common_ancestors = self._find_visible_elements(
            (
                (
                    By.XPATH,
                    "//*[.//input[@name='existing_username'] and "
                    ".//input[@name='existing_password'] and "
                    "(.//button[@type='submit'] or .//input[@type='submit'] or "
                    ".//*[contains(@class, 'hvr-sweep-to-right')])]",
                ),
            )
        )
        for ancestor in common_ancestors:
            controls = self._visible_login_form_controls(ancestor)
            if controls is not None:
                return controls
        return None

    def login_existing_customer(self, email: str, password: str) -> bool:
        """Submit the visible existing-customer form twice and expose code state."""
        form = self._visible_login_form()
        if form is None:
            return False

        for _ in range(2):
            try:
                form[0].clear()
                form[1].clear()
                form[0].send_keys(email)
                form[1].send_keys(password)
                form[2].click()
            except Exception:
                return False

            if _ == 0:
                form = self._visible_login_form()
                if form is None:
                    return False

        return True

    def is_email_code_required(self) -> bool:
        code_field = self._find_visible_element(
            (
                (By.CSS_SELECTOR, "input[name='email_code']"),
                (By.CSS_SELECTOR, "input[name='verification_code']"),
                (By.CSS_SELECTOR, "input[name='code']"),
                (By.CSS_SELECTOR, "input[autocomplete='one-time-code']"),
                (By.ID, "email_code"),
                (By.ID, "verification_code"),
            )
        )
        if code_field is not None:
            return True

        marker = self._find_visible_element(
            (
                (By.CSS_SELECTOR, "[data-testid='email-code']"),
                (By.CSS_SELECTOR, "form[data-purpose='email-verification']"),
                (By.ID, "email-code-form"),
            )
        )
        if marker is not None:
            return True

        body = self._find_visible_element(((By.TAG_NAME, "body"),))
        if body is None:
            return False
        page_text = " ".join((getattr(body, "text", "") or "").lower().split())
        return any(
            marker_text in page_text
            for marker_text in (
                "verification code",
                "email verification",
                "one-time code",
            )
        )

    def submit_email_code(self, code: str) -> bool:
        if not isinstance(code, str) or re.fullmatch(r"[0-9]{4,12}", code) is None:
            return False

        field = self._find_visible_element(
            (
                (By.CSS_SELECTOR, "input[name='email_code']"),
                (By.CSS_SELECTOR, "input[name='verification_code']"),
                (By.CSS_SELECTOR, "input[name='code']"),
                (By.CSS_SELECTOR, "input[autocomplete='one-time-code']"),
                (By.ID, "email_code"),
                (By.ID, "verification_code"),
            )
        )
        if field is None:
            return False

        try:
            field.clear()
            field.send_keys(code)
            submit = self._find_visible_element(
                (
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    (By.CSS_SELECTOR, "input[type='submit']"),
                    (By.CSS_SELECTOR, ".email-code-submit"),
                )
            )
            if submit is None:
                field.clear()
                return False
            submit.click()
            self._wait.until(lambda driver: not self.is_email_code_required())
            return True
        except exceptions.TimeoutException:
            try:
                field.clear()
            except Exception:
                pass
            return False
        except Exception:
            try:
                field.clear()
            except Exception:
                pass
            return False

    def close(self) -> None:
        logger.trace("Closing windows and disconnecting from remote browser")
        try:
            self._driver.quit()
        finally:
            extension_dir = getattr(self, "_proxy_extension_dir", None)
            if extension_dir is not None:
                shutil.rmtree(extension_dir, ignore_errors=True)
                self._proxy_extension_dir = None

    def test_connection(self, url: str) -> None:
        self._driver.get(url)

    @property
    def current_url(self) -> str:
        return self._driver.current_url

    def _find_element(self, find_by=By.ID, find_value=None) -> WebElement | None:
        try:
            return self._wait.until(
                expected_conditions.presence_of_element_located((find_by, find_value))
            )
        except exceptions.TimeoutException:
            raise RuntimeError(
                f"Timed out while finding element {find_by}={find_value!r}"
            ) from None

    def _find_alert(self) -> Any | None:
        try:
            return self._wait.until(expected_conditions.alert_is_present())
        except exceptions.TimeoutException:
            return None

    def _find_list_and_select(
        self,
        display_name: str,
        target_option_value: str,
        find_by=By.ID,
        find_value=None,
    ) -> bool:
        logger.trace(f"Finding {display_name} select list")
        select_element = self._find_element(find_by, find_value)
        select_object = Select(select_element)

        logger.trace(f"Finding available {display_name} options")
        for option in select_object.options:
            if target_option_value.lower() in option.text.lower():
                logger.debug(f"Found {display_name} option: {option.text}")

                if option.is_selected():
                    logger.trace(f"'{option.text}' is already selected")
                    return True

                logger.trace(f"Selecting '{option.text}'")
                option.click()
                return True

        logger.trace(f"Cannot find '{target_option_value}' from options")
        return False

    def _find_button_and_click(
        self,
        display_name: str,
        find_by=By.ID,
        find_value=None,
    ) -> None:
        logger.trace(f"Finding {display_name} button")
        button = self._find_element(find_by, find_value)
        logger.trace(f"Clicking {display_name} button")
        button.click()

    def click_next_step_button(self) -> None:
        self._find_button_and_click(
            display_name="next step",
            find_by=By.CLASS_NAME,
            find_value="hvr-sweep-to-right",
        )

    def _find_and_select_country(self, value: str) -> bool:
        return self._find_list_and_select(
            display_name="country",
            target_option_value=value,
            find_by=By.NAME,
            find_value="country",
        )

    def _find_box_and_fill(
        self,
        display_name: str,
        value: str,
        find_by=By.ID,
        find_value=None,
    ) -> None:
        logger.trace(f"Finding {display_name} box")
        box = self._find_element(find_by, find_value)
        logger.trace(f"Filling {display_name}")
        box.send_keys(value)

    def check_stock(self, goods_id: str, stock_url: str | None = None) -> bool:
        target_url = stock_url or f"https://nocix.net/out-of-stock/?id={goods_id}"
        logger.trace(f"Requesting goods page: {_safe_url(target_url)}")
        self._driver.get(target_url)

        body = self._find_element(By.TAG_NAME, "body")
        page_text = body.text
        current_url = self._driver.current_url
        logger.debug(f"Stock page URL: {_safe_url(current_url)}")
        return logic.is_in_stock(page_text, current_url)

    def open_cart(self, goods_id: str, cart_url: str | None = None) -> None:
        target_url = cart_url or f"https://nocix.net/cart/?id={goods_id}"
        logger.trace(f"Opening product cart page: {_safe_url(target_url)}")
        self._driver.get(target_url)

    def wait_until_in_stock(self, goods_id: str, wait: float = 2.5) -> None:
        while True:
            logger.trace("Checking stock")
            if self.check_stock(goods_id):
                return
            logger.trace(f"Out of stock, sleep for {wait} second")
            time.sleep(wait)

    def select_operating_system(self, value: str) -> bool:
        return self._find_list_and_select(
            display_name="operating system",
            target_option_value=value,
            find_by=By.ID,
            find_value="2",
        )

    def _find_price_and_parse(self) -> str:
        logger.trace("Finding price element")
        price_element = self._find_element(find_by=By.ID, find_value="due_today")

        logger.trace("Parsing price from text")
        logger.debug(f"Price in string format: {price_element.text}")
        self.last_price_text = price_element.text
        return self.last_price_text

    def match_price(self, target_price: float) -> bool:
        price = self._find_price_and_parse()
        return logic.prices_match(price, target_price)

    def _select_customer_type(self, new: bool) -> None:
        logger.debug(f"New customer: {new}")
        if new:
            logger.trace("Selecting new customer")
            self._find_button_and_click(
                display_name="new customer", find_by=By.ID, find_value="radio-5"
            )
        else:
            logger.trace("Selecting existing customer")
            self._find_button_and_click(
                display_name="existing customer", find_by=By.ID, find_value="radio-9"
            )

    def _fill_in_new_customer_info(
        self,
        *,
        email: str,
        first_name: str,
        last_name: str,
        company: str,
        phone: str,
        address: str,
        city: str,
        state: str,
        zip: str,
        country_name: str,
    ) -> None:
        self._find_and_select_country(country_name)

        items = [
            "email",
            "first_name",
            "last_name",
            "company",
            "phone",
            "address",
            "city",
            "state",
            "zip",
        ]
        for item in items:
            self._find_box_and_fill(
                display_name=item.replace(
                    "_",
                    " ",
                ),
                value=locals()[item],
                find_by=By.NAME,
                find_value=item,
            )

    def _fill_in_existing_customer_info(
        self, existing_username: str, existing_password: str
    ) -> None:
        items = [
            "existing_username",
            "existing_password",
        ]
        for item in items:
            self._find_box_and_fill(
                display_name=item.replace(
                    "_",
                    " ",
                ),
                value=locals()[item],
                find_by=By.NAME,
                find_value=item,
            )

    def fill_in_customer_info(
        self,
        *,
        new: bool,
        email: str,
        password: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        company: str | None = None,
        phone: str | None = None,
        address: str | None = None,
        city: str | None = None,
        state: str | None = None,
        postal_code: str | None = None,
        country_name: str | None = None,
    ) -> None:
        logger.trace("Selecting customer type")
        self._select_customer_type(new)
        if new:
            logger.trace("Filling new customer info")
            self._fill_in_new_customer_info(
                email=email,
                first_name=first_name,
                last_name=last_name,
                company=company,
                phone=phone,
                address=address,
                city=city,
                state=state,
                zip=postal_code,
                country_name=country_name,
            )
        else:
            logger.trace("Filling existing customer info")
            self._fill_in_existing_customer_info(
                existing_username=email, existing_password=password
            )

    def _select_payment_method(self, value: str) -> None:
        logger.debug(f"Payment method: {value}")
        self._find_button_and_click(
            display_name=value,
            find_by=By.XPATH,
            find_value=f".//input[@value='{value}']",
        )

    def _fill_in_credit_card_info(
        self,
        *,
        cc_num: str,
        cc_exp_month: str,
        cc_exp_year: str,
        cc_ccv: str,
        first_name: str,
        last_name: str,
        company: str,
        address: str,
        city: str,
        state: str,
        zip: str,
        country_name: str,
    ) -> None:
        self._find_box_and_fill(
            display_name="credit card expiration month",
            value=cc_exp_month,
            find_by=By.XPATH,
            find_value=".//input[@placeholder='MM']",
        )
        self._find_box_and_fill(
            display_name="credit card expiration year",
            value=cc_exp_year,
            find_by=By.XPATH,
            find_value=".//input[@placeholder='YY']",
        )

        self._find_and_select_country(country_name)

        items = [
            "cc_num",
            "cc_ccv",
            "first_name",
            "last_name",
            "company",
            "address",
            "city",
            "state",
            "zip",
        ]
        for item in items:
            self._find_box_and_fill(
                display_name=item.replace(
                    "_",
                    " ",
                ),
                value=locals()[item],
                find_by=By.NAME,
                find_value=item,
            )

        self._find_button_and_click(
            display_name="accept terms", find_by=By.ID, find_value="accept_terms"
        )

    def _accept_terms(self) -> None:
        self._find_button_and_click(
            display_name="accept terms", find_by=By.ID, find_value="accept_terms"
        )

    def fill_in_payment_info(
        self,
        *,
        payment_method: types.PaymentMethod,
        cc_num: str | None = None,
        cc_exp_month: str | None = None,
        cc_exp_year: str | None = None,
        cc_ccv: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        company: str | None = None,
        address: str | None = None,
        city: str | None = None,
        state: str | None = None,
        postal_code: str | None = None,
        country_name: str | None = None,
    ) -> None:
        logger.trace("Selecting payment method")
        self._select_payment_method(payment_method.value)

        match payment_method:
            case types.PaymentMethod.BITCOIN:
                self._accept_terms()
            case types.PaymentMethod.PAYPAL:
                self._accept_terms()
            case types.PaymentMethod.CREDIT_CARD:
                logger.trace("Filling credit card info")
                self._fill_in_credit_card_info(
                    cc_num=cc_num,
                    cc_exp_month=cc_exp_month,
                    cc_exp_year=cc_exp_year,
                    cc_ccv=cc_ccv,
                    first_name=first_name,
                    last_name=last_name,
                    company=company,
                    address=address,
                    city=city,
                    state=state,
                    zip=postal_code,
                    country_name=country_name,
                )
            case _:
                raise NotImplementedError(
                    f"Payment method {payment_method} is not supported"
                )

    def submit_order(self) -> str | None:
        self._find_button_and_click(
            display_name="submit order",
            find_by=By.ID,
            find_value="submit_order_btn",
        )

        alert = self._find_alert()
        if alert:
            return alert.text

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
